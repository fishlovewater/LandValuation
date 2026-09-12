from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError, ResourceNotFoundError
from app.storage.paths import build_generated_report_object_key
from app.storage.service import StorageService
from app.valuation.documents.repository import DocumentRepository
from app.valuation.documents.service import safe_filename
from app.valuation.models import (
    BenchmarkLandRecord,
    BenchmarkValuationRecord,
    CaseEventRecord,
    ComparisonFactorValueRecord,
    DocumentRecord,
    ExtractedFieldRecord,
    FormInstanceRecord,
    ParcelRecord,
    ValuationLocationRecord,
    ValidationRunRecord,
)
from app.valuation.f01_f04_schemas import F04DraftData
from app.valuation.report_packages.complete_draft_pdf_builder import (
    build_six_page_formal_pdf,
)
from app.valuation.pdf_errors import build_pdf_safely
from app.valuation.report_packages.factor_catalog import (
    INDIVIDUAL_FACTOR_CODES,
    TEMPLATE_FACTOR_CODES,
)
from app.valuation.report_packages.formal_calculation import (
    FactorAdjustment,
    LevelValue,
    TargetPriceInput,
    calculate_benchmark_comparison_price,
    calculate_level_adjustment,
    calculate_target_price,
    sum_absolute_adjustments,
    sum_adjustments,
)
from app.valuation.report_packages.formal_schemas import (
    FormalCalculationResponse,
    FormalReportResponse,
    FormalTargetCalculationResponse,
    FormalValidationFinding,
    FormalValidationResponse,
    FormalWorkflowStatusResponse,
    TemplateExportResponse,
)
from app.valuation.report_packages.formal_xlsx_builder import build_formal_report_xlsx
from app.valuation.report_packages.template_exports import (
    EXCEL_MIME,
    TEMPLATE_EXPORTS,
    build_template_export_xlsx,
)
from app.valuation.report_packages.page_schemas import (
    F02DraftData,
    F02RFDraftData,
    S01DraftData,
)
from app.valuation.report_packages.page_service import ReportPageService
from app.valuation.report_packages.repository import ReportPackageRepository
from app.valuation.rule_packs.coverage import (
    NEW_TAIPEI_CITYWIDE_SCOPE,
    NEW_TAIPEI_DISTRICT_CODES,
)
from app.valuation.schemas import FormStatus


FORMAL_FORMULA_CODE = "NTPC_COMPARISON_V1"
FORMAL_ROUNDING_CODE = "NTPC_LAND_PRICE_V1"
MAP_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
MAX_OFFICIAL_TEMPLATE_BYTES = 30 * 1024 * 1024
MAX_OFFICIAL_TEMPLATE_MANIFEST_BYTES = 1024 * 1024
LAND_USE_ALIASES = {
    "住宅用地": "RESIDENTIAL",
    "商業用地": "COMMERCIAL",
    "工業用地": "INDUSTRIAL",
    "農業用地": "AGRICULTURAL",
    "其他": "OTHER",
}


def _read_and_close(response) -> bytes:
    try:
        return response.read()
    finally:
        response.close()
        release = getattr(response, "release_conn", None)
        if callable(release):
            release()


async def _optional_official_template_assets(
    storage: StorageService,
) -> tuple[bytes | None, dict | None]:
    settings = get_settings()
    template_key = settings.official_report_blank_template_object_key
    manifest_key = settings.official_report_blank_template_manifest_object_key
    if template_key is None:
        return None, None
    template_response = await storage.download(template_key)
    manifest_response = await storage.download(manifest_key or "")
    template_bytes = await run_in_threadpool(_read_and_close, template_response)
    manifest_bytes = await run_in_threadpool(_read_and_close, manifest_response)
    if len(template_bytes) > MAX_OFFICIAL_TEMPLATE_BYTES:
        raise AppError(
            "OFFICIAL_TEMPLATE_TOO_LARGE",
            "官方空白 PDF 超過 30 MB 上限",
            500,
        )
    if len(manifest_bytes) > MAX_OFFICIAL_TEMPLATE_MANIFEST_BYTES:
        raise AppError(
            "OFFICIAL_TEMPLATE_MANIFEST_TOO_LARGE",
            "官方模板 manifest 超過 1 MB 上限",
            500,
        )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
            "官方模板 manifest 不是有效的 UTF-8 JSON",
            500,
        ) from exc
    if not isinstance(manifest, dict):
        raise AppError(
            "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
            "官方模板 manifest 根節點必須為 JSON object",
            500,
        )
    return template_bytes, manifest


