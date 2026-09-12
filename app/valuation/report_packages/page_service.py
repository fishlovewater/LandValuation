import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError, ResourceNotFoundError
from app.valuation.extraction.repository import ExtractionRepository
from app.valuation.models import (
    CaseRecord,
    DocumentExtractionRecord,
    DocumentRecord,
    ExtractedFieldRecord,
    FormInstanceRecord,
)
from app.valuation.report_packages.page_schemas import (
    F02DraftData,
    F02DraftUpdate,
    F02PageResponse,
    F02RFDraftData,
    F02RFDraftUpdate,
    F02RFPageResponse,
    F02RFFactorDraft,
    ReportBenchmarkContext,
    ReportPageCode,
    ReportPageContext,
    ReportParcelContext,
    S01DraftData,
    S01Observation,
    S01DraftUpdate,
    S01PageResponse,
)
from app.valuation.report_packages.factor_catalog import DISTANCE_FACTOR_CODES
from app.valuation.report_packages.repository import ReportPackageRepository
from app.valuation.report_packages.requirements import get_report_definition
from app.valuation.report_packages.schemas import ReportDraftReadinessResponse
from app.valuation.report_packages.service import ReportPackageService
from app.valuation.schemas import FormStatus
from app.valuation.service import ValuationService


PAGE_SCHEMA_VERSIONS = {
    ReportPageCode.S01.value: "s01-draft-v1",
    ReportPageCode.F02_RF.value: "f02-rf-draft-v1",
    ReportPageCode.F02.value: "f02-draft-v1",
}

FILLED_REPORT_TEXT_MARKERS = (
    "表1地價區段勘查表",
    "表5-2",
    "表4比較法調查估價表",
)


def looks_like_filled_three_page_report(extracted_text: str | None) -> bool:
    text = re.sub(r"\s+", "", extracted_text or "")
    text = text.translate(str.maketrans({"－": "-", "–": "-", "—": "-"}))
    return all(marker in text for marker in FILLED_REPORT_TEXT_MARKERS)

PageData = TypeVar("PageData", bound=BaseModel)