class FormalReportService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageService | None = None,
        repository: ReportPackageRepository | None = None,
        pages: ReportPageService | None = None,
        documents: DocumentRepository | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.repository = repository or ReportPackageRepository(session)
        self.pages = pages or ReportPageService(
            session,
            repository=self.repository,
        )
        self.documents = documents or DocumentRepository(session)

    async def calculate(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
    ) -> FormalCalculationResponse:
        case, records = await self.pages._editable_records(case_id, report_id, user)
        regional = self.pages._read_data(records["F02-RF"], F02RFDraftData)
        comparison = self.pages._read_data(records["F02"], F02DraftData)
        if not comparison.comparison_workflow_enabled:
            return await self._calculate_without_comparison(
                case_id=case_id,
                report_id=report_id,
                case=case,
                records=records,
                regional=regional,
                comparison=comparison,
                user=user,
            )
        self.pages._validate_cross_page_ids(regional, comparison)
        regional = await self.pages._ensure_default_formal_rule(
            case, records["F02-RF"], regional, user
        )
        if regional.benchmark_land_id is None or regional.comparison_analysis_id is None:
            raise AppError(
                "COMPARISON_ANALYSIS_REQUIRED",
                "正式計算前必須指定比準地與比較分析",
                422,
            )
        if not 1 <= len(comparison.comparison_targets) <= 3:
            raise AppError("COMPARISON_TARGET_COUNT", "比較標的必須為 1 至 3 筆", 422)

        analysis = await self.repository.get_comparison_analysis(
            case_id, regional.comparison_analysis_id
        )
        if analysis is None:
            raise ResourceNotFoundError("比較分析")
        db_targets = await self.repository.list_comparison_targets(
            case_id, regional.comparison_analysis_id
        )
        db_target_by_id = {item.comparison_target_id: item for item in db_targets}
        selected_ids = {
            item.comparison_target_id for item in comparison.comparison_targets
        }
        if not selected_ids.issubset(db_target_by_id):
            raise AppError(
                "CROSS_CASE_REFERENCE",
                "F02 比較標的不存在或不屬於指定比較分析",
                422,
            )

        rule, level_lookup = await self._formal_rule_and_levels(
            case,
            regional.rule_version_id,
            TEMPLATE_FACTOR_CODES | INDIVIDUAL_FACTOR_CODES,
        )
        regional_codes = {item.factor_code for item in regional.factor_rows}
        if regional_codes != TEMPLATE_FACTOR_CODES:
            missing = sorted(TEMPLATE_FACTOR_CODES - regional_codes)
            extra = sorted(regional_codes - TEMPLATE_FACTOR_CODES)
            raise AppError(
                "F02_RF_FACTOR_COVERAGE_INCOMPLETE",
                "F02-RF 必須完整包含範本的正式區域因素",
                422,
                {"missing": missing, "extra": extra},
            )

        target_regional: dict[UUID, list[FactorAdjustment]] = {
            target_id: [] for target_id in selected_ids
        }
        factor_value_records: list[ComparisonFactorValueRecord] = []
        for row in regional.factor_rows:
            benchmark_level = (
                self._resolve_level(
                    level_lookup, row.factor_code, row.benchmark_confirmed_level
                )
                if row.benchmark_confirmed_level
                else None
            )
            row_target_by_id = {
                item.comparison_target_id: item for item in row.targets
            }
            for target_id, target_draft in row_target_by_id.items():
                comparable_level = (
                    self._resolve_level(
                        level_lookup, row.factor_code, target_draft.confirmed_level
                    )
                    if target_draft.confirmed_level
                    else None
                )
                if benchmark_level and comparable_level:
                    adjustment = calculate_level_adjustment(
                        benchmark_level, comparable_level
                    )
                else:
                    adjustment = FactorAdjustment(
                        benchmark=benchmark_level or self._dummy_level(row.factor_code),
                        comparable=comparable_level or self._dummy_level(row.factor_code),
                        adjustment_rate=Decimal("0"),
                        maximum_impact_rate=Decimal("0"),
                    )
                target_draft.calculated_adjustment_rate = adjustment.adjustment_rate
                target_regional[target_id].append(adjustment)
                factor_value_records.append(
                    self._factor_value_record(
                        target_id,
                        adjustment,
                        target_draft.source_notes or row.source_notes,
                    )
                )

        target_results = []
        response_targets = []
        regional.regional_adjustment_rates = {}
        for selected in sorted(
            comparison.comparison_targets, key=lambda item: item.display_order
        ):
            db_target = db_target_by_id[selected.comparison_target_id]
            individual_adjustments: list[FactorAdjustment] = []
            for factor in selected.individual_factors:
                benchmark_level = (
                    self._resolve_level(
                        level_lookup,
                        factor.factor_code,
                        factor.benchmark_confirmed_level,
                    )
                    if factor.benchmark_confirmed_level
                    else None
                )
                comparable_level = (
                    self._resolve_level(
                        level_lookup,
                        factor.factor_code,
                        factor.comparable_confirmed_level,
                    )
                    if factor.comparable_confirmed_level
                    else None
                )
                if benchmark_level and comparable_level:
                    adjustment = calculate_level_adjustment(
                        benchmark_level, comparable_level
                    )
                else:
                    adjustment = FactorAdjustment(
                        benchmark=benchmark_level or self._dummy_level(factor.factor_code),
                        comparable=comparable_level or self._dummy_level(factor.factor_code),
                        adjustment_rate=Decimal("0"),
                        maximum_impact_rate=Decimal("0"),
                    )
                factor.calculated_adjustment_rate = adjustment.adjustment_rate
                individual_adjustments.append(adjustment)
                factor_value_records.append(
                    self._factor_value_record(
                        selected.comparison_target_id,
                        adjustment,
                        factor.source_notes,
                    )
                )
            if selected.weight is None:
                selected.weight = Decimal("1")


            regional_adjustments = target_regional[selected.comparison_target_id]
            regional_rate = sum_adjustments(regional_adjustments)
            individual_rate = sum_adjustments(individual_adjustments)
            result = calculate_target_price(
                TargetPriceInput(
                    comparison_target_id=selected.comparison_target_id,
                    normal_unit_price=db_target.normal_unit_price_snapshot,
                    time_adjustment_rate=selected.time_adjustment_rate,
                    regional_adjustment_rate=regional_rate,
                    individual_adjustment_rate=individual_rate,
                    regional_absolute_total=sum_absolute_adjustments(
                        regional_adjustments
                    ),
                    individual_absolute_total=sum_absolute_adjustments(
                        individual_adjustments
                    ),
                    weight=selected.weight,
                )
            )
            selected.regional_adjustment_rate = regional_rate
            selected.individual_adjustment_rate = individual_rate
            selected.total_adjustment_absolute = result.total_adjustment_absolute
            selected.trial_price = result.trial_price
            selected.normal_unit_price_snapshot = db_target.normal_unit_price_snapshot
            selected.transaction_date_snapshot = db_target.transaction_date_snapshot
            selected.date_adjusted_price = result.date_adjusted_price
            selected.regional_adjusted_price = result.regional_adjusted_price
            regional.regional_adjustment_rates[
                str(selected.comparison_target_id)
            ] = regional_rate
            db_target.time_adjustment_rate = selected.time_adjustment_rate
            db_target.regional_adjustment_rate = regional_rate
            db_target.total_adjustment_absolute = result.total_adjustment_absolute
            db_target.trial_price = result.trial_price
            db_target.weight = selected.weight
            db_target.condition_notes = selected.individual_condition_notes or None
            target_results.append(result)
            response_targets.append(
                FormalTargetCalculationResponse(
                    comparison_target_id=selected.comparison_target_id,
                    regional_adjustment_rate=regional_rate,
                    individual_adjustment_rate=individual_rate,
                    total_adjustment_absolute=result.total_adjustment_absolute,
                    date_adjusted_price=result.date_adjusted_price,
                    regional_adjusted_price=result.regional_adjusted_price,
                    trial_price=result.trial_price,
                    weight=result.weight,
                )
            )

        benchmark_price = calculate_benchmark_comparison_price(target_results)
        now = datetime.now(UTC)
        input_snapshot = self._input_snapshot(
            case, regional, comparison, db_target_by_id
        )
        fingerprint = self._fingerprint(input_snapshot)
        calculation_snapshot = {
            "formula_code": rule.formula_code,
            "rounding_code": rule.rounding_code,
            "rule_version_id": str(rule.rule_version_id),
            "rule_version_no": rule.version_no,
            "input_fingerprint": fingerprint,
            "inputs": input_snapshot,
            "targets": [item.model_dump(mode="json") for item in response_targets],
            "benchmark_comparison_price": format(benchmark_price, "f"),
        }
        regional.calculation_status = "CALCULATED"
        regional.calculation_snapshot = calculation_snapshot
        regional.calculated_at = now
        regional.calculated_by_user_id = user.user_id
        comparison.benchmark_comparison_price = benchmark_price
        comparison.calculation_status = "CALCULATED"
        comparison.calculation_snapshot = calculation_snapshot
        comparison.calculated_at = now
        comparison.calculated_by_user_id = user.user_id

        analysis.rule_version_id = rule.rule_version_id
        analysis.benchmark_comparison_price = benchmark_price
        analysis.calculation_snapshot = calculation_snapshot
        analysis.calculated_by_user_id = user.user_id
        analysis.calculated_at = now
        analysis.analysis_status = "READY"
        await self.repository.replace_factor_values(
            selected_ids, factor_value_records
        )
        await self.repository.save_comparison_targets(
            [db_target_by_id[target_id] for target_id in selected_ids]
        )
        await self.repository.save_comparison_analysis(analysis)
        await self.pages._save_data(records["F02-RF"], regional, user)
        await self.pages._save_data(records["F02"], comparison, user)

        return FormalCalculationResponse(
            case_id=case_id,
            report_id=report_id,
            comparison_analysis_id=analysis.comparison_analysis_id,
            rule_version_id=rule.rule_version_id,
            formula_code=rule.formula_code,
            rounding_code=rule.rounding_code,
            benchmark_comparison_price=benchmark_price,
            targets=response_targets,
            input_fingerprint=fingerprint,
            calculated_at=now,
        )

    async def _calculate_without_comparison(
        self,
        *,
        case_id: UUID,
        report_id: UUID,
        case,
        records: dict[str, object],
        regional: F02RFDraftData,
        comparison: F02DraftData,
        user: User,
    ) -> FormalCalculationResponse:
        """Complete the formal-calculation step when comparison is optional.

        The report still uses the published formal rule for auditability, but
        it does not require a benchmark, comparison analysis, targets, or a
        fabricated comparison price.
        """
        regional = await self.pages._ensure_default_formal_rule(
            case, records["F02-RF"], regional, user
        )
        rule = await self.repository.get_rule_version(regional.rule_version_id)
        if rule is None:
            raise AppError(
                "FORMAL_RULE_VERSION_REQUIRED",
                "正式計算前必須套用已發布且可用的正式規則版本",
                422,
            )
        self._validate_rule(case, rule)
        now = datetime.now(UTC)
        input_snapshot = self._input_snapshot(case, regional, comparison, {})
        fingerprint = self._fingerprint(input_snapshot)
        calculation_snapshot = {
            "formula_code": rule.formula_code,
            "rounding_code": rule.rounding_code,
            "rule_version_id": str(rule.rule_version_id),
            "rule_version_no": rule.version_no,
            "comparison_workflow_enabled": False,
            "input_fingerprint": fingerprint,
            "inputs": input_snapshot,
            "targets": [],
            "benchmark_comparison_price": None,
        }
        regional.calculation_status = "CALCULATED"
        regional.calculation_snapshot = calculation_snapshot
        regional.calculated_at = now
        regional.calculated_by_user_id = user.user_id
        comparison.benchmark_comparison_price = None
        comparison.calculation_status = "CALCULATED"
        comparison.calculation_snapshot = calculation_snapshot
        comparison.calculated_at = now
        comparison.calculated_by_user_id = user.user_id
        await self.pages._save_data(records["F02-RF"], regional, user)
        await self.pages._save_data(records["F02"], comparison, user)
        return FormalCalculationResponse(
            case_id=case_id,
            report_id=report_id,
            comparison_analysis_id=None,
            rule_version_id=rule.rule_version_id,
            formula_code=rule.formula_code,
            rounding_code=rule.rounding_code,
            benchmark_comparison_price=None,
            targets=[],
            input_fingerprint=fingerprint,
            calculated_at=now,
        )

    async def validate(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
        request_id: UUID | None,
    ) -> FormalValidationResponse:
        if request_id is not None:
            existing = await self.repository.validation_for_request(
                case_id, report_id, request_id
            )
            if existing is not None:
                return self._validation_response(existing, report_id)
        # Validation creates a run and may transition all report forms to
        # CHECKED; acquire the shared Case writer lock before reading them.
        case, records = await self.pages._read_records(
            case_id, report_id, user, for_update=True
        )
        if request_id is not None:
            existing = await self.repository.validation_for_request(
                case_id, report_id, request_id
            )
            if existing is not None:
                return self._validation_response(existing, report_id)
        regional = self.pages._read_data(records["F02-RF"], F02RFDraftData)
        comparison = self.pages._read_data(records["F02"], F02DraftData)
        s01 = self.pages._read_data(records["S01"], S01DraftData)
        findings: list[FormalValidationFinding] = []

        def error(code: str, message: str, field: str | None = None) -> None:
            # This system exports working Excel templates. Missing or incomplete
            # formal data must remain visible to the second review system, but
            # must not prevent a template with blank cells from being produced.
            findings.append(
                FormalValidationFinding(
                    code=code, severity="WARNING", message=message, field_code=field
                )
            )

        def warning(code: str, message: str, field: str | None = None) -> None:
            findings.append(
                FormalValidationFinding(
                    code=code, severity="WARNING", message=message, field_code=field
                )
            )

        if not s01.district_name or not s01.district_boundary or s01.survey_date is None:
            warning("S01_REQUIRED_FIELDS", "S01 缺少行政區名稱、區段範圍或勘查日期（尚未填寫，暫時留空）")
        if not s01.observations:
            warning("S01_OBSERVATIONS_REQUIRED", "S01 尚未包含勘查因素（暫時留空）")
        elif any(not item.confirmed_by_user for item in s01.observations):
            warning("S01_UNCONFIRMED_OBSERVATION", "S01 含有未經使用者確認的勘查因素")
        if comparison.comparison_workflow_enabled and regional.calculation_status != "CALCULATED":
            warning("F02_RF_CALCULATION_REQUIRED", "F02-RF 尚未完成計算")
        if comparison.comparison_workflow_enabled and comparison.calculation_status != "CALCULATED":
            warning("F02_CALCULATION_REQUIRED", "F02 尚未完成計算")
        if comparison.comparison_workflow_enabled and not comparison.comparison_targets:
            warning("F02_TARGETS_REQUIRED", "F02 缺少比較標的")
        if comparison.comparison_workflow_enabled and not comparison.benchmark_notes:
            warning("F02_BENCHMARK_NOTES_MISSING", "F02 尚未填寫比較價格決定說明")
        if not s01.appraiser_name and not regional.appraiser_name and not comparison.appraiser_name:
            warning("APPRAISER_NAME_MISSING", "查估書尚未填寫不動產估價師")

        documents = await self.pages.draft_map_documents(case_id, report_id, user)
        for document_type in (
            "map-section-sketch",
            "map-zoning",
            "map-land-value-section",
        ):
            document = documents.get(document_type)
            if document is None:
                warning("FORMAL_MAP_MISSING", f"未附正式附圖：{document_type}")
                continue
            if document.mime_type.lower() not in MAP_MIME_TYPES:
                warning("FORMAL_MAP_MIME_INVALID", f"附圖格式不支援：{document_type}")
            if self.storage is None or not await self.storage.object_exists(
                document.object_key
            ):
                warning("FORMAL_MAP_OBJECT_MISSING", f"附圖目前無法讀取：{document_type}")


        fingerprint = None
        input_snapshot = None
        if comparison.comparison_workflow_enabled:
            db_targets = []
            if regional.comparison_analysis_id is not None:
                db_targets = await self.repository.list_comparison_targets(
                    case_id, regional.comparison_analysis_id
                )
            input_snapshot = self._input_snapshot(case, regional, comparison, {
                item.comparison_target_id: item for item in db_targets
            })
            fingerprint = self._fingerprint(input_snapshot)
            saved_fingerprint = comparison.calculation_snapshot.get(
                "input_fingerprint"
            )
            if saved_fingerprint != fingerprint:
                error(
                    "FORMAL_CALCULATION_STALE",
                    "表單或比較標資料已在最後一次計算後變更，請重新計算",
                )
            if regional.comparison_analysis_id is None:
                error("FORMAL_REFERENCES_REQUIRED", "缺少正式比較分析（暫時留空）")
            if regional.rule_version_id is None:
                error("FORMAL_RULE_VERSION_REQUIRED", "缺少正式規則版本（暫時留空）")
            else:
                rule = await self.repository.get_rule_version(regional.rule_version_id)
                if rule is None:
                    error("FORMAL_RULE_VERSION_INVALID", "正式規則版本不存在或未發布")
                else:
                    try:
                        self._validate_rule(case, rule)
                    except AppError as exc:
                        error(exc.code, exc.message)
        else:
            input_snapshot = self._input_snapshot(case, regional, comparison, {})
            fingerprint = self._fingerprint(input_snapshot)
            saved_fingerprint = comparison.calculation_snapshot.get(
                "input_fingerprint"
            )
            if saved_fingerprint != fingerprint:
                error(
                    "FORMAL_CALCULATION_STALE",
                    "表單資料已在最後一次計算後變更，請重新計算",
                )
            if regional.rule_version_id is None:
                error("FORMAL_RULE_VERSION_REQUIRED", "缺少正式規則版本（暫時留空）")
            else:
                rule = await self.repository.get_rule_version(regional.rule_version_id)
                if rule is None:
                    error("FORMAL_RULE_VERSION_INVALID", "正式規則版本不存在或未發布")
                else:
                    try:
                        self._validate_rule(case, rule)
                    except AppError as exc:
                        error(exc.code, exc.message)
        failed_count = sum(item.severity == "ERROR" for item in findings)
        warning_count = sum(item.severity == "WARNING" for item in findings)
        checklist_count = 12
        passed_count = max(
            0,
            checklist_count
            - len({item.code for item in findings if item.severity == "ERROR"}),
        )
        now = datetime.now(UTC)
        snapshot = {
            "ruleset_code": "COMPLETE_REPORT_VALIDATION_V1",
            "input_fingerprint": fingerprint,
            "calculation_fingerprint": comparison.calculation_snapshot.get(
                "input_fingerprint"
            ),
            "findings": [item.model_dump(mode="json") for item in findings],
            "map_document_ids": {
                key: str(value.document_id) for key, value in documents.items()
            },
        }
        run = await self.repository.create_validation_run(
            ValidationRunRecord(
                case_id=case_id,
                form_instance_id=report_id,
                run_status="COMPLETED",
                passed_count=passed_count,
                warning_count=warning_count,
                failed_count=failed_count,
                completed_at=now,
                triggered_by_user_id=user.user_id,
                rule_version_id=regional.rule_version_id,
                input_snapshot=self._validation_input_snapshot(
                    case=case,
                    report_id=report_id,
                    records=records,
                    s01=s01,
                    regional=regional,
                    comparison=comparison,
                    documents=documents,
                    fingerprint=fingerprint,
                ),
                ruleset_snapshot=snapshot,
                request_id=request_id,
            )
        )
        if failed_count == 0:
            for record in records.values():
                record.form_status = FormStatus.CHECKED.value
                record.updated_by_user_id = user.user_id
                await self.repository.save_form(record)
        await self.repository.create_event(
            CaseEventRecord(
                case_id=case_id,
                event_type="COMPLETE_REPORT_VALIDATION_COMPLETED",
                event_data={
                    "report_id": str(report_id),
                    "validation_run_id": str(run.validation_run_id),
                    "failed_count": failed_count,
                    "warning_count": warning_count,
                    "input_fingerprint": fingerprint,
                },
                occurred_by_user_id=user.user_id,
                request_id=request_id,
            )
        )
        return FormalValidationResponse(
            validation_run_id=run.validation_run_id,
            case_id=case_id,
            report_id=report_id,
            passed_count=passed_count,
            warning_count=warning_count,
            failed_count=failed_count,
            can_generate_formal_report=failed_count == 0,
            input_fingerprint=fingerprint,
            findings=findings,
            completed_at=now,
        )

    async def generate(
        self,
        case_id: UUID,
        report_id: UUID,
        acknowledged_warning_codes: set[str],
        user: User,
        request_id: UUID | None,
    ) -> FormalReportResponse:
        if self.storage is None:
            raise RuntimeError("Formal report generation requires storage")
        await self.pages.valuation._owned_editable_case(case_id, user)
        if request_id is not None:
            event = await self.repository.event_for_request(
                case_id, "COMPLETE_REPORT_GENERATED", request_id
            )
            if event is not None:
                document = await self.documents.get(
                    case_id, UUID(event.event_data["document_id"])
                )
                if document is not None:
                    return self._report_response(
                        document,
                        report_id,
                        UUID(event.event_data["validation_run_id"]),
                        request_id,
                    )

        case, records = await self.pages._read_records(case_id, report_id, user)
        validation = await self.repository.latest_report_validation(case_id, report_id)
        if validation is None or validation.failed_count > 0:
            raise AppError(
                "FORMAL_VALIDATION_REQUIRED",
                "必須先完成且通過整份六頁檢核",
                409,
            )
        validation_snapshot = validation.ruleset_snapshot or {}
        warnings = {
            item["code"]
            for item in validation_snapshot.get("findings", [])
            if item.get("severity") == "WARNING"
        }
        if warnings - acknowledged_warning_codes:
            raise AppError(
                "FORMAL_WARNINGS_NOT_ACKNOWLEDGED",
                "正式產出前必須明確確認所有 WARNING",
                422,
                {"unacknowledged_warning_codes": sorted(warnings - acknowledged_warning_codes)},
            )

        data = await self.pages.draft_pdf_data(case_id, report_id, user)
        data = self._merge_location_data_into_pdf(data, await self._template_location_data(case_id))
        regional = self.pages._read_data(records["F02-RF"], F02RFDraftData)
        comparison = self.pages._read_data(records["F02"], F02DraftData)
        if not comparison.comparison_workflow_enabled:
            # Do not leak stale comparison references from an earlier enabled
            # run into a report generated after the section was disabled.
            data["f02"] = dict(data["f02"])
            data["f02"]["benchmark_land_id"] = None
            data["f02"]["comparison_analysis_id"] = None
            data["f02"]["comparison_targets"] = []
            data["f02"]["benchmark_comparison_price"] = None
            data["f02_rf"] = dict(data["f02_rf"])
            data["f02_rf"]["benchmark_land_id"] = None
            data["f02_rf"]["comparison_analysis_id"] = None
        db_targets = []
        if comparison.comparison_workflow_enabled and regional.comparison_analysis_id is not None:
            db_targets = await self.repository.list_comparison_targets(
                case_id, regional.comparison_analysis_id
            )
        current_fingerprint = self._fingerprint(
            self._input_snapshot(
                case,
                regional,
                comparison,
                {item.comparison_target_id: item for item in db_targets},
            )
        )
        if validation_snapshot.get("input_fingerprint") != current_fingerprint:
            raise AppError(
                "FORMAL_VALIDATION_STALE",
                "資料已在最後一次檢核後變更，請重新計算及檢核",
                409,
            )

        map_records = await self.pages.draft_map_documents(case_id, report_id, user)
        expected_map_ids = validation_snapshot.get("map_document_ids") or {}
        current_map_ids = {
            key: str(value.document_id) for key, value in map_records.items()
        }
        if current_map_ids != expected_map_ids:
            raise AppError(
                "FORMAL_VALIDATION_STALE",
                "正式附圖已在最後一次檢核後變更，請重新檢核",
                409,
            )
        map_documents = {}
        for document_type, record in map_records.items():
            response = await self.storage.download(record.object_key)
            content = await run_in_threadpool(_read_and_close, response)
            map_documents[document_type] = {
                "filename": record.original_filename,
                "mime_type": record.mime_type,
                "uploaded_at": record.uploaded_at.isoformat(),
                "content": content,
            }
        official_template_pdf_bytes, official_template_manifest = (
            await _optional_official_template_assets(self.storage)
        )
        report_template_metadata = {"mode": "STRUCTURED_REDRAWN"}
        if official_template_pdf_bytes is not None:
            manifest_for_metadata = official_template_manifest or {}
            report_template_metadata = {
                "mode": "OFFICIAL_BLANK_OVERLAY",
                "template_sha256": sha256(official_template_pdf_bytes).hexdigest(),
                "manifest_version": manifest_for_metadata.get("manifest_version"),
                "template_name": manifest_for_metadata.get("template_name"),
            }
        pdf_bytes = await run_in_threadpool(
            build_pdf_safely,
            build_six_page_formal_pdf,
            data,
            map_documents,
            official_template_pdf_bytes=official_template_pdf_bytes,
            official_template_manifest=official_template_manifest,
        )
        identical_document = await self.documents.get_by_checksum(
            case_id, sha256(pdf_bytes).hexdigest()
        )
        if (
            identical_document is not None
            and identical_document.document_type == "complete-valuation-report"
        ):
            await self._finalize_report_document(
                case_id=case_id,
                report_id=report_id,
                records=records,
                document=identical_document,
                validation_run_id=validation.validation_run_id,
                acknowledged_warning_codes=acknowledged_warning_codes,
                user=user,
                request_id=request_id,
                reused_existing_document=True,
                report_template_metadata=report_template_metadata,
            )
            return self._report_response(
                identical_document,
                report_id,
                validation.validation_run_id,
                request_id,
            )

        existing_output = (
            None
            if records["F02"].output_document_id is None
            else await self.documents.get(
                case_id, records["F02"].output_document_id
            )
        )
        group_id = (
            existing_output.document_group_id if existing_output else uuid4()
        )
        version_no = await self.documents.next_version(case_id, group_id)
        document_id = uuid4()
        filename = safe_filename(
            f"complete_valuation_report_{case.case_no}_v{version_no}.pdf"
        )
        object_key = build_generated_report_object_key(
            case_id, group_id, document_id, version_no, filename
        )
        uploaded = await self.storage.upload(
            object_key,
            BytesIO(pdf_bytes),
            len(pdf_bytes),
            content_type="application/pdf",
        )
        try:
            await self.documents.deactivate_group(case_id, group_id)
            document = await self.documents.create(
                DocumentRecord(
                    document_id=document_id,
                    document_group_id=group_id,
                    case_id=case_id,
                    document_type="complete-valuation-report",
                    original_filename=filename,
                    mime_type="application/pdf",
                    bucket_name=str(uploaded["bucket_name"]),
                    object_key=str(uploaded["object_key"]),
                    checksum_sha256=str(uploaded["checksum_sha256"]),
                    file_size_bytes=int(uploaded["file_size_bytes"]),
                    storage_etag=str(uploaded["etag"]),
                    version_no=version_no,
                    uploaded_by_user_id=user.user_id,
                    is_active=True,
                )
            )
            await self._finalize_report_document(
                case_id=case_id,
                report_id=report_id,
                records=records,
                document=document,
                validation_run_id=validation.validation_run_id,
                acknowledged_warning_codes=acknowledged_warning_codes,
                user=user,
                request_id=request_id,
                report_template_metadata=report_template_metadata,
            )
        except Exception:
            await self.storage.delete(object_key)
            raise
        return self._report_response(
            document, report_id, validation.validation_run_id, request_id
        )

    async def _finalize_report_document(
        self,
        *,
        case_id: UUID,
        report_id: UUID,
        records: dict[str, object],
        document: DocumentRecord,
        validation_run_id: UUID,
        acknowledged_warning_codes: set[str],
        user: User,
        request_id: UUID | None,
        reused_existing_document: bool = False,
        report_template_metadata: dict | None = None,
    ) -> None:
        for record in records.values():
            record.form_status = FormStatus.FINAL.value
            record.output_document_id = document.document_id
            record.updated_by_user_id = user.user_id
            await self.repository.save_form(record)
        await self.repository.create_event(
            CaseEventRecord(
                case_id=case_id,
                event_type="COMPLETE_REPORT_GENERATED",
                event_data={
                    "report_id": str(report_id),
                    "document_id": str(document.document_id),
                    "validation_run_id": str(validation_run_id),
                    "object_key": document.object_key,
                    "version_no": document.version_no,
                    "reused_existing_document": reused_existing_document,
                    "acknowledged_warning_codes": sorted(acknowledged_warning_codes),
                    "report_template": report_template_metadata
                    or {"mode": "STRUCTURED_REDRAWN"},
                },
                occurred_by_user_id=user.user_id,
                request_id=request_id,
            )
        )

    async def get_generated_document(
        self, case_id: UUID, document_id: UUID, user: User
    ) -> DocumentRecord:
        await self.pages.valuation.get_case(case_id, user)
        document = await self.documents.get(case_id, document_id)
        if document is None or document.document_type != "complete-valuation-report":
            raise ResourceNotFoundError("完整六頁查估書 PDF")
        return document


    async def _template_location_data(self, case_id: UUID) -> list[dict[str, object]]:
        """Collect AI-extracted and manual values per active valuation location.

        Manual values override confirmed values, which override pending AI values.  Keeping this separate from the
        formal calculation pages lets working Excel exports preserve blank fields
        and supports any number of uploaded locations.
        """
        locations = list((await self.session.scalars(
            select(ValuationLocationRecord)
            .where(
                ValuationLocationRecord.case_id == case_id,
                ValuationLocationRecord.is_active.is_(True),
            )
            .order_by(ValuationLocationRecord.display_order)
        )).all())
        if not locations:
            return []

        location_by_id = {item.location_id: item for item in locations}
        values_by_location: dict[UUID, dict[str, object]] = {
            item.location_id: {} for item in locations
        }
        parcels = list((await self.session.scalars(
            select(ParcelRecord).where(
                ParcelRecord.case_id == case_id,
                ParcelRecord.location_id.in_(location_by_id),
            )
        )).all())
        for parcel in parcels:
            if parcel.location_id is None:
                continue
            values = values_by_location[parcel.location_id]
            values.setdefault("land_no", parcel.land_no)
            values.setdefault("section_name", parcel.section_name)
            values.setdefault("subsection_name", parcel.subsection_name)
            values.setdefault("area_sqm", parcel.area_sqm)
            values.setdefault("land_use_zone", parcel.land_use_zone)
            values.setdefault("designated_use", parcel.designated_use)

        aliases = {
            "administrative_area": "district_name",
            "zone_boundary_description": "district_boundary",
            "urban_plan_scope": "urban_plan_status",
            "land_use_zone_category": "land_use_zone",
            "building_coverage_ratio": "building_coverage_rate",
            "building_prohibition_status": "prohibited_building",
            "building_restriction_status": "restricted_building",
            "building_restriction_details": "restricted_building",
            "internal_road_width_m": "average_road_width_m",
            "average_internal_road_width_m": "average_road_width_m",
            "section_chief_name": "section_head_name",
        }
        candidates = list((await self.session.scalars(
            select(ExtractedFieldRecord)
            .where(
                ExtractedFieldRecord.case_id == case_id,
                ExtractedFieldRecord.location_id.in_(location_by_id),
                ExtractedFieldRecord.field_status.in_(("CONFIRMED", "APPLIED")),
                ExtractedFieldRecord.confirmed_value.is_not(None),
            )
            .order_by(
                ExtractedFieldRecord.updated_at.desc(),
                ExtractedFieldRecord.created_at.desc(),
            )
        )).all())
        candidate_priorities: dict[tuple[UUID, str], int] = {}
        for candidate in candidates:
            if candidate.location_id is None:
                continue
            field = aliases.get(str(candidate.field_name), str(candidate.field_name))
            priority = 2 if candidate.field_status in {"CONFIRMED", "APPLIED"} else 1
            key = (candidate.location_id, field)
            if candidate_priorities.get(key, 0) >= priority:
                continue
            value = candidate.confirmed_value if candidate.confirmed_value is not None else candidate.extracted_value
            if value in (None, ""):
                continue
            values_by_location[candidate.location_id][field] = value
            candidate_priorities[key] = priority

        forms = list((await self.session.scalars(
            select(FormInstanceRecord).where(FormInstanceRecord.case_id == case_id)
        )).all())
        for form in forms:
            content = form.form_content if isinstance(form.form_content, dict) else {}
            scoped = content.get("manual_overrides_by_location")
            if not isinstance(scoped, dict):
                continue
            for raw_location_id, raw_values in scoped.items():
                try:
                    location_id = UUID(str(raw_location_id))
                except (TypeError, ValueError):
                    continue
                if location_id not in values_by_location or not isinstance(raw_values, dict):
                    continue
                values = values_by_location[location_id]
                for field, value in raw_values.items():
                    if value not in (None, ""):
                        values[aliases.get(str(field), str(field))] = value

        return [
            {
                "location_id": str(item.location_id),
                "display_order": item.display_order,
                "label": item.label,
                "address": item.address,
                "is_benchmark_location": item.is_benchmark_location,
                "values": values_by_location[item.location_id],
            }
            for item in locations
        ]

    async def _template_f03_data(
        self,
        case_id: UUID,
        s01: dict[str, object],
        locations: list[dict[str, object]],
    ) -> dict[str, object]:
        """Build Table 14 rows from canonical F03/benchmark records.

        Table 14 has room for five benchmark rows.  Do not silently truncate
        additional benchmark valuations because that would make the official
        export incomplete.
        """

        valuations = list((await self.session.scalars(
            select(BenchmarkValuationRecord)
            .where(BenchmarkValuationRecord.case_id == case_id)
            .order_by(
                BenchmarkValuationRecord.updated_at.desc(),
                BenchmarkValuationRecord.version_no.desc(),
                BenchmarkValuationRecord.benchmark_valuation_id,
            )
        )).all())
        latest_by_benchmark: dict[UUID, BenchmarkValuationRecord] = {}
        for valuation in valuations:
            latest_by_benchmark.setdefault(valuation.benchmark_land_id, valuation)
        latest = list(latest_by_benchmark.values())

        benchmark_ids = {item.benchmark_land_id for item in latest}
        benchmarks = list((await self.session.scalars(
            select(BenchmarkLandRecord).where(
                BenchmarkLandRecord.case_id == case_id,
                BenchmarkLandRecord.benchmark_land_id.in_(benchmark_ids),
                BenchmarkLandRecord.is_active.is_(True),
            )
        )).all()) if benchmark_ids else []
        benchmark_by_id = {item.benchmark_land_id: item for item in benchmarks}
        latest = [item for item in latest if item.benchmark_land_id in benchmark_by_id]
        if len(latest) > 5:
            raise AppError(
                "F03_TEMPLATE_MAX_ROWS",
                "表14正式範本最多可列5筆比準地；目前案件超過範本容量",
                422,
                {"benchmark_count": len(latest), "template_capacity": 5},
            )

        parcel_ids = {item.parcel_id for item in benchmarks}
        parcels = list((await self.session.scalars(
            select(ParcelRecord).where(
                ParcelRecord.case_id == case_id,
                ParcelRecord.parcel_id.in_(parcel_ids),
            )
        )).all()) if parcel_ids else []
        parcel_by_id = {item.parcel_id: item for item in parcels}
        location_by_id = {
            str(item.get("location_id")): item for item in locations
            if item.get("location_id") is not None
        }

        rows: list[dict[str, object]] = []
        for valuation in sorted(
            latest,
            key=lambda item: (
                benchmark_by_id.get(item.benchmark_land_id).benchmark_land_no
                if benchmark_by_id.get(item.benchmark_land_id) is not None
                else str(item.benchmark_land_id)
            ),
        ):
            benchmark = benchmark_by_id.get(valuation.benchmark_land_id)
            parcel = None if benchmark is None else parcel_by_id.get(benchmark.parcel_id)
            location = (
                None
                if parcel is None or parcel.location_id is None
                else location_by_id.get(str(parcel.location_id))
            )
            values = (
                dict(location.get("values") or {})
                if isinstance(location, dict)
                else {}
            )
            section_subsection = ""
            if parcel is not None:
                section_subsection = "".join(
                    part for part in (parcel.section_name, parcel.subsection_name or "") if part
                )
            rows.append({
                "price_zone_no": None if benchmark is None else benchmark.price_zone_no,
                "benchmark_land_no": (
                    None
                    if benchmark is None
                    else benchmark.land_consolidation_serial or benchmark.benchmark_land_no
                ),
                "district_name": (
                    values.get("district_name")
                    if values.get("district_name") not in (None, "")
                    else (None if parcel is None else parcel.district_code)
                ),
                "section_subsection_name": section_subsection or None,
                "land_no": None if parcel is None else parcel.land_no,
                "comparison_price": valuation.comparison_price,
                "comparison_weight": valuation.comparison_weight,
                "income_price": valuation.income_price,
                "income_weight": valuation.income_weight,
                "benchmark_land_price": valuation.benchmark_land_price,
                "decision_reason": valuation.decision_reason,
            })

        return {
            "rows": rows,
            "footer": {
                # F03 relational storage does not currently own these signature
                # fields.  Reuse only explicit case-level S01 signatories; do
                # not invent a filled date.
                "filled_date": None,
                "handler_name": s01.get("handler_name"),
                "section_head_name": s01.get("section_head_name"),
                "director_name": s01.get("director_name"),
                "appraiser_name": s01.get("appraiser_name"),
            },
        }

    async def _template_f04_data(
        self,
        case_id: UUID,
        locations: list[dict[str, object]],
    ) -> dict[str, object] | None:
        """Build Table 6 data from the latest canonical F04 draft."""

        form = await self.session.scalar(
            select(FormInstanceRecord)
            .where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_code == "F04",
            )
            .order_by(
                FormInstanceRecord.version_no.desc(),
                FormInstanceRecord.updated_at.desc(),
                FormInstanceRecord.form_instance_id,
            )
            .limit(1)
        )
        if form is None:
            return None
        content = form.form_content if isinstance(form.form_content, dict) else {}
        try:
            data = F04DraftData.model_validate(content.get("data") or {})
        except ValueError as exc:
            raise AppError(
                "F04_FORM_CONTENT_INVALID",
                "表6資料不符合目前正式Schema，請先修正F04資料",
                409,
            ) from exc
        if len(data.parcel_rows) > 5:
            raise AppError(
                "F04_TEMPLATE_MAX_PARCELS",
                "表6正式範本最多可列5筆宗地；目前案件超過範本容量",
                422,
                {"parcel_count": len(data.parcel_rows), "template_capacity": 5},
            )

        benchmark_valuation = None
        benchmark = None
        benchmark_parcel = None
        if data.benchmark_valuation_id is not None:
            benchmark_valuation = await self.session.scalar(
                select(BenchmarkValuationRecord).where(
                    BenchmarkValuationRecord.case_id == case_id,
                    BenchmarkValuationRecord.benchmark_valuation_id
                    == data.benchmark_valuation_id,
                )
            )
        if benchmark_valuation is not None:
            benchmark = await self.session.scalar(
                select(BenchmarkLandRecord).where(
                    BenchmarkLandRecord.case_id == case_id,
                    BenchmarkLandRecord.benchmark_land_id
                    == benchmark_valuation.benchmark_land_id,
                )
            )
        if benchmark is not None:
            benchmark_parcel = await self.session.scalar(
                select(ParcelRecord).where(
                    ParcelRecord.case_id == case_id,
                    ParcelRecord.parcel_id == benchmark.parcel_id,
                )
            )

        parcel_ids = {item.parcel_id for item in data.parcel_rows}
        parcel_records = list((await self.session.scalars(
            select(ParcelRecord).where(
                ParcelRecord.case_id == case_id,
                ParcelRecord.parcel_id.in_(parcel_ids),
            )
        )).all()) if parcel_ids else []
        parcel_by_id = {item.parcel_id: item for item in parcel_records}

        def parcel_display(parcel: ParcelRecord | None) -> str | None:
            if parcel is None:
                return None
            section = "".join(
                part for part in (parcel.section_name, parcel.subsection_name or "") if part
            )
            return f"{section} {parcel.land_no}地號".strip()

        exported_rows: list[dict[str, object]] = []
        for index, row in enumerate(data.parcel_rows, start=1):
            payload = row.model_dump(mode="json")
            payload["parcel_serial"] = index
            payload["parcel_display"] = parcel_display(parcel_by_id.get(row.parcel_id))
            exported_rows.append(payload)

        return {
            **data.model_dump(mode="json"),
            "benchmark": {
                "benchmark_land_no": (
                    None
                    if benchmark is None
                    else benchmark.land_consolidation_serial or benchmark.benchmark_land_no
                ),
                "parcel_display": parcel_display(benchmark_parcel),
            },
            "parcel_rows": exported_rows,
            "footer": {
                "filled_date": data.filled_date,
                "handler_name": data.handler_name,
                "section_head_name": data.section_head_name,
                "director_name": data.director_name,
                "appraiser_name": data.appraiser_name,
            },
        }

    @staticmethod
    def _merge_location_data_into_pdf(
        data: dict, locations: list[dict[str, object]]
    ) -> dict:
        """Use the same per-location values as Excel when building the PDF."""
        if not locations:
            return data
        merged = deepcopy(data)

        def values(location: dict[str, object] | None) -> dict[str, object]:
            raw = {} if location is None else location.get("values")
            return dict(raw) if isinstance(raw, dict) else {}

        def value(location: dict[str, object] | None, field: str, fallback=None):
            current = values(location).get(field)
            return fallback if current in (None, "", []) else current

        def label(location: dict[str, object] | None) -> str:
            if location is None:
                return ""
            return str(location.get("label") or location.get("address") or "")

        benchmark = next(
            (item for item in locations if item.get("is_benchmark_location")),
            locations[0],
        )
        targets = [item for item in locations if item is not benchmark][:3]
        benchmark_id = str(benchmark.get("location_id"))

        context = dict(merged.get("context") or {})
        context["benchmark_lands"] = [
            {
                "benchmark_land_id": str(item.get("location_id")),
                "parcel_id": str(item.get("location_id")),
                "benchmark_land_no": label(item),
                "price_zone_no": value(item, "price_zone_no"),
            }
            for item in locations
        ]
        merged["context"] = context

        s01 = dict(merged.get("s01") or {})
        for field in (
            "district_name", "district_boundary", "survey_date", "urban_plan_status",
            "land_use_zone", "building_coverage_rate", "floor_area_ratio",
            "prohibited_building", "restricted_building", "main_road_name",
            "main_road_width_m", "average_road_width_m", "handler_name",
            "section_head_name", "director_name", "appraiser_name",
        ):
            current = value(benchmark, field)
            if current not in (None, "", []):
                if field in {"building_coverage_rate", "floor_area_ratio"}:
                    current = str(current).removesuffix("%")
                s01[field] = current
        observations = {
            str(item.get("item_code")): dict(item)
            for item in s01.get("observations") or []
        }
        for code in TEMPLATE_FACTOR_CODES:
            current = value(benchmark, code)
            if current not in (None, "", []):
                observations[code] = {
                    "item_code": code,
                    "raw_value": str(current),
                    "source_notes": "地點 AI／人工確認值",
                }
        s01["observations"] = list(observations.values())
        merged["s01"] = s01

        regional = dict(merged.get("f02_rf") or {})
        regional["benchmark_land_id"] = benchmark_id
        old_rows = {
            str(item.get("factor_code")): dict(item)
            for item in regional.get("factor_rows") or []
        }
        factor_rows = []
        for code in TEMPLATE_FACTOR_CODES:
            row = deepcopy(old_rows.get(code, {"factor_code": code, "targets": []}))
            row["factor_code"] = code
            benchmark_value = value(benchmark, code)
            if benchmark_value not in (None, "", []):
                row["benchmark_confirmed_level"] = str(benchmark_value)
                row["benchmark_reported_level"] = str(benchmark_value)
            old_targets = list(row.get("targets") or [])
            new_targets = []
            for index, target in enumerate(targets, start=1):
                item = deepcopy(old_targets[index - 1] if index <= len(old_targets) else {})
                item["comparison_target_id"] = str(target.get("location_id"))
                item["display_order"] = index
                target_value = value(target, code)
                if target_value not in (None, "", []):
                    item["confirmed_level"] = str(target_value)
                    item["reported_level"] = str(target_value)
                new_targets.append(item)
            row["targets"] = new_targets
            if benchmark_value not in (None, "", []) or new_targets or code in old_rows:
                factor_rows.append(row)
        regional["factor_rows"] = factor_rows
        merged["f02_rf"] = regional

        comparison = dict(merged.get("f02") or {})
        comparison["benchmark_land_id"] = benchmark_id
        benchmark_price = value(benchmark, "benchmark_comparison_price", value(benchmark, "comparison_price"))
        if benchmark_price not in (None, "", []):
            comparison["benchmark_comparison_price"] = benchmark_price
        old_targets = sorted(
            list(comparison.get("comparison_targets") or []),
            key=lambda item: item.get("display_order", 0),
        )
        comparison_targets = []
        for index, target in enumerate(targets, start=1):
            item = deepcopy(old_targets[index - 1] if index <= len(old_targets) else {})
            item["comparison_target_id"] = str(target.get("location_id"))
            item["comparison_target_label"] = label(target)
            item["display_order"] = index
            for field, destination in (
                ("transaction_date", "transaction_date_snapshot"),
                ("normal_unit_price", "normal_unit_price_snapshot"),
                ("time_adjustment_rate", "time_adjustment_rate"),
                ("regional_adjustment_rate", "regional_adjustment_rate"),
                ("individual_adjustment_rate", "individual_adjustment_rate"),
                ("total_adjustment_absolute", "total_adjustment_absolute"),
                ("trial_price", "trial_price"),
                ("weight", "weight"),
            ):
                current = value(target, field)
                if current not in (None, "", []):
                    item[destination] = current
            old_factors = {
                str(factor.get("factor_code")): dict(factor)
                for factor in item.get("individual_factors") or []
            }
            individual_factors = []
            for code in INDIVIDUAL_FACTOR_CODES:
                factor = old_factors.get(code, {"factor_code": code})
                current = value(target, code)
                if current not in (None, "", []):
                    factor["comparable_confirmed_level"] = str(current)
                    factor["comparable_reported_level"] = str(current)
                if current not in (None, "", []) or code in old_factors:
                    individual_factors.append(factor)
            item["individual_factors"] = individual_factors
            comparison_targets.append(item)
        comparison["comparison_targets"] = comparison_targets
        merged["f02"] = comparison
        return merged
    async def generate_template_exports(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
    ) -> list[TemplateExportResponse]:
        if self.storage is None:
            raise RuntimeError("Template export requires storage")
        case, records = await self.pages._read_records(case_id, report_id, user)
        pages = {
            code: self.pages._read_data(records[code], model).model_dump(mode="json")
            for code, model in (
                ("S01", S01DraftData),
                ("F02-RF", F02RFDraftData),
                ("F02", F02DraftData),
            )
        }
        regional_data = self.pages._read_data(records["F02-RF"], F02RFDraftData)
        if regional_data.rule_version_id is not None:
            land_use = LAND_USE_ALIASES.get(
                str(case.land_use_type or "").strip(),
                str(case.land_use_type or "").strip().upper(),
            )
            level_rows = await self.repository.list_factor_levels(
                regional_data.rule_version_id,
                land_use,
                set(TEMPLATE_FACTOR_CODES),
            )
            level_lookup: dict[str, dict[str, dict[str, object]]] = {}
            for definition, level in level_rows:
                payload = {
                    "level_code": level.level_code,
                    "level_name": level.level_name,
                    "sort_order": level.sort_order,
                }
                factor_lookup = level_lookup.setdefault(definition.factor_code, {})
                factor_lookup[str(level.level_code)] = payload
                factor_lookup[str(level.level_name)] = payload
            pages["F02-RF"]["level_lookup"] = level_lookup

        locations = await self._template_location_data(case_id)
        pages["F03"] = await self._template_f03_data(case_id, pages["S01"], locations)
        f04 = await self._template_f04_data(case_id, locations)
        if f04 is not None:
            pages["F04"] = f04
        case_data = {
            "case_no": case.case_no,
            "case_title": case.case_title,
            "valuation_base_date": case.valuation_base_date,
            "land_use_type": LAND_USE_ALIASES.get(
                str(case.land_use_type or "").strip(),
                str(case.land_use_type or "").strip().upper(),
            ),
        }
        jobs: list[tuple[object, dict[str, object] | None]] = []
        s01_definition = next(item for item in TEMPLATE_EXPORTS if item.code == "S01")
        if locations:
            jobs.extend((s01_definition, location) for location in locations)
        else:
            jobs.append((s01_definition, None))
        jobs.extend(
            (definition, None)
            for definition in TEMPLATE_EXPORTS
            if definition.code != "S01" and definition.code in pages
        )

        repository = DocumentRepository(self.session)
        results: list[TemplateExportResponse] = []
        for definition, location in jobs:
            location_id = None if location is None else UUID(str(location["location_id"]))
            location_label = None if location is None else str(location["label"])
            scope_key = "combined" if location is None else str(location["location_id"])
            try:
                content = await run_in_threadpool(
                    build_template_export_xlsx,
                    code=definition.code,
                    case=case_data,
                    pages=pages,
                    locations=locations if definition.code != "S01" else None,
                    location=location,
                )
            except FileNotFoundError as exc:
                raise AppError(
                    "OFFICIAL_EXCEL_TEMPLATE_MISSING",
                    str(exc),
                    409,
                    {
                        "form_code": definition.code,
                        "land_use_type": case_data["land_use_type"],
                    },
                ) from exc
            group_id = uuid5(
                NAMESPACE_URL,
                f"land-valuation:{case_id}:report:{report_id}:template:{definition.code}:{scope_key}",
            )
            version_no = await repository.next_version(case_id, group_id)
            document_id = uuid4()
            suffix = "combined" if location is None else f"location-{location['display_order']}"
            output_filename = definition.output_filename
            output_title = definition.title
            filename = safe_filename(
                f"{case.case_no}_{definition.code}_{suffix}_{output_filename}"
            )
            object_key = build_generated_report_object_key(
                case_id, group_id, document_id, version_no, filename
            )
            uploaded = await self.storage.upload(
                object_key,
                BytesIO(content),
                len(content),
                content_type=EXCEL_MIME,
            )
            try:
                await repository.deactivate_group(case_id, group_id)
                document = await repository.create(
                    DocumentRecord(
                        document_id=document_id,
                        document_group_id=group_id,
                        case_id=case_id,
                        location_id=location_id,
                        document_type="generated-template-xlsx",
                        original_filename=filename,
                        mime_type=EXCEL_MIME,
                        bucket_name=str(uploaded["bucket_name"]),
                        object_key=str(uploaded["object_key"]),
                        checksum_sha256=sha256(content).hexdigest(),
                        file_size_bytes=len(content),
                        storage_etag=str(uploaded["etag"]),
                        version_no=version_no,
                        uploaded_by_user_id=user.user_id,
                        is_active=True,
                    )
                )
            except Exception:
                await self.storage.delete(object_key)
                raise
            title = output_title if location is None else f"{output_title}（{location_label}）"
            results.append(
                TemplateExportResponse(
                    form_code=definition.code,
                    title=title,
                    location_id=location_id,
                    location_label=location_label,
                    document_id=document.document_id,
                    filename=document.original_filename,
                    mime_type=document.mime_type,
                    version_no=document.version_no,
                    file_size_bytes=document.file_size_bytes,
                    download_path=(
                        f"/api/v1/valuation/cases/{case_id}/documents/"
                        f"{document.document_id}/download"
                    ),
                )
            )
        return results
    async def _existing_template_exports(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> list[TemplateExportResponse]:
        documents = await self.documents.list_active_for_case(case_id)
        locations = await self._template_location_data(case_id)
        s01_definition = next(item for item in TEMPLATE_EXPORTS if item.code == "S01")
        jobs: list[tuple[object, dict[str, object] | None]] = []
        if locations:
            jobs.extend((s01_definition, location) for location in locations)
        else:
            jobs.append((s01_definition, None))
        jobs.extend(
            (definition, None)
            for definition in TEMPLATE_EXPORTS
            if definition.code != "S01"
        )
        results: list[TemplateExportResponse] = []
        for definition, location in jobs:
            scope_key = "combined" if location is None else str(location["location_id"])
            group_id = uuid5(
                NAMESPACE_URL,
                f"land-valuation:{case_id}:report:{report_id}:template:{definition.code}:{scope_key}",
            )
            document = next(
                (
                    item for item in documents
                    if item.document_type == "generated-template-xlsx"
                    and item.is_active
                    and item.document_group_id == group_id
                ),
                None,
            )
            if document is None:
                continue
            location_id = None if location is None else UUID(str(location["location_id"]))
            location_label = None if location is None else str(location["label"])
            results.append(
                TemplateExportResponse(
                    form_code=definition.code,
                    title=(definition.title if location is None else f"{definition.title}（{location_label}）"),
                    location_id=location_id,
                    location_label=location_label,
                    document_id=document.document_id,
                    filename=document.original_filename,
                    mime_type=document.mime_type,
                    version_no=document.version_no,
                    file_size_bytes=document.file_size_bytes,
                    download_path=(
                        f"/api/v1/valuation/cases/{case_id}/documents/"
                        f"{document.document_id}/download"
                    ),
                )
            )
        return results
    async def export_xlsx(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> tuple[bytes, str]:
        """Export finalized structured report data as a readable workbook."""
        case, records = await self.pages._read_records(case_id, report_id, user)
        f02 = records["F02"]
        if f02.form_status != FormStatus.FINAL.value or f02.output_document_id is None:
            raise AppError(
                "FORMAL_REPORT_REQUIRED",
                "??????????????? PDF???????? Excel",
                409,
            )
        document = await self.documents.get(case_id, f02.output_document_id)
        if (
            document is None
            or not document.is_active
            or document.document_type != "complete-valuation-report"
        ):
            raise AppError(
                "FORMAL_REPORT_REQUIRED",
                "??????????? PDF??????????? Excel",
                409,
            )
        data = await self.pages.draft_pdf_data(case_id, report_id, user)
        xlsx_bytes = await run_in_threadpool(build_formal_report_xlsx, data)
        filename = safe_filename(f"valuation_data_{case.case_no}_v{f02.version_no}.xlsx")
        return xlsx_bytes, filename

    async def status(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> FormalWorkflowStatusResponse:
        _, records = await self.pages._read_records(case_id, report_id, user)
        validation = await self.repository.latest_report_validation(case_id, report_id)
        validation_response = (
            None
            if validation is None
            else self._validation_response(validation, report_id)
        )
        document = None
        output_document_id = records["F02"].output_document_id
        if output_document_id is not None:
            candidate = await self.documents.get(case_id, output_document_id)
            if (
                candidate is not None
                and candidate.is_active
                and candidate.document_type == "complete-valuation-report"
            ):
                document = candidate
        report = (
            None
            if document is None or validation is None
            else self._report_response(
                document, report_id, validation.validation_run_id, None
            )
        )
        return FormalWorkflowStatusResponse(
            validation=validation_response,
            report=report,
            template_exports=await self._existing_template_exports(case_id, report_id, user),
            requires_revalidation_for_submission=(
                validation is not None
                and not bool(validation.input_snapshot)
            ),
        )

    async def _formal_rule_and_levels(self, case, rule_version_id, factor_codes):
        rule = await self.repository.get_rule_version(rule_version_id)
        if rule is None:
            raise AppError(
                "FORMAL_RULE_VERSION_INVALID",
                "規則版本不存在或尚未發布",
                422,
            )
        land_use = self._validate_rule(case, rule)
        rows = await self.repository.list_factor_levels(
            rule.rule_version_id, land_use, set(factor_codes)
        )
        level_lookup: dict[str, list[LevelValue]] = {}
        for definition, level in rows:
            level_lookup.setdefault(definition.factor_code, []).append(
                LevelValue(
                    factor_definition_id=definition.factor_definition_id,
                    factor_level_id=level.factor_level_id,
                    factor_code=definition.factor_code,
                    level_code=level.level_code,
                    level_name=level.level_name,
                    suggested_rate=level.suggested_rate,
                    maximum_impact_rate=level.maximum_impact_rate,
                )
            )
        missing = sorted(set(factor_codes) - set(level_lookup))
        if missing:
            raise AppError(
                "FORMAL_RULE_LEVELS_INCOMPLETE",
                "正式規則版本缺少本查估書所需因素級距",
                409,
                {"missing_factor_codes": missing},
            )
        for factor_code, levels in level_lookup.items():
            if len(levels) < 2:
                raise AppError(
                    "FORMAL_RULE_LEVELS_INCOMPLETE",
                    f"正式因素 {factor_code} 至少需要兩個級距",
                    409,
                )
            bounds = {item.maximum_impact_rate for item in levels}
            if len(bounds) != 1:
                raise AppError(
                    "RULE_FACTOR_BOUND_INCONSISTENT",
                    f"正式因素 {factor_code} 的最大影響範圍不一致",
                    409,
                )
            scores = [item.suggested_rate for item in levels]
            if max(scores) - min(scores) > next(iter(bounds)):
                raise AppError(
                    "RULE_FACTOR_SPAN_OUT_OF_RANGE",
                    f"正式因素 {factor_code} 的級距修正跨度超出最大影響範圍",
                    409,
                )
        return rule, level_lookup

    @staticmethod
    def _validate_rule(case, rule) -> str:
        if (
            rule.status != "PUBLISHED"
            or rule.import_status != "VERIFIED"
            or rule.verified_at is None
            or rule.source_document_id is None
            or not rule.source_checksum_sha256
        ):
            raise AppError(
                "FORMAL_RULE_AUDIT_FAILED",
                "規則版本尚未完成來源、匯入及人工發布稽核",
                409,
            )
        if rule.formula_code != FORMAL_FORMULA_CODE:
            raise AppError("FORMAL_FORMULA_INVALID", "規則版本公式代碼不支援", 409)
        if rule.rounding_code != FORMAL_ROUNDING_CODE:
            raise AppError("FORMAL_ROUNDING_INVALID", "規則版本尾數規則不支援", 409)
        if (
            rule.effective_from is None
            or rule.effective_from > case.valuation_base_date
            or (
                rule.effective_to is not None
                and rule.effective_to < case.valuation_base_date
            )
        ):
            raise AppError(
                "FORMAL_RULE_DATE_NOT_APPLICABLE",
                "規則版本不適用案件估價基準日",
                409,
            )
        land_use = LAND_USE_ALIASES.get(
            str(case.land_use_type or "").strip(),
            str(case.land_use_type or "").strip().upper(),
        )
        if land_use != "COMMERCIAL":
            raise AppError(
                "FORMAL_REPORT_TEMPLATE_LAND_USE_UNSUPPORTED",
                "目前正式六頁版型為商業用地查估書；其他用途須使用對應正式版型，不得誤套",
                409,
            )
        if land_use not in set(rule.land_use_types or []):
            raise AppError(
                "FORMAL_RULE_LAND_USE_NOT_APPLICABLE",
                "規則版本不適用案件土地用途",
                409,
            )
        if case.district_code not in NEW_TAIPEI_DISTRICT_CODES:
            raise AppError(
                "FORMAL_RULE_DISTRICT_NOT_APPLICABLE",
                "案件行政區不在新北市 29 區範圍",
                409,
            )
        if rule.district_scope != NEW_TAIPEI_CITYWIDE_SCOPE:
            raise AppError(
                "FORMAL_RULE_SCOPE_NOT_CITYWIDE",
                "正式六頁產出只接受已確認適用新北市 29 區的全市共同規則",
                409,
            )
        return land_use

    @staticmethod
    def _validation_response(
        run: ValidationRunRecord, report_id: UUID
    ) -> FormalValidationResponse:
        snapshot = run.ruleset_snapshot or {}
        findings = [
            FormalValidationFinding.model_validate(item)
            for item in snapshot.get("findings", [])
        ]
        return FormalValidationResponse(
            validation_run_id=run.validation_run_id,
            case_id=run.case_id,
            report_id=report_id,
            passed_count=run.passed_count,
            warning_count=run.warning_count,
            failed_count=run.failed_count,
            can_generate_formal_report=run.failed_count == 0,
            input_fingerprint=snapshot.get("input_fingerprint"),
            findings=findings,
            completed_at=run.completed_at,
        )

    @staticmethod
    def _validation_input_snapshot(
        *,
        case,
        report_id: UUID,
        records: dict[str, object],
        s01: S01DraftData,
        regional: F02RFDraftData,
        comparison: F02DraftData,
        documents: dict[str, DocumentRecord],
        fingerprint: str | None,
    ) -> dict:
        """Freeze all inputs used by a formal validation before review handoff."""
        form_data = {
            "S01": s01.model_dump(mode="json"),
            "F02-RF": regional.model_dump(mode="json"),
            "F02": comparison.model_dump(mode="json"),
        }
        form_versions = {
            code: {
                "form_instance_id": str(record.form_instance_id),
                "version_no": record.version_no,
                "form_status": record.form_status,
            }
            for code, record in records.items()
        }
        map_documents = {
            document_type: {
                "document_id": str(document.document_id),
                "document_group_id": str(document.document_group_id),
                "version_no": document.version_no,
                "checksum_sha256": document.checksum_sha256,
                "original_filename": document.original_filename,
                "mime_type": document.mime_type,
            }
            for document_type, document in documents.items()
        }
        return {
            "schema_version": "complete-report-validation-input-v1",
            "case_version": records["F02"].version_no,
            "case": {
                "case_id": str(case.case_id),
                "case_no": case.case_no,
                "case_title": case.case_title,
                "case_type": case.case_type,
                "valuation_base_date": case.valuation_base_date.isoformat(),
                "city_code": case.city_code,
                "district_code": case.district_code,
                "land_use_type": case.land_use_type,
            },
            "report": {
                "report_id": str(report_id),
                "forms": form_versions,
                "data": form_data,
            },
            "formal_calculation": comparison.calculation_snapshot,
            "map_documents": map_documents,
            "input_fingerprint": fingerprint,
        }

    @staticmethod
    def _resolve_level(level_lookup, factor_code: str, supplied: str) -> LevelValue:
        matches = [
            item
            for item in level_lookup.get(factor_code, [])
            if supplied in {item.level_code, item.level_name}
        ]
        if len(matches) != 1:
            raise AppError(
                "FORMAL_FACTOR_LEVEL_INVALID",
                f"因素 {factor_code} 的確認等級不存在或不唯一：{supplied}",
                422,
            )
        return matches[0]

    @staticmethod
    def _dummy_level(factor_code: str) -> LevelValue:
        return LevelValue(
            factor_definition_id=uuid4(),
            factor_level_id=uuid4(),
            factor_code=factor_code,
            level_code="NONE",
            level_name="未選擇",
            suggested_rate=Decimal("0"),
            maximum_impact_rate=Decimal("0"),
        )

    @staticmethod
    def _factor_value_record(

        target_id: UUID,
        adjustment: FactorAdjustment,
        reason: str | None,
    ) -> ComparisonFactorValueRecord:
        return ComparisonFactorValueRecord(
            comparison_target_id=target_id,
            factor_definition_id=adjustment.benchmark.factor_definition_id,
            factor_level_id=adjustment.comparable.factor_level_id,
            benchmark_factor_level_id=adjustment.benchmark.factor_level_id,
            comparable_factor_level_id=adjustment.comparable.factor_level_id,
            benchmark_text=adjustment.benchmark.level_name,
            comparable_text=adjustment.comparable.level_name,
            suggested_rate=adjustment.adjustment_rate,
            adopted_rate=adjustment.adjustment_rate,
            adjustment_reason=reason,
        )

    @staticmethod
    def _input_snapshot(case, regional, comparison, db_target_by_id) -> dict:
        return {
            "case": {
                "case_id": str(case.case_id),
                "valuation_base_date": case.valuation_base_date.isoformat(),
                "district_code": case.district_code,
                "land_use_type": case.land_use_type,
            },
            "rule_version_id": (
                None
                if regional.rule_version_id is None
                else str(regional.rule_version_id)
            ),
            "benchmark_land_id": (
                None
                if regional.benchmark_land_id is None
                else str(regional.benchmark_land_id)
            ),
            "comparison_analysis_id": (
                None
                if regional.comparison_analysis_id is None
                else str(regional.comparison_analysis_id)
            ),
            "regional_factors": [
                {
                    "factor_code": row.factor_code,
                    "benchmark_level": row.benchmark_confirmed_level,
                    "confirmed": row.confirmed_by_user,
                    "source_notes": row.source_notes,
                    "targets": [
                        {
                            "comparison_target_id": str(item.comparison_target_id),
                            "level": item.confirmed_level,
                            "confirmed": item.confirmed_by_user,
                            "source_notes": item.source_notes,
                        }
                        for item in sorted(
                            row.targets, key=lambda target: target.display_order
                        )
                    ],
                }
                for row in sorted(
                    regional.factor_rows, key=lambda factor: factor.factor_code
                )
            ],
            "comparison_targets": [
                {
                    "comparison_target_id": str(item.comparison_target_id),
                    "display_order": item.display_order,
                    "normal_unit_price_snapshot": (
                        None
                        if item.comparison_target_id not in db_target_by_id
                        else format(
                            db_target_by_id[
                                item.comparison_target_id
                            ].normal_unit_price_snapshot,
                            "f",
                        )
                    ),
                    "transaction_date_snapshot": (
                        None
                        if item.comparison_target_id not in db_target_by_id
                        else db_target_by_id[
                            item.comparison_target_id
                        ].transaction_date_snapshot.isoformat()
                    ),
                    "time_adjustment_rate": format(
                        item.time_adjustment_rate, "f"
                    ),
                    "time_adjustment_confirmed": item.time_adjustment_confirmed_by_user,
                    "time_adjustment_source_notes": item.time_adjustment_source_notes,
                    "weight": None if item.weight is None else format(item.weight, "f"),
                    "weight_confirmed": item.weight_confirmed_by_user,
                    "weight_reason": item.weight_reason,
                    "individual_factors": [
                        {
                            "factor_code": factor.factor_code,
                            "benchmark_level": factor.benchmark_confirmed_level,
                            "comparable_level": factor.comparable_confirmed_level,
                            "confirmed": factor.confirmed_by_user,
                            "source_notes": factor.source_notes,
                        }
                        for factor in sorted(
                            item.individual_factors,
                            key=lambda factor: factor.factor_code,
                        )
                    ],
                }
                for item in sorted(
                    comparison.comparison_targets,
                    key=lambda target: target.display_order,
                )
            ],
        }

    @staticmethod
    def _fingerprint(snapshot: dict) -> str:
        payload = json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    @staticmethod
    def _report_response(
        document: DocumentRecord,
        report_id: UUID,
        validation_run_id: UUID,
        request_id: UUID | None,
    ) -> FormalReportResponse:
        return FormalReportResponse(
            document_id=document.document_id,
            case_id=document.case_id,
            report_id=report_id,
            validation_run_id=validation_run_id,
            filename=document.original_filename,
            version_no=document.version_no,
            bucket_name=document.bucket_name,
            object_key=document.object_key,
            checksum_sha256=document.checksum_sha256,
            file_size_bytes=document.file_size_bytes,
            download_path=(
                f"/api/v1/valuation/cases/{document.case_id}/complete-reports/"
                f"{document.document_id}/download"
            ),
            request_id=request_id,
        )