class ReportPageService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ReportPackageRepository | None = None,
        valuation: ValuationService | None = None,
    ) -> None:
        self.repository = repository or ReportPackageRepository(session)
        self.extraction_repository = ExtractionRepository(session)
        self.valuation = valuation or ValuationService(session)
        self.packages = ReportPackageService(
            session,
            repository=self.repository,
            valuation=self.valuation,
        )

    async def get_s01(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> S01PageResponse:
        case, records = await self._read_records(case_id, report_id, user)
        return await self._s01_response(case, report_id, records["S01"])

    async def update_s01(
        self,
        case_id: UUID,
        report_id: UUID,
        payload: S01DraftUpdate,
        user: User,
    ) -> S01PageResponse:
        case, records = await self._editable_records(case_id, report_id, user)
        record = records["S01"]
        current = self._read_data(record, S01DraftData)
        updated = self._merge(current, payload, S01DraftData)
        for observation in updated.observations:
            if observation.source_document_id is not None and not await self.repository.document_belongs_to_case(
                case_id, observation.source_document_id
            ):
                raise AppError(
                    "CROSS_CASE_REFERENCE",
                    "S01 來源文件不存在、已停用或不屬於此案件",
                    422,
                )
        await self._save_data(record, updated, user)
        return await self._s01_response(case, report_id, record)

    async def get_f02_rf(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> F02RFPageResponse:
        case, records = await self._read_records(case_id, report_id, user)
        comparison = self._read_data(records["F02"], F02DraftData)
        return await self._f02_rf_response(
            case, report_id, records["F02-RF"], comparison.comparison_workflow_enabled
        )

    async def update_f02_rf(
        self,
        case_id: UUID,
        report_id: UUID,
        payload: F02RFDraftUpdate,
        user: User,
    ) -> F02RFPageResponse:
        case, records = await self._editable_records(case_id, report_id, user)
        record = records["F02-RF"]
        current = self._read_data(record, F02RFDraftData)
        current = await self._ensure_default_formal_rule(
            case, record, current, user
        )
        updated = self._merge(current, payload, F02RFDraftData)
        self._invalidate_f02_rf_calculation(updated)
        await self._validate_f02_rf(case, updated)

        f02_data = self._read_data(records["F02"], F02DraftData)
        self._validate_cross_page_ids(updated, f02_data)
        await self._save_data(record, updated, user)
        return await self._f02_rf_response(
            case, report_id, record, f02_data.comparison_workflow_enabled
        )

    async def apply_extracted_candidates(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
    ) -> F02RFPageResponse:
        case, records = await self._editable_records(case_id, report_id, user)
        record = records["F02-RF"]
        current = self._read_data(record, F02RFDraftData)
        current = await self._ensure_default_formal_rule(
            case, record, current, user
        )

        # Query all CONFIRMED F02-RF candidates for this case
        stmt = (
            select(ExtractedFieldRecord)
            .where(
                ExtractedFieldRecord.case_id == case_id,
                ExtractedFieldRecord.form_code == "F02-RF",
                ExtractedFieldRecord.field_status == "CONFIRMED",
            )
        )
        candidates = list((await self.repository.session.scalars(stmt)).all())
        if not candidates:
            raise AppError("NO_CONFIRMED_FIELDS", "沒有已確認的 F02-RF 候選欄位可套用", 422)

        rule = await self.repository.get_rule_version(current.rule_version_id)
        if (
            rule is None
            or rule.import_status != "VERIFIED"
            or not rule.formula_code
            or not rule.rounding_code
            or not rule.land_use_types
        ):
            raise AppError(
                "FORMAL_RULE_NOT_READY",
                "正式規則尚未完成來源關聯、級距匯入、人工驗證與發布",
                409,
            )

        land_use = self._normalized_land_use(case.land_use_type)
        level_rows = await self.repository.list_factor_levels(
            current.rule_version_id,
            land_use,
            {candidate.field_name for candidate in candidates},
        )
        levels_by_factor: dict[str, list[object]] = {}
        for definition, level in level_rows:
            levels_by_factor.setdefault(definition.factor_code, []).append(level)

        resolved: dict[str, str] = {}
        unresolved: list[str] = []
        for candidate in candidates:
            supplied = str(candidate.confirmed_value or "").strip()
            level = self._resolve_rule_level(
                supplied,
                levels_by_factor.get(candidate.field_name, []),
            )
            if level is None:
                unresolved.append(candidate.field_name)
            else:
                resolved[candidate.field_name] = level
        if unresolved:
            raise AppError(
                "F02_RF_LEVEL_UNRESOLVED",
                "部分已確認因素無法依正式規則轉換為級距",
                422,
                {"fields": sorted(unresolved)},
            )

        # Merge candidates into current factor rows
        factor_map = {row.factor_code: row for row in current.factor_rows}
        for candidate in candidates:
            code = candidate.field_name
            level = resolved[code]
            if code in factor_map:
                factor_map[code].benchmark_reported_level = level
                factor_map[code].benchmark_confirmed_level = level
                factor_map[code].source_notes = f"AI 自動擷取自文件: {candidate.source_text}"
                factor_map[code].confirmed_by_user = True
            else:
                factor_map[code] = F02RFFactorDraft(
                    factor_code=code,
                    benchmark_reported_level=level,
                    benchmark_confirmed_level=level,
                    source_notes=f"AI 自動擷取自文件: {candidate.source_text}",
                    confirmed_by_user=True,
                    targets=[]
                )

        current.factor_rows = list(factor_map.values())
        self._invalidate_f02_rf_calculation(current)
        await self._validate_f02_rf(case, current)

        f02_data = self._read_data(records["F02"], F02DraftData)
        self._validate_cross_page_ids(current, f02_data)
        await self._save_data(record, current, user)

        # Apply candidates through the case-wide replacement operation.
        for candidate in candidates:
            await self.extraction_repository.apply_candidate(
                candidate, record.form_instance_id
            )

        await self.repository.session.flush()
        return await self._f02_rf_response(
            case, report_id, record, f02_data.comparison_workflow_enabled
        )

    async def confirm_manual_walking_distance(
        self,
        case_id: UUID,
        report_id: UUID,
        *,
        item_code: str,
        facility_name: str,
        walking_distance_m: Decimal,
        source_notes: str,
        origin_type: str,
        origin_reference_id: UUID | None,
        user: User,
    ) -> str:
        if item_code not in DISTANCE_FACTOR_CODES:
            raise AppError(
                "FACILITY_FACTOR_NOT_SUPPORTED",
                "此欄位不是可以人工輸入最短步行距離的設施因素",
                422,
            )
        case, records = await self._editable_records(case_id, report_id, user)
        s01_record = records["S01"]
        rf_record = records["F02-RF"]
        s01 = self._read_data(s01_record, S01DraftData)
        regional = self._read_data(rf_record, F02RFDraftData)
        regional = await self._ensure_default_formal_rule(
            case, rf_record, regional, user
        )
        rule = await self.repository.get_rule_version(regional.rule_version_id)
        if (
            rule is None
            or rule.import_status != "VERIFIED"
            or not rule.formula_code
            or not rule.rounding_code
        ):
            raise AppError(
                "FORMAL_RULE_NOT_READY",
                "正式規則尚未完成來源關聯、級距匯入、人工驗證與發布",
                409,
            )
        levels = await self.repository.list_factor_levels(
            regional.rule_version_id,
            self._normalized_land_use(case.land_use_type),
            {item_code},
        )
        resolved_level = self._resolve_rule_level(
            f"{walking_distance_m}公尺",
            [level for _, level in levels],
        )
        if resolved_level is None:
            raise AppError(
                "FACILITY_DISTANCE_LEVEL_UNRESOLVED",
                "最短步行距離無法對應已選擇正式規則的級距",
                422,
                {"item_code": item_code, "walking_distance_m": str(walking_distance_m)},
            )

        observation = S01Observation(
            item_code=item_code,
            raw_value=f"{walking_distance_m}公尺",
            facility_name=facility_name,
            walking_distance_m=walking_distance_m,
            distance_type="WALKING",
            origin_type=origin_type,
            origin_reference_id=origin_reference_id,
            source_type="MANUAL_CONFIRMED",
            source_notes=source_notes,
            confirmed_by_user=True,
        )
        observation_map = {item.item_code: item for item in s01.observations}
        observation_map[item_code] = observation
        s01.observations = list(observation_map.values())

        factor_map = {row.factor_code: row for row in regional.factor_rows}
        factor = factor_map.get(item_code)
        if factor is None:
            factor = F02RFFactorDraft(factor_code=item_code)
            factor_map[item_code] = factor
        factor.benchmark_reported_level = f"{walking_distance_m}公尺"
        factor.benchmark_confirmed_level = resolved_level
        factor.source_notes = source_notes
        factor.confirmed_by_user = True
        regional.factor_rows = list(factor_map.values())
        self._invalidate_f02_rf_calculation(regional)
        await self._validate_f02_rf(case, regional)
        await self._save_data(s01_record, s01, user)
        await self._save_data(rf_record, regional, user)
        return resolved_level

    @staticmethod
    def _normalized_land_use(value: object) -> str:
        aliases = {
            "住宅用地": "RESIDENTIAL",
            "商業用地": "COMMERCIAL",
            "工業用地": "INDUSTRIAL",
            "農業用地": "AGRICULTURAL",
            "其他": "OTHER",
        }
        text = str(value or "").strip()
        return aliases.get(text, text.upper())

    @staticmethod
    def _rule_text(value: object) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or "")).upper()
        return re.sub(r"[\s,，:：|\\/\-_。；;\(\)（）]", "", normalized)

    @classmethod
    def _resolve_rule_level(cls, supplied: str, levels: list[object]) -> str | None:
        """Resolve any formal factor against imported rule levels, not hard-coded factors."""
        value_key = cls._rule_text(supplied)
        if not value_key or not levels:
            return None

        direct = [
            level
            for level in levels
            if value_key
            in {
                cls._rule_text(level.level_code),
                cls._rule_text(level.level_name),
            }
        ]
        if len(direct) == 1:
            return direct[0].level_code

        number_match = re.search(r"-?\d+(?:\.\d+)?", unicodedata.normalize("NFKC", supplied))
        if number_match:
            try:
                number = Decimal(number_match.group(0))
            except InvalidOperation:
                number = None
            if number is not None:
                ranged = [
                    level
                    for level in levels
                    if (level.range_min is None or number >= level.range_min)
                    and (level.range_max is None or number <= level.range_max)
                    and (level.range_min is not None or level.range_max is not None)
                ]
                if len(ranged) == 1:
                    return ranged[0].level_code

        qualitative = []
        for level in levels:
            condition_key = cls._rule_text(level.qualitative_value)
            if condition_key and (
                condition_key == value_key
                or condition_key in value_key
                or value_key in condition_key
            ):
                qualitative.append(level)
        if len(qualitative) == 1:
            return qualitative[0].level_code
        return None

    async def get_f02(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> F02PageResponse:
        case, records = await self._read_records(case_id, report_id, user)
        return await self._f02_response(case, report_id, records["F02"])

    async def update_f02(
        self,
        case_id: UUID,
        report_id: UUID,
        payload: F02DraftUpdate,
        user: User,
    ) -> F02PageResponse:
        case, records = await self._editable_records(case_id, report_id, user)
        record = records["F02"]
        current = self._read_data(record, F02DraftData)
        updated = self._merge(current, payload, F02DraftData)
        self._invalidate_f02_calculation(updated)
        await self._validate_f02(case_id, updated)

        regional_data = self._read_data(records["F02-RF"], F02RFDraftData)
        self._validate_cross_page_ids(regional_data, updated)
        await self._save_data(record, updated, user)
        return await self._f02_response(case, report_id, record)

    async def draft_pdf_data(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> dict:
        case, records = await self._read_records(case_id, report_id, user)
        context = await self._context(case)
        return {
            "context": context.model_dump(mode="json"),
            "s01": self._read_data(records["S01"], S01DraftData).model_dump(
                mode="json"
            ),
            "f02_rf": self._read_data(
                records["F02-RF"], F02RFDraftData
            ).model_dump(mode="json"),
            "f02": self._read_data(records["F02"], F02DraftData).model_dump(
                mode="json"
            ),
            "report_id": str(report_id),
            "version_no": records["F02"].version_no,
        }

    async def filled_template_source_document(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
    ) -> DocumentRecord | None:
        """Return a source PDF only when all three known headings were extracted."""
        await self._read_records(case_id, report_id, user)
        statement = (
            select(DocumentRecord, DocumentExtractionRecord.extracted_text)
            .join(
                DocumentExtractionRecord,
                DocumentExtractionRecord.document_id == DocumentRecord.document_id,
            )
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.is_active.is_(True),
                DocumentRecord.mime_type == "application/pdf",
                DocumentExtractionRecord.case_id == case_id,
                DocumentExtractionRecord.extraction_status == "COMPLETED",
            )
            .order_by(DocumentExtractionRecord.completed_at.desc())
        )
        rows = (await self.repository.session.execute(statement)).all()
        for document, extracted_text in rows:
            if looks_like_filled_three_page_report(extracted_text):
                return document
        return None

    async def draft_map_documents(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> dict[str, object]:
        await self._read_records(case_id, report_id, user)
        definition = get_report_definition("REPORT_COMPARISON_COMMERCIAL")
        map_types = {
            page.document_type
            for page in definition.pages
            if page.kind == "DOCUMENT" and page.document_type is not None
        }
        return await self.repository.active_documents_by_types(case_id, map_types)

    async def draft_readiness(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> ReportDraftReadinessResponse:
        _, records = await self._read_records(case_id, report_id, user)

        s01 = self._read_data(records["S01"], S01DraftData)
        f02_rf = self._read_data(records["F02-RF"], F02RFDraftData)
        f02 = self._read_data(records["F02"], F02DraftData)
        blockers: list[str] = []
        warnings = [
            "DRAFT_PREVIEW_DOES_NOT_WRITE_TO_MINIO",
        ]
        if not any(item.confirmed_by_user for item in s01.observations):
            warnings.append("S01_CONFIRMED_OBSERVATIONS_MISSING")
        if not f02_rf.factor_rows:
            warnings.append("F02_RF_FACTOR_ROWS_MISSING")
        if not f02.comparison_targets:
            warnings.append("F02_COMPARISON_TARGETS_MISSING")
        if f02_rf.rule_version_id is None:
            warnings.append("FORMAL_RULE_VERSION_MISSING")
        validation = await self.repository.latest_report_validation(
            case_id, report_id
        )
        if validation and validation.failed_count > 0:
            blockers.append("FORMAL_SIX_PAGE_VALIDATION_REQUIRED")

        return ReportDraftReadinessResponse(
            report_id=report_id,
            case_id=case_id,
            can_generate_pages_1_3_draft=True,
            can_generate_pages_1_6_draft=True,
            can_generate_formal_report=not blockers,
            missing_map_document_types=[],
            blocking_errors=list(dict.fromkeys(blockers)),
            warnings=warnings,
        )

    async def _read_records(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
        *,
        for_update: bool = False,
    ) -> tuple[CaseRecord, dict[str, FormInstanceRecord]]:
        if for_update:
            case = await self.valuation._case_or_404(case_id, for_update=True)
            self.valuation._require_case_read(case, user)
        else:
            case = await self.valuation.get_case(case_id, user)
        root = await self.repository.get_form(case_id, report_id)
        if root is None:
            raise ResourceNotFoundError("完整查估書")
        records = await self.packages._load_components(case_id, root)
        return case, {record.form_code: record for record in records}

    async def _editable_records(
        self, case_id: UUID, report_id: UUID, user: User
    ) -> tuple[CaseRecord, dict[str, FormInstanceRecord]]:
        case = await self.valuation._owned_editable_case(case_id, user)
        root = await self.repository.get_form(case_id, report_id)
        if root is None:
            raise ResourceNotFoundError("完整查估書")
        records = await self.packages._load_components(case_id, root)
        by_code = {record.form_code: record for record in records}
        if any(
            record.form_status != FormStatus.DRAFT.value
            for record in by_code.values()
        ):
            raise AppError(
                "REPORT_PAGE_STATE_CONFLICT",
                "前三頁只能在套件全部為 DRAFT 時修改",
                409,
            )
        return case, by_code

    async def _context(self, case: CaseRecord) -> ReportPageContext:
        parcels = await self.valuation.repository.list_parcels(case.case_id)
        benchmark_lands = await self.repository.list_benchmark_lands(case.case_id)
        return ReportPageContext(
            case_id=case.case_id,
            case_no=case.case_no,
            case_title=case.case_title,
            valuation_base_date=case.valuation_base_date,
            city_code=case.city_code,
            district_code=case.district_code,
            land_use_type=case.land_use_type,
            parcels=[
                ReportParcelContext(
                    parcel_id=parcel.parcel_id,
                    district_code=parcel.district_code,
                    section_name=parcel.section_name,
                    subsection_name=parcel.subsection_name,
                    land_no=parcel.land_no,
                    area_sqm=parcel.area_sqm,
                    land_use_zone=parcel.land_use_zone,
                    designated_use=parcel.designated_use,
                )
                for parcel in parcels
            ],
            benchmark_lands=[
                ReportBenchmarkContext(
                    benchmark_land_id=benchmark.benchmark_land_id,
                    parcel_id=benchmark.parcel_id,
                    benchmark_land_no=benchmark.benchmark_land_no,
                    price_zone_no=benchmark.price_zone_no,
                )
                for benchmark in benchmark_lands
            ],
        )

    async def _s01_response(
        self,
        case: CaseRecord,
        report_id: UUID,
        record: FormInstanceRecord,
    ) -> S01PageResponse:
        data = self._read_data(record, S01DraftData)
        warnings: list[str] = []
        if not data.district_name:
            warnings.append("DISTRICT_NAME_MISSING")
        if not data.district_boundary:
            warnings.append("DISTRICT_BOUNDARY_MISSING")
        if data.survey_date is None:
            warnings.append("SURVEY_DATE_MISSING")
        if not any(item.confirmed_by_user for item in data.observations):
            warnings.append("CONFIRMED_SURVEY_OBSERVATION_MISSING")
        warnings.append("MANUAL_WALKING_DISTANCE_REQUIRES_USER_CONFIRMATION")
        return S01PageResponse(
            **await self._base_response(case, report_id, record, warnings),
            page_code=ReportPageCode.S01,
            data=data,
        )

    async def _f02_rf_response(
        self,
        case: CaseRecord,
        report_id: UUID,
        record: FormInstanceRecord,
        comparison_workflow_enabled: bool = True,
    ) -> F02RFPageResponse:
        data = self._read_data(record, F02RFDraftData)
        warnings: list[str] = []
        if comparison_workflow_enabled:
            if data.benchmark_land_id is None:
                warnings.append("BENCHMARK_LAND_MISSING")
            if data.comparison_analysis_id is None:
                warnings.append("COMPARISON_ANALYSIS_MISSING")
            if data.rule_version_id is None:
                warnings.append("FORMAL_FACTOR_RULE_VERSION_MISSING")
            if not data.factor_rows:
                warnings.append("FACTOR_ROWS_MISSING")
            if data.calculation_status != "CALCULATED":
                warnings.append("FORMAL_ADJUSTMENT_CALCULATION_REQUIRED")
        return F02RFPageResponse(
            **await self._base_response(case, report_id, record, warnings),
            page_code=ReportPageCode.F02_RF,
            data=data,
        )

    async def _f02_response(
        self,
        case: CaseRecord,
        report_id: UUID,
        record: FormInstanceRecord,
    ) -> F02PageResponse:
        data = self._read_data(record, F02DraftData)
        warnings: list[str] = []
        if data.comparison_workflow_enabled:
            if data.benchmark_land_id is None:
                warnings.append("BENCHMARK_LAND_MISSING")
            if data.comparison_analysis_id is None:
                warnings.append("COMPARISON_ANALYSIS_MISSING")
            if not data.comparison_targets:
                warnings.append("COMPARISON_TARGETS_MISSING")
            if data.calculation_status != "CALCULATED":
                warnings.append("FORMAL_COMPARISON_CALCULATION_REQUIRED")
        return F02PageResponse(
            **await self._base_response(case, report_id, record, warnings),
            page_code=ReportPageCode.F02,
            data=data,
        )

    async def _base_response(
        self,
        case: CaseRecord,
        report_id: UUID,
        record: FormInstanceRecord,
        warnings: list[str],
    ) -> dict:
        return {
            "report_id": report_id,
            "form_instance_id": record.form_instance_id,
            "case_id": case.case_id,
            "version_no": record.version_no,
            "form_status": record.form_status,
            "page_schema_version": PAGE_SCHEMA_VERSIONS[record.form_code],
            "context": await self._context(case),
            "warnings": warnings,
        }

    async def _validate_f02_rf(
        self, case: CaseRecord, data: F02RFDraftData
    ) -> None:
        await self._validate_common_comparison_references(
            case.case_id,
            data.benchmark_land_id,
            data.comparison_analysis_id,
            {
                item.comparison_target_id
                for row in data.factor_rows
                for item in row.targets
            },
        )
        if data.rule_version_id is not None:
            rule = await self.repository.get_rule_version(data.rule_version_id)
            if rule is None:
                raise AppError(
                    "RULE_VERSION_NOT_FOUND",
                    "找不到已發布的正式因素規則版本",
                    422,
                )
            if (
                rule.effective_from is None
                or rule.effective_from > case.valuation_base_date
                or (
                    rule.effective_to is not None
                    and rule.effective_to < case.valuation_base_date
                )
            ):
                raise AppError(
                    "RULE_DATE_NOT_APPLICABLE",
                    "此規則版本不適用案件估價基準日",
                    422,
                )
            if rule.jurisdiction_code == "NEW_TAIPEI_CITY":
                aliases = {
                    "住宅用地": "RESIDENTIAL",
                    "商業用地": "COMMERCIAL",
                    "工業用地": "INDUSTRIAL",
                    "農業用地": "AGRICULTURAL",
                    "其他": "OTHER",
                }
                land_use = aliases.get(
                    str(case.land_use_type or "").strip(),
                    str(case.land_use_type or "").strip().upper(),
                )
                if land_use not in set(rule.land_use_types or []):
                    raise AppError(
                        "RULE_LAND_USE_NOT_APPLICABLE",
                        "此規則版本不適用案件的土地用途",
                        422,
                    )
                scope = rule.district_scope or {}
                if (
                    scope.get("mode") == "INCLUDE"
                    and case.district_code not in set(scope.get("district_codes") or [])
                ):
                    raise AppError(
                        "RULE_DISTRICT_NOT_APPLICABLE",
                        "此規則版本不適用案件行政區",
                        422,
                    )

    async def _validate_f02(self, case_id: UUID, data: F02DraftData) -> None:
        await self._validate_common_comparison_references(
            case_id,
            data.benchmark_land_id,
            data.comparison_analysis_id,
            {item.comparison_target_id for item in data.comparison_targets},
        )

    async def _validate_common_comparison_references(
        self,
        case_id: UUID,
        benchmark_land_id: UUID | None,
        comparison_analysis_id: UUID | None,
        supplied_target_ids: set[UUID],
    ) -> None:
        benchmark = None
        if benchmark_land_id is not None:
            benchmark = await self.repository.get_benchmark_land(
                case_id, benchmark_land_id
            )
            if benchmark is None:
                raise AppError(
                    "CROSS_CASE_REFERENCE",
                    "比準地不存在、已停用或不屬於此案件",
                    422,
                )

        analysis = None
        if comparison_analysis_id is not None:
            analysis = await self.repository.get_comparison_analysis(
                case_id, comparison_analysis_id
            )
            if analysis is None:
                raise AppError(
                    "CROSS_CASE_REFERENCE",
                    "比較分析不存在、已停用或不屬於此案件",
                    422,
                )
            if benchmark is not None and analysis.benchmark_land_id != benchmark_land_id:
                raise AppError(
                    "REPORT_CROSS_PAGE_CONFLICT",
                    "比較分析的比準地與表單不一致",
                    422,
                )

        if supplied_target_ids:
            if analysis is None:
                raise AppError(
                    "COMPARISON_ANALYSIS_REQUIRED",
                    "選擇比較標前必須先指定比較分析",
                    422,
                )
            targets = await self.repository.list_comparison_targets(
                case_id, comparison_analysis_id
            )
            target_ids = {target.comparison_target_id for target in targets}
            if not supplied_target_ids.issubset(target_ids):
                raise AppError(
                    "CROSS_CASE_REFERENCE",
                    "比較標不存在或不屬於指定的比較分析",
                    422,
                )

    @staticmethod
    def _validate_cross_page_ids(
        regional: F02RFDraftData, comparison: F02DraftData
    ) -> None:
        for label, left, right in (
            (
                "benchmark_land_id",
                regional.benchmark_land_id,
                comparison.benchmark_land_id,
            ),
            (
                "comparison_analysis_id",
                regional.comparison_analysis_id,
                comparison.comparison_analysis_id,
            ),
        ):
            if left is not None and right is not None and left != right:
                raise AppError(
                    "REPORT_CROSS_PAGE_CONFLICT",
                    f"F02-RF 與 F02 的 {label} 不一致",
                    422,
                )

    @staticmethod
    def _read_data(record: FormInstanceRecord, model: type[PageData]) -> PageData:
        content = record.form_content if isinstance(record.form_content, dict) else {}
        return model.model_validate(content.get("data") or {})

    @staticmethod
    def _merge(
        current: PageData,
        payload: BaseModel,
        model: type[PageData],
    ) -> PageData:
        values = current.model_dump()
        values.update(payload.model_dump(exclude_unset=True))
        return model.model_validate(values)

    async def _save_data(
        self, record: FormInstanceRecord, data: BaseModel, user: User
    ) -> None:
        content = dict(record.form_content or {})
        content["page_schema_version"] = PAGE_SCHEMA_VERSIONS[record.form_code]
        content["data"] = data.model_dump(mode="json")
        record.form_content = content
        record.updated_by_user_id = user.user_id
        await self.repository.save_form(record)

    async def _ensure_default_formal_rule(
        self,
        case: CaseRecord,
        record: FormInstanceRecord,
        data: F02RFDraftData,
        user: User,
    ) -> F02RFDraftData:
        if data.rule_version_id is not None:
            return data
        rule = await self.repository.select_default_formal_rule(case)
        if rule is None:
            return data
        data.rule_version_id = rule.rule_version_id
        await self._save_data(record, data, user)
        return data

    @staticmethod
    def _invalidate_f02_rf_calculation(data: F02RFDraftData) -> None:
        data.regional_adjustment_rates = {}
        data.calculation_status = "NOT_CALCULATED"
        data.calculation_snapshot = {}
        data.calculated_at = None
        data.calculated_by_user_id = None
        for row in data.factor_rows:
            for target in row.targets:
                target.calculated_adjustment_rate = None

    @staticmethod
    def _invalidate_f02_calculation(data: F02DraftData) -> None:
        data.benchmark_comparison_price = None
        data.calculation_status = "NOT_CALCULATED"
        data.calculation_snapshot = {}
        data.calculated_at = None
        data.calculated_by_user_id = None
        for target in data.comparison_targets:
            target.regional_adjustment_rate = None
            target.individual_adjustment_rate = None
            target.total_adjustment_absolute = None
            target.trial_price = None
            target.normal_unit_price_snapshot = None
            target.transaction_date_snapshot = None
            target.date_adjusted_price = None
            target.regional_adjusted_price = None
            for factor in target.individual_factors:
                factor.calculated_adjustment_rate = None
