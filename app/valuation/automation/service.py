from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.storage.paths import build_generated_report_object_key
from app.storage.service import StorageService
from app.valuation.automation.schemas import (
    AutomatedConfirmRequest,
    AutomatedConfirmationExport,
    AutomatedDocumentResult,
    AutomatedIntakeManifest,
    AutomatedFormGuidance,
    AutomatedWorkflowResponse,
    AutomatedWorkflowStatus,
    ManualFieldValuesRequest,
)
from app.valuation.automation.confirmation_export_excel import (
    build_confirmation_export_xlsx,
)
from app.valuation.documents.schemas import DocumentCategory, DocumentResponse
from app.valuation.documents.repository import DocumentRepository
from app.valuation.documents.service import safe_filename
from app.valuation.documents.service import DocumentService
from app.valuation.extraction.field_analysis import FieldAnalysisService
from app.valuation.extraction.repository import ExtractionRepository
from app.valuation.extraction.schemas import (
    CandidateConfirmation,
    ExtractedFieldResponse,
    ExtractionConfirmRequest,
    ExtractionResponse,
    FieldAnalysisRequest,
)
from app.valuation.extraction.service import ExtractionService
from app.valuation.f01_f04_schemas import F01DraftUpdate, F04DraftUpdate
from app.valuation.f01_f04_service import F01F04Service
from app.valuation.f03_schemas import F03DraftUpdate
from app.valuation.f03_service import F03Service
from app.valuation.models import (
    BenchmarkLandRecord,
    CaseRecord,
    DocumentRecord,
    ExtractedFieldRecord,
)
from app.valuation.report_packages.draft_pdf_builder import (
    build_three_page_draft_pdf,
    build_three_page_source_preserved_draft_pdf,
)
from app.valuation.pdf_errors import build_pdf_safely
from app.valuation.report_packages.page_service import ReportPageService
from app.valuation.report_packages.page_schemas import (
    S01DraftUpdate,
    S01Observation,
)
from app.valuation.report_packages.factor_catalog import TEMPLATE_FACTOR_CODES
from app.valuation.report_packages.schemas import ReportPackageCreate, ReportType
from app.valuation.report_packages.service import ReportPackageService
from app.valuation.schemas import CaseResponse, FormCode, FormCreate, FormStatus
from app.valuation.requirements import FORM_REQUIREMENTS
from app.valuation.service import ValuationService


_CATEGORY_KEYWORDS: tuple[tuple[DocumentCategory, tuple[str, ...]], ...] = (
    (DocumentCategory.MAP_SECTION_SKETCH, ("地價區段略圖", "區段略圖")),
    (DocumentCategory.MAP_ZONING, ("地價使用分區圖", "使用分區圖")),
    (DocumentCategory.MAP_LAND_VALUE_SECTION, ("地價區段圖",)),
    (DocumentCategory.LAND_REGISTER, ("土地登記", "登記謄本", "謄本")),
    (DocumentCategory.CADASTRAL_MAP, ("地籍圖",)),
    (DocumentCategory.PHOTOS, ("現場照片", "勘查照片", "照片", "photo")),
)

F01_DECIMAL_FIELDS = frozenset(
    {
        "land_area_sqm",
        "building_area_sqm",
        "transaction_total_price",
        "land_transaction_price",
        "building_transaction_price",
        "parking_transaction_price",
        "building_price_deduction",
        "parking_price_deduction",
        "special_transaction_adjustment",
    }
)
F01_CANDIDATE_TO_DRAFT_FIELD = {
    "case_and_instance_refs": "transaction_no",
    "property_registry_fields": "location",
    "registered_building_area": "building_area_sqm",
    "calculation_building_area": "building_area_sqm",
    "land_area": "land_area_sqm",
    "transaction_total_price": "transaction_total_price",
}
F01_AUTO_APPLY_FIELDS = frozenset(
    {*F01DraftUpdate.model_fields, *F01_CANDIDATE_TO_DRAFT_FIELD}
)

AUTO_EXTRACT_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)


def classify_document(
    filename: str | None,
    content_type: str | None,
    override: str | None = None,
) -> tuple[DocumentCategory, str]:
    if override is not None:
        try:
            return DocumentCategory(override), "MANIFEST_OVERRIDE"
        except ValueError as exc:
            raise AppError(
                "DOCUMENT_CATEGORY_INVALID",
                f"檔案 {filename or 'upload'} 的 category_overrides 類型不支援",
                422,
            ) from exc

    name = Path(filename or "upload").name.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword.lower() in name for keyword in keywords):
            return category, "FILENAME_RULE"
    if (content_type or "").lower().startswith("image/"):
        return DocumentCategory.ATTACHMENTS, "SAFE_FALLBACK"
    return DocumentCategory.ORIGINAL, "SAFE_FALLBACK"


def _read_and_close_minio_response(response) -> bytes:
    try:
        return response.read()
    finally:
        response.close()
        release = getattr(response, "release_conn", None)
        if callable(release):
            release()


class AutomatedWorkflowService:
    def __init__(self, session: AsyncSession, storage: StorageService) -> None:
        self.session = session
        self.storage = storage
        self.valuation = ValuationService(session)
        self.documents = DocumentService(session, storage)
        self.extractions = ExtractionService(session, storage)
        self.extraction_repository = ExtractionRepository(session)
        self.f03 = F03Service(session)
        self.report_packages = ReportPackageService(session)
        self.pages = ReportPageService(session)

    async def intake(
        self,
        manifest: AutomatedIntakeManifest,
        files: list[UploadFile],
        user: User,
    ) -> AutomatedWorkflowResponse:
        if not files:
            raise AppError("INTAKE_FILES_REQUIRED", "至少需要上傳一份資料檔案", 422)

        uploaded_object_keys: list[str] = []
        document_results: list[AutomatedDocumentResult] = []
        warnings: list[str] = []
        ignored_duplicate_files: list[str] = []
        try:
            existing_case = await self.session.scalar(
                select(CaseRecord.case_id).where(
                    CaseRecord.case_no == manifest.case.case_no
                )
            )
            if existing_case is None:
                case = await self.valuation.create_case(manifest.case, user)
                parcels = [
                    await self.valuation.create_parcel(case.case_id, payload, user)
                    for payload in manifest.parcels
                ]
                benchmark_lands = [
                    await self.f03.create_benchmark_land(
                        case.case_id,
                        payload.as_create(parcels[payload.parcel_index].parcel_id),
                        user,
                    )
                    for payload in manifest.benchmark_lands
                ]

                f03_form = await self.valuation.create_form(
                    case.case_id,
                    FormCreate(
                        form_code=FormCode.F03,
                        prepared_date=manifest.prepared_date,
                    ),
                    user,
                )
                if benchmark_lands:
                    await self.f03.update_draft(
                        case.case_id,
                        f03_form.form_instance_id,
                        F03DraftUpdate(
                            benchmark_land_id=benchmark_lands[0].benchmark_land_id,
                            valuation_base_date=case.valuation_base_date,
                        ),
                        user,
                    )
                else:
                    warnings.append("BENCHMARK_LAND_NOT_SUPPLIED_F03_REMAINS_BLANK")

                report_id: UUID | None = None
                normalized_land_use = str(case.land_use_type or "").strip().upper()
                commercial = normalized_land_use in {"COMMERCIAL", "商業用地"}
                if manifest.create_commercial_report and commercial:
                    package = await self.report_packages.create(
                        case.case_id,
                        ReportPackageCreate(
                            report_type=ReportType.REPORT_COMPARISON_COMMERCIAL,
                            prepared_date=manifest.prepared_date,
                        ),
                        user,
                    )
                    report_id = package.report_id
                elif manifest.create_commercial_report:
                    warnings.append("COMMERCIAL_TEMPLATE_SKIPPED_FOR_OTHER_LAND_USE")
            else:
                # Reusing an existing case only appends evidence files; never
                # overwrite the established case, parcel, or benchmark data.
                case = await self.valuation.get_case(existing_case, user)
                parcels = []
                benchmark_lands = []
                warnings.append("EXISTING_CASE_DOCUMENTS_APPENDED")
                if manifest.parcels or manifest.benchmark_lands:
                    warnings.append("EXISTING_CASE_METADATA_IGNORED")

                forms = await self.valuation.list_forms(case.case_id, user)
                f03_form = next((item for item in forms if item.form_code == "F03"), None)
                if f03_form is None:
                    f03_form = await self.valuation.create_form(
                        case.case_id,
                        FormCreate(
                            form_code=FormCode.F03,
                            prepared_date=manifest.prepared_date,
                        ),
                        user,
                    )
                report_root = next(
                    (
                        item
                        for item in forms
                        if item.form_code == "F02"
                        and isinstance(item.form_content, dict)
                        and item.form_content.get("report_type")
                        == "REPORT_COMPARISON_COMMERCIAL"
                    ),
                    None,
                )
                report_id = report_root.form_instance_id if report_root else None
                normalized_land_use = str(case.land_use_type or "").strip().upper()
                commercial = normalized_land_use in {"COMMERCIAL", "商業用地"}
                if report_id is None and manifest.create_commercial_report and commercial:
                    package = await self.report_packages.create(
                        case.case_id,
                        ReportPackageCreate(
                            report_type=ReportType.REPORT_COMPARISON_COMMERCIAL,
                            prepared_date=manifest.prepared_date,
                        ),
                        user,
                    )
                    report_id = package.report_id
                elif report_id is None and manifest.create_commercial_report:
                    warnings.append("COMMERCIAL_TEMPLATE_SKIPPED_FOR_OTHER_LAND_USE")

            uploaded_checksums: dict[str, str] = {}
            for file in files:
                checksum = self._source_file_checksum(file)
                filename = Path(file.filename or "未命名檔案").name
                if checksum in uploaded_checksums:
                    ignored_duplicate_files.append(filename)
                    continue
                if await self.documents.repository.get_by_checksum(case.case_id, checksum):
                    ignored_duplicate_files.append(filename)
                    continue
                uploaded_checksums[checksum] = filename
                override = manifest.category_overrides.get(Path(file.filename or "").name)
                category, source = classify_document(
                    file.filename,
                    file.content_type,
                    override,
                )
                record = await self.documents.upload(
                    case.case_id,
                    category,
                    file,
                    user,
                )
                uploaded_object_keys.append(record.object_key)
                extraction_response: ExtractionResponse | None = None
                if record.mime_type.lower() in AUTO_EXTRACT_MIME_TYPES:
                    extraction, candidates = await self.extractions.start(
                        case.case_id,
                        record.document_id,
                        user,
                    )
                    if extraction.extraction_status == "COMPLETED":
                        await self._optional_ai_analysis(
                            case.case_id,
                            record.document_id,
                            report_id is not None,
                            user,
                            warnings,
                        )
                        extraction, candidates = await self.extractions.get_latest(
                            case.case_id,
                            record.document_id,
                            user,
                        )
                    extraction_response = self._extraction_response(
                        extraction,
                        candidates,
                    )
                document_results.append(
                    AutomatedDocumentResult(
                        document=DocumentResponse.model_validate(record),
                        detected_category=category.value,
                        category_source=source,
                        extraction=extraction_response,
                    )
                )

            if ignored_duplicate_files:
                warnings.append("DUPLICATE_SOURCE_FILE_IGNORED")

            return await self._response(
                case.case_id,
                user,
                status=AutomatedWorkflowStatus.REVIEW_REQUIRED,
                parcel_ids=[item.parcel_id for item in parcels],
                benchmark_land_ids=[item.benchmark_land_id for item in benchmark_lands],
                f03_form_instance_id=f03_form.form_instance_id,
                report_id=report_id,
                document_results=document_results,
                warnings=warnings,
                ignored_duplicate_files=ignored_duplicate_files,
            )
        except Exception:
            for object_key in reversed(uploaded_object_keys):
                try:
                    await self.storage.delete(object_key)
                except Exception:
                    pass
            raise

    @staticmethod
    def _source_file_checksum(file: UploadFile) -> str:
        """Hash an upload without changing the position seen by later processing."""
        stream = file.file
        stream.seek(0)
        digest = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
        stream.seek(0)
        return digest.hexdigest()

    async def review(self, case_id: UUID, user: User) -> AutomatedWorkflowResponse:
        await self.valuation.get_case(case_id, user)
        forms = await self.valuation.list_forms(case_id, user)
        f03_forms = [item for item in forms if item.form_code == "F03"]
        if not f03_forms:
            raise AppError(
                "AUTOMATED_WORKFLOW_NOT_FOUND",
                "此案件尚未建立簡化自動流程",
                404,
            )
        report_roots = [
            item
            for item in forms
            if item.form_code == "F02"
            and isinstance(item.form_content, dict)
            and item.form_content.get("report_type") == "REPORT_COMPARISON_COMMERCIAL"
        ]
        return await self._response(
            case_id,
            user,
            status=AutomatedWorkflowStatus.REVIEW_REQUIRED,
            f03_form_instance_id=f03_forms[0].form_instance_id,
            report_id=(report_roots[0].form_instance_id if report_roots else None),
        )

    async def confirm(
        self,
        case_id: UUID,
        payload: AutomatedConfirmRequest,
        user: User,
    ) -> AutomatedWorkflowResponse:
        await self.valuation._owned_editable_case(case_id, user)
        grouped: dict[UUID, list[CandidateConfirmation]] = defaultdict(list)
        for item in payload.confirmations:
            grouped[item.document_id].append(
                CandidateConfirmation(
                    extracted_field_id=item.extracted_field_id,
                    decision=item.decision,
                    corrected_value=item.corrected_value,
                )
            )
        for document_id, confirmations in grouped.items():
            await self.extractions.confirm(
                case_id,
                document_id,
                ExtractionConfirmRequest(confirmations=confirmations),
                user,
            )

        forms = await self.valuation.list_forms(case_id, user)
        f03_form = next((item for item in forms if item.form_code == "F03"), None)
        if f03_form is None:
            raise AppError("AUTOMATED_WORKFLOW_NOT_FOUND", "找不到自動建立的 F03", 404)
        report_root = next(
            (
                item
                for item in forms
                if item.form_code == "F02"
                and isinstance(item.form_content, dict)
                and item.form_content.get("report_type") == "REPORT_COMPARISON_COMMERCIAL"
            ),
            None,
        )

        warnings: list[str] = []
        await self._apply_f03_candidates(
            case_id,
            f03_form.form_instance_id,
            user,
            warnings,
        )
        await self._apply_confirmed_codex_f01_candidates(
            case_id,
            user,
            warnings,
        )
        if report_root is not None:
            await self._apply_confirmed_s01_candidates(
                case_id,
                report_root.form_instance_id,
                user,
                warnings,
            )
        if report_root is not None:
            has_factor_candidate = await self.session.scalar(
                select(ExtractedFieldRecord.extracted_field_id)
                .where(
                    ExtractedFieldRecord.case_id == case_id,
                    ExtractedFieldRecord.form_code == "F02-RF",
                    ExtractedFieldRecord.field_status == "CONFIRMED",
                )
                .limit(1)
            )
            if has_factor_candidate is not None:
                # Confirming OCR/Codex evidence is intentionally independent
                # from formal factor calculation. Applying F02-RF values
                # requires a reviewed rule version to translate raw evidence
                # into formal levels, but that later prerequisite must not
                # roll back an otherwise valid review decision.
                warnings.append(
                    "F02_RF_CONFIRMED_CANDIDATES_AWAIT_RULE_VERSION"
                )
        await self._save_confirmation_export(case_id, user)
        response = await self._response(
            case_id,
            user,
            status=AutomatedWorkflowStatus.READY_FOR_VALIDATION,
            f03_form_instance_id=f03_form.form_instance_id,
            report_id=(report_root.form_instance_id if report_root else None),
            warnings=warnings,
        )
        return response

    async def save_manual_fields(
        self,
        case_id: UUID,
        payload: ManualFieldValuesRequest,
        user: User,
    ) -> AutomatedWorkflowResponse:
        """Persist non-empty workbench values without requiring a full form."""
        await self.valuation._owned_editable_case(case_id, user)
        forms = await self.valuation.list_forms(case_id, user)
        forms_by_code: dict[str, object] = {}
        for form in forms:
            forms_by_code.setdefault(str(form.form_code), form)

        # The simplified intake always creates F03 and, when applicable, the
        # three-page report package.  A user may nevertheless need to fill an
        # F01 or F04 fact manually before AI/OCR has created that draft.  Create
        # only those missing standalone drafts when a non-empty manual value is
        # actually submitted; merely opening their selector remains read-only.
        requested_codes = {
            form_code
            for form_code, fields in (payload.values or {}).items()
            if any(value is not None and str(value).strip() for value in (fields or {}).values())
        }
        for code in (FormCode.F01.value, FormCode.F04.value):
            if code not in requested_codes or code in forms_by_code:
                continue
            created = await self.valuation.create_form(
                case_id,
                FormCreate(form_code=FormCode(code)),
                user,
            )
            forms.append(created)
            forms_by_code[code] = created

        report_root = next(
            (
                form for form in forms
                if str(form.form_code) == "F02"
                and isinstance(form.form_content, dict)
                and form.form_content.get("report_type") == "REPORT_COMPARISON_COMMERCIAL"
            ),
            None,
        )
        # A new manual value supersedes the previous value.  If a formal
        # report was already generated, reopen its three report pages so the
        # new value can be written into the formal S01 page and recalculated.
        # The previous PDF remains in storage as history, but is no longer
        # treated as the current downloadable/submittable report.
        has_new_values = any(
            any(value is not None and str(value).strip() != "" for value in (fields or {}).values())
            for fields in (payload.values or {}).values()
        )
        if has_new_values and report_root is not None:
            _, report_records = await self.pages._read_records(
                case_id, report_root.form_instance_id, user
            )
            if any(
                record.form_status != FormStatus.DRAFT.value
                for record in report_records.values()
            ):
                for record in report_records.values():
                    record.form_status = FormStatus.DRAFT.value
                    record.output_document_id = None
                    record.updated_by_user_id = user.user_id
                    await self.valuation.repository.save_form(record)

        saved: list[str] = []
        ignored: list[str] = []
        errors: dict[str, str] = {}
        direct_updates: dict[str, dict[str, object]] = {
            "F01": {}, "F03": {}, "F04": {},
        }
        direct_allowed = {
            "F01": set(F01DraftUpdate.model_fields),
            "F03": set(F03DraftUpdate.model_fields),
        }
        # F04 uses the same dedicated service as F01, but its draft has a
        # different update model and must not receive arbitrary catalogue keys.
        direct_allowed["F04"] = {
            "valuation_base_date", "price_zone_no", "rule_version_id", "notes",
            "filled_date", "handler_name", "section_head_name", "director_name",
            "appraiser_name",
        }

        for form_code, fields in (payload.values or {}).items():
            form = forms_by_code.get(form_code)
            if form is None:
                ignored.extend(f"{form_code}.{name}" for name in fields)
                continue
            non_empty = {
                name: value
                for name, value in (fields or {}).items()
                if value is not None and str(value).strip() != ""
            }
            if not non_empty:
                continue
            saved.extend(f"{form_code}.{name}" for name in non_empty)
            accepted = {
                name: value
                for name, value in non_empty.items()
                if name in direct_allowed.get(form_code, set())
            }
            if accepted:
                direct_updates[form_code].update(accepted)

            # Keep every accepted catalogue value, including fields that are
            # not yet represented by a formal page schema, for audit/export.
            content = dict(form.form_content or {})
            overrides = dict(content.get("manual_overrides") or {})
            overrides.update(non_empty)
            content["manual_overrides"] = overrides
            form.form_content = content
            form.updated_by_user_id = user.user_id
            await self.valuation.repository.save_form(form)

        for form_code, values in direct_updates.items():
            if not values:
                continue
            form = forms_by_code.get(form_code)
            if form is None:
                continue
            try:
                if form_code == "F01":
                    await F01F04Service(self.session).update(
                        case_id, form.form_instance_id, "F01",
                        F01DraftUpdate.model_validate(values), user,
                    )
                elif form_code == "F03":
                    await F03Service(self.session).update_draft(
                        case_id, form.form_instance_id,
                        F03DraftUpdate.model_validate(values), user,
                    )
                else:
                    await F01F04Service(self.session).update(
                        case_id, form.form_instance_id, "F04",
                        F04DraftUpdate.model_validate(values), user,
                    )
            except Exception as exc:
                message = getattr(exc, "message", str(exc))
                for name in values:
                    errors[f"{form_code}.{name}"] = message

        # The AI catalogue uses descriptive field codes while the formal S01
        # page stores a smaller set of direct fields plus observation rows.
        # Translate the user-entered catalogue values before formal checking;
        # otherwise a completed S01 in the workbench would still look empty.
        s01_values = {
            name: value
            for name, value in (payload.values or {}).get("S01", {}).items()
            if value is not None and str(value).strip() != ""
        }
        if s01_values and report_root is not None:
            try:
                current_page = await self.pages.get_s01(
                    case_id, report_root.form_instance_id, user
                )
                current_data = current_page.data.model_dump(mode="json")
                numeric_targets = {
                    "building_coverage_rate",
                    "floor_area_ratio",
                    "main_road_width_m",
                    "average_road_width_m",
                }

                def normalize_s01_value(source: str, target: str, value: object):
                    if target in numeric_targets:
                        raw = str(value).strip().replace(",", "").replace("％", "%")
                        if raw.endswith("%"):
                            raw = raw[:-1].strip()
                        for suffix in ("公尺", "m", "M"):
                            if raw.endswith(suffix):
                                raw = raw[: -len(suffix)].strip()
                                break
                        try:
                            return Decimal(raw)
                        except (InvalidOperation, ValueError):
                            errors[f"S01.{source}"] = (
                                f"{source} 必須是數字；目前輸入「{value}」已保留在手動資料，"
                                "正式 S01 欄位暫時留空"
                            )
                            return None
                    if target == "survey_date":
                        raw = str(value).strip().replace("/", "-")
                        try:
                            return date.fromisoformat(raw)
                        except ValueError:
                            errors[f"S01.{source}"] = (
                                f"{source} 必須是 YYYY-MM-DD 日期；目前輸入「{value}」已保留在手動資料，"
                                "正式 S01 欄位暫時留空"
                            )
                            return None
                    return value

                direct_map = {
                    "administrative_area": "district_name",
                    "zone_boundary_description": "district_boundary",
                    "survey_date": "survey_date",
                    "urban_plan_status": "urban_plan_status",
                    "urban_plan_scope": "urban_plan_status",
                    "land_use_zone": "land_use_zone",
                    "land_use_zone_category": "land_use_zone",
                    "building_coverage_rate": "building_coverage_rate",
                    "building_coverage_ratio": "building_coverage_rate",
                    "floor_area_ratio": "floor_area_ratio",
                    "prohibited_building": "prohibited_building",
                    "building_prohibition_status": "prohibited_building",
                    "restricted_building": "restricted_building",
                    "building_restriction_status": "restricted_building",
                    "building_restriction_details": "restricted_building",
                    "main_road_name": "main_road_name",
                    "main_road_width_m": "main_road_width_m",
                    "average_internal_road_width_m": "average_road_width_m",
                    "internal_road_width_m": "average_road_width_m",
                    "handler_name": "handler_name",
                    "section_chief_name": "section_head_name",
                    "director_name": "director_name",
                    "appraiser_name": "appraiser_name",
                }
                s01_payload = {
                    target: normalized
                    for source, target in direct_map.items()
                    if source in s01_values
                    for normalized in [normalize_s01_value(source, target, s01_values[source])]
                    if normalized is not None
                }
                observation_map = {
                    "urban_plan_status": "urban_plan_status",
                    "urban_plan_scope": "urban_plan_status",
                    "land_use_zone": "land_use_zone",
                    "land_use_zone_category": "land_use_zone",
                    "building_coverage_rate": "building_coverage_rate",
                    "building_coverage_ratio": "building_coverage_rate",
                    "floor_area_ratio": "floor_area_ratio",
                    "prohibited_building": "prohibited_building",
                    "building_prohibition_status": "prohibited_building",
                    "restricted_building": "restricted_building",
                    "building_restriction_status": "restricted_building",
                    "building_restriction_details": "restricted_building",
                    "main_road_width_m": "main_road_width",
                    "internal_road_width_m": "average_road_width",
                    "average_internal_road_width_m": "average_road_width",
                    "road_planning_development_level": "road_plan",
                    "drainage_level": "drainage",
                    "terrain_level": "terrain",
                    "slope_level": "terrain",
                    "consumer_market_proximity": "market_proximity",
                    "settlement_proximity_level": "settlement_proximity",
                    "park_proximity_level": "park_proximity",
                    "major_station_distance_m": "mass_transit_proximity",
                    "major_station_type": "mass_transit_proximity",
                    "interchange_distance_m": "interchange_proximity",
                    "commercial_facility_distance_m": "department_store",
                    "commercial_facility_count": "department_store",
                    "pollution_distance_m": "environmental_pollution",
                    "wastewater_waste_facility_present": "waste_facility",
                }
                observations = list(current_data.get("observations") or [])
                by_code = {item.get("item_code"): item for item in observations}
                for source, item_code in observation_map.items():
                    if source not in s01_values or item_code not in TEMPLATE_FACTOR_CODES:
                        continue
                    normalized = normalize_s01_value(
                        source,
                        direct_map.get(source, item_code),
                        s01_values[source],
                    )
                    if normalized is None:
                        continue
                    row = by_code.get(item_code, {"item_code": item_code})
                    row.update({
                        "raw_value": normalized,
                        "source_type": "MANUAL_CONFIRMED",
                        "source_notes": "簡易前端手動輸入並載入",
                        "confirmed_by_user": True,
                    })
                    by_code[item_code] = row
                if by_code:
                    s01_payload["observations"] = list(by_code.values())
                if s01_payload:
                    await self.pages.update_s01(
                        case_id,
                        report_root.form_instance_id,
                        S01DraftUpdate.model_validate(s01_payload),
                        user,
                    )
            except Exception as exc:
                message = getattr(exc, "message", str(exc))
                errors["S01"] = f"正式 S01 同步失敗：{message}"

        await self._save_confirmation_export(case_id, user)
        response = await self.review(case_id, user)
        response.manual_fields_saved = saved
        response.manual_fields_ignored = ignored
        response.manual_field_errors = errors
        response.manual_field_values = {
            str(form.form_code): dict(
                (form.form_content or {}).get("manual_overrides") or {}
            )
            for form in await self.valuation.list_forms(case_id, user)
            if isinstance(form.form_content, dict)
            and isinstance(form.form_content.get("manual_overrides"), dict)
        }
        return response

    async def _save_confirmation_export(
        self,
        case_id: UUID,
        user: User,
    ) -> DocumentRecord:
        """Save a review-only Excel spreadsheet of all resolved candidate decisions."""
        case = await self.valuation.get_case(case_id, user)
        candidates = list(
            (
                await self.session.scalars(
                    select(ExtractedFieldRecord)
                    .where(
                        ExtractedFieldRecord.case_id == case_id,
                        ExtractedFieldRecord.field_status.in_(
                            ("CONFIRMED", "APPLIED", "REJECTED")
                        ),
                    )
                    .order_by(
                        ExtractedFieldRecord.form_code,
                        ExtractedFieldRecord.field_name,
                    )
                )
            ).all()
        )
        forms = await self.valuation.list_forms(case_id, user)
        manual_values = {
            str(form.form_code): dict(
                (form.form_content or {}).get("manual_overrides") or {}
            )
            for form in forms
            if isinstance(form.form_content, dict)
            and isinstance(form.form_content.get("manual_overrides"), dict)
        }
        generated_at = datetime.now(UTC)
        xlsx_bytes = await run_in_threadpool(
            build_confirmation_export_xlsx,
            case_no=case.case_no,
            case_title=case.case_title,
            generated_at=generated_at,
            candidates=candidates,
            manual_values=manual_values,
        )
        repository = DocumentRepository(self.session)
        group_id = uuid5(
            NAMESPACE_URL,
            f"land-valuation:{case_id}:candidate-confirmation-export",
        )
        version_no = await repository.next_version(case_id, group_id)
        document_id = uuid4()
        filename = safe_filename(
            f"candidate_confirmation_{case.case_no}_v{version_no}.xlsx"
        )
        object_key = build_generated_report_object_key(
            case_id, group_id, document_id, version_no, filename
        )
        xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        uploaded = await self.storage.upload(
            object_key,
            BytesIO(xlsx_bytes),
            len(xlsx_bytes),
            content_type=xlsx_mime,
        )
        try:
            await repository.deactivate_group(case_id, group_id)
            return await repository.create(
                DocumentRecord(
                    document_id=document_id,
                    document_group_id=group_id,
                    case_id=case_id,
                    document_type="candidate-confirmation-export",
                    original_filename=filename,
                    mime_type=xlsx_mime,
                    bucket_name=str(uploaded["bucket_name"]),
                    object_key=str(uploaded["object_key"]),
                    checksum_sha256=hashlib.sha256(xlsx_bytes).hexdigest(),
                    file_size_bytes=len(xlsx_bytes),
                    storage_etag=str(uploaded["etag"]),
                    version_no=version_no,
                    uploaded_by_user_id=user.user_id,
                    is_active=True,
                )
            )
        except Exception:
            await self.storage.delete(object_key)
            raise

    @staticmethod
    def _normalized_confirmed_f01_value(field_name: str, value: object) -> object:
        """Convert only display formatting that is unambiguous for the F01 schema."""
        if value is None:
            return None
        if field_name in F01_DECIMAL_FIELDS and isinstance(value, str):
            normalized = value.strip().replace(",", "").replace("\uFF0C", "")
            try:
                return Decimal(normalized)
            except InvalidOperation:
                return value
        if field_name == "transaction_date" and isinstance(value, str):
            match = re.fullmatch(r"(\d{2,3})\D+(\d{1,2})\D+(\d{1,2})\D*", value.strip())
            if match:
                year, month, day = (int(part) for part in match.groups())
                try:
                    return date(year + 1911, month, day)
                except ValueError:
                    return value
        return value

    async def _apply_confirmed_codex_f01_candidates(
        self,
        case_id: UUID,
        user: User,
        warnings: list[str],
    ) -> list[UUID]:
        """Apply reviewed Codex F01 values to a draft form without producing a file."""
        candidates = list(
            (
                await self.session.scalars(
                    select(ExtractedFieldRecord)
                    .where(
                        ExtractedFieldRecord.case_id == case_id,
                        ExtractedFieldRecord.form_code == "F01",
                        ExtractedFieldRecord.analysis_provider.in_(("CODEX", "XLSX_RULE")),
                        ExtractedFieldRecord.field_status.in_(("CONFIRMED", "APPLIED")),
                    )
                    .order_by(ExtractedFieldRecord.confirmed_at.desc())
                )
            ).all()
        )
        if not candidates:
            return []

        forms = await self.valuation.list_forms(case_id, user)
        forms_by_source = {
            form.source_document_id: form
            for form in forms
            if form.form_code == FormCode.F01.value and form.source_document_id is not None
        }
        by_document: dict[UUID, list[ExtractedFieldRecord]] = defaultdict(list)
        for candidate in candidates:
            by_document[candidate.document_id].append(candidate)

        f01 = F01F04Service(self.session)
        applied_form_ids: list[UUID] = []
        for document_id, document_candidates in by_document.items():
            applicable = [
                candidate
                for candidate in document_candidates
                if candidate.field_name in F01_AUTO_APPLY_FIELDS
                and candidate.confirmed_value is not None
            ]
            form = forms_by_source.get(document_id)
            if form is None:
                if not applicable:
                    continue
                form = await self.valuation.create_form(
                    case_id,
                    FormCreate(form_code=FormCode.F01, source_document_id=document_id),
                    user,
                )
                forms_by_source[document_id] = form

            applied_any = False
            seen_fields: set[str] = set()
            for candidate in applicable:
                draft_field = F01_CANDIDATE_TO_DRAFT_FIELD.get(
                    candidate.field_name, candidate.field_name
                )
                if draft_field in seen_fields:
                    continue
                seen_fields.add(draft_field)
                value = self._normalized_confirmed_f01_value(
                    draft_field,
                    candidate.confirmed_value,
                )
                try:
                    payload = F01DraftUpdate.model_validate({draft_field: value})
                    await f01.update(
                        case_id,
                        form.form_instance_id,
                        FormCode.F01.value,
                        payload,
                        user,
                    )
                except (ValueError, AppError):
                    warning = "CONFIRMED_CODEX_F01_VALUE_INVALID_REQUIRES_CORRECTION"
                    if warning not in warnings:
                        warnings.append(warning)
                    continue
                await self.extraction_repository.apply_candidate(
                    candidate, form.form_instance_id
                )
                applied_any = True
            if applied_any:
                applied_form_ids.append(form.form_instance_id)
        return applied_form_ids

    async def _save_three_page_draft(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
    ) -> tuple[DocumentRecord, str]:
        """Save a confirmed-but-not-formal three-page snapshot in MinIO."""
        page_service = ReportPageService(self.session)
        data = await page_service.draft_pdf_data(
            case_id,
            report_id,
            user,
        )
        source = await page_service.filled_template_source_document(
            case_id,
            report_id,
            user,
        )
        source_mode = "STRUCTURED_DRAFT_OVERLAY"
        if source is None:
            pdf_bytes = build_pdf_safely(build_three_page_draft_pdf, data)
        else:
            if source.file_size_bytes > 30 * 1024 * 1024:
                raise AppError(
                    "FILLED_REPORT_SOURCE_TOO_LARGE",
                    "已填寫查估書來源超過 30 MB 草稿上限",
                    422,
                )
            if source.bucket_name != self.storage.bucket:
                raise AppError(
                    "FILLED_REPORT_STORAGE_BUCKET_MISMATCH",
                    "已填寫查估書來源的 MinIO bucket metadata 不一致",
                    422,
                )
            storage_response = await self.storage.download(source.object_key)
            source_bytes = await run_in_threadpool(
                _read_and_close_minio_response,
                storage_response,
            )
            pdf_bytes = build_pdf_safely(
                build_three_page_source_preserved_draft_pdf,
                source_bytes,
                source_is_user_upload=True,
            )
            source_mode = "FILLED_TEMPLATE_SOURCE_PRESERVED"
        group_id = uuid5(
            NAMESPACE_URL,
            f"land-valuation:{case_id}:{report_id}:draft-pages-1-3",
        )
        repository = DocumentRepository(self.session)
        checksum_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        existing = await repository.get_by_checksum(case_id, checksum_sha256)
        if existing is not None:
            if (
                existing.document_group_id == group_id
                and existing.document_type == "generated-draft-report"
                and existing.is_active
            ):
                return existing, source_mode
            raise AppError(
                "DRAFT_CONTENT_DUPLICATE",
                "相同草稿內容已存在於此案件的其他文件版本",
                409,
            )
        version_no = await repository.next_version(case_id, group_id)
        document_id = uuid4()
        filename = safe_filename(
            f"report_{report_id}_pages_1_3_CONFIRMED_DRAFT_v{version_no}.pdf"
        )
        object_key = build_generated_report_object_key(
            case_id,
            group_id,
            document_id,
            version_no,
            filename,
        )
        uploaded = await self.storage.upload(
            object_key,
            BytesIO(pdf_bytes),
            len(pdf_bytes),
            content_type="application/pdf",
        )
        try:
            await repository.deactivate_group(case_id, group_id)
            record = await repository.create(
                DocumentRecord(
                    document_id=document_id,
                    document_group_id=group_id,
                    case_id=case_id,
                    document_type="generated-draft-report",
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
            return record, source_mode
        except Exception:
            await self.storage.delete(object_key)
            raise

    async def _optional_ai_analysis(
        self,
        case_id: UUID,
        document_id: UUID,
        has_commercial_report: bool,
        user: User,
        warnings: list[str],
    ) -> None:
        settings = get_settings()
        if settings.ai_provider not in {"bedrock", "ollama"}:
            warning = "AI_FIELD_ANALYSIS_NOT_CONFIGURED_ONLY_OCR_CANDIDATES_USED"
            if warning not in warnings:
                warnings.append(warning)
            return
        # Every uploaded source may contain evidence for any official form.
        # Analyze the complete form set and leave a form empty when the source
        # contains no grounded evidence, rather than treating its report type
        # as a reason to skip the analysis entirely.
        del has_commercial_report
        form_codes = [
            FormCode.F01,
            FormCode.F02,
            FormCode.F02_RF,
            FormCode.F03,
            FormCode.F04,
            FormCode.S01,
        ]
        for form_code in form_codes:
            try:
                await FieldAnalysisService(self.session).analyze(
                    case_id,
                    document_id,
                    FieldAnalysisRequest(form_code=form_code),
                    user,
                )
            except AppError as exc:
                warning = f"AI_FIELD_ANALYSIS_SKIPPED_{exc.code}"
                if warning not in warnings:
                    warnings.append(warning)

    async def _apply_f03_candidates(
        self,
        case_id: UUID,
        form_id: UUID,
        user: User,
        warnings: list[str],
    ) -> None:
        candidates = list(
            (
                await self.session.scalars(
                    select(ExtractedFieldRecord)
                    .where(
                        ExtractedFieldRecord.case_id == case_id,
                        ExtractedFieldRecord.form_code == "F03",
                        ExtractedFieldRecord.field_status == "CONFIRMED",
                    )
                    .order_by(ExtractedFieldRecord.confirmed_at.desc())
                )
            ).all()
        )
        if not candidates:
            return
        fields: dict[str, object] = {}
        used: list[ExtractedFieldRecord] = []
        for candidate in candidates:
            if candidate.field_name in fields:
                continue
            if candidate.field_name == "valuation_base_date":
                fields["valuation_base_date"] = candidate.confirmed_value
                used.append(candidate)
            elif candidate.field_name == "benchmark_land_no":
                val_str = str(candidate.confirmed_value).strip()
                benchmarks = list(
                    (
                        await self.session.scalars(
                            select(BenchmarkLandRecord).where(
                                BenchmarkLandRecord.case_id == case_id,
                                BenchmarkLandRecord.is_active.is_(True),
                            )
                        )
                    ).all()
                )
                matched_benchmark = None
                for bm in benchmarks:
                    if bm.benchmark_land_no == val_str:
                        matched_benchmark = bm
                        break
                    bm_norm = re.sub(r"[^\w]", "", bm.benchmark_land_no)
                    val_norm = re.sub(r"[^\w]", "", val_str)
                    if (
                        bm_norm
                        and val_norm
                        and (
                            bm_norm == val_norm
                            or bm_norm in val_norm
                            or val_norm in bm_norm
                        )
                    ):
                        matched_benchmark = bm
                        break

                if matched_benchmark is None:
                    warnings.append("CONFIRMED_BENCHMARK_NUMBER_HAS_NO_CASE_MATCH")
                    continue
                fields["benchmark_land_id"] = matched_benchmark.benchmark_land_id
                used.append(candidate)


        if not fields:
            return
        try:
            await self.f03.update_draft(
                case_id,
                form_id,
                F03DraftUpdate.model_validate(fields),
                user,
            )
        except AppError as exc:
            if exc.code == "F03_REQUIRED_FIELDS":
                warnings.append("F03_REQUIRED_FIELDS_STILL_BLANK")
                return
            raise
        except Exception:
            warnings.append("CONFIRMED_F03_VALUE_INVALID_REQUIRES_CORRECTION")
            return
        for candidate in used:
            await self.extraction_repository.apply_candidate(candidate, form_id)

    async def _apply_confirmed_s01_candidates(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
        warnings: list[str],
    ) -> None:
        """Apply confirmed OCR/AI S01 candidates to the formal S01 page."""
        candidates = list(
            (
                await self.session.scalars(
                    select(ExtractedFieldRecord)
                    .where(
                        ExtractedFieldRecord.case_id == case_id,
                        ExtractedFieldRecord.form_code == "S01",
                        ExtractedFieldRecord.field_status == "CONFIRMED",
                        ExtractedFieldRecord.confirmed_value.is_not(None),
                    )
                    .order_by(ExtractedFieldRecord.confirmed_at.desc())
                )
            ).all()
        )
        if not candidates:
            return

        _, records = await self.pages._read_records(case_id, report_id, user)
        s01_form_id = records["S01"].form_instance_id
        if any(
            record.form_status != FormStatus.DRAFT.value
            for record in records.values()
        ):
            for record in records.values():
                record.form_status = FormStatus.DRAFT.value
                record.output_document_id = None
                record.updated_by_user_id = user.user_id
                await self.valuation.repository.save_form(record)

        current_page = await self.pages.get_s01(case_id, report_id, user)
        current_data = current_page.data.model_dump(mode="json")
        direct_map = {
            "administrative_area": "district_name",
            "zone_boundary_description": "district_boundary",
            "survey_date": "survey_date",
            "urban_plan_scope": "urban_plan_status",
            "land_use_zone_category": "land_use_zone",
            "building_coverage_ratio": "building_coverage_rate",
            "floor_area_ratio": "floor_area_ratio",
            "building_prohibition_status": "prohibited_building",
            "building_restriction_status": "restricted_building",
            "building_restriction_details": "restricted_building",
            "main_road_name": "main_road_name",
            "main_road_width_m": "main_road_width_m",
            "average_internal_road_width_m": "average_road_width_m",
            "internal_road_width_m": "average_road_width_m",
            "handler_name": "handler_name",
            "section_chief_name": "section_head_name",
            "director_name": "director_name",
            "appraiser_name": "appraiser_name",
        }
        observation_map = {
            "urban_plan_scope": "urban_plan_status",
            "land_use_zone_category": "land_use_zone",
            "building_coverage_ratio": "building_coverage_rate",
            "floor_area_ratio": "floor_area_ratio",
            "building_prohibition_status": "prohibited_building",
            "building_restriction_status": "restricted_building",
            "building_restriction_details": "restricted_building",
            "main_road_width_m": "main_road_width",
            "internal_road_width_m": "average_road_width",
            "average_internal_road_width_m": "average_road_width",
            "road_planning_development_level": "road_plan",
            "drainage_level": "drainage",
            "terrain_level": "terrain",
            "slope_level": "terrain",
            "consumer_market_proximity": "market_proximity",
            "major_station_distance_m": "mass_transit_proximity",
            "major_station_type": "mass_transit_proximity",
            "interchange_distance_m": "interchange_proximity",
            "commercial_facility_distance_m": "department_store",
            "commercial_facility_count": "department_store",
            "pollution_distance_m": "environmental_pollution",
            "wastewater_waste_facility_present": "waste_facility",
        }
        numeric_targets = {
            "building_coverage_rate",
            "floor_area_ratio",
            "main_road_width_m",
            "average_road_width_m",
        }
        direct_values: dict[str, object] = {}
        observations = list(current_data.get("observations") or [])
        by_code = {item.get("item_code"): item for item in observations}
        applied: list[ExtractedFieldRecord] = []

        for candidate in candidates:
            source = str(candidate.field_name)
            value: object = candidate.confirmed_value
            target = direct_map.get(source)
            if target == "survey_date":
                raw = str(value).strip().replace("/", "-")
                roc = re.fullmatch(r"(\d{2,3})年(\d{1,2})月(\d{1,2})日", str(value).strip())
                if roc:
                    raw = f"{int(roc.group(1)) + 1911:04d}-{int(roc.group(2)):02d}-{int(roc.group(3)):02d}"
                try:
                    value = date.fromisoformat(raw)
                except ValueError:
                    warnings.append("CONFIRMED_S01_SURVEY_DATE_INVALID_REQUIRES_CORRECTION")
                    continue
            elif target in numeric_targets:
                try:
                    value = Decimal(str(value).strip().replace(",", "").replace("%", ""))
                except (InvalidOperation, ValueError):
                    warnings.append("CONFIRMED_S01_NUMERIC_VALUE_INVALID_REQUIRES_CORRECTION")
                    continue
            if target is not None:
                direct_values[target] = value

            item_code = observation_map.get(source)
            if item_code in TEMPLATE_FACTOR_CODES:
                row = by_code.get(item_code, {"item_code": item_code})
                row.update({
                    "raw_value": value,
                    "source_type": "DOCUMENT_CONFIRMED",
                    "source_document_id": candidate.document_id,
                    "source_notes": "AI/OCR 候選內容經使用者確認",
                    "confirmed_by_user": True,
                })
                by_code[item_code] = row
            if target is not None or item_code in TEMPLATE_FACTOR_CODES:
                applied.append(candidate)

        if by_code:
            direct_values["observations"] = list(by_code.values())
        if not direct_values:
            return
        try:
            await self.pages.update_s01(
                case_id,
                report_id,
                S01DraftUpdate.model_validate(direct_values),
                user,
            )
        except (ValueError, AppError):
            warnings.append("CONFIRMED_S01_VALUE_INVALID_REQUIRES_CORRECTION")
            return
        for candidate in applied:
            await self.extraction_repository.apply_candidate(candidate, s01_form_id)

    async def _form_guidance(
        self,
        case_id: UUID,
        user: User,
        candidates: list[ExtractedFieldResponse],
    ) -> list[AutomatedFormGuidance]:
        forms = await self.valuation.list_forms(case_id, user)
        forms_by_code: dict[str, list] = defaultdict(list)
        for form in forms:
            forms_by_code[form.form_code].append(form)
        candidate_codes = {item.form_code for item in candidates}
        guidance_codes = [FormCode.F03.value]
        if FormCode.F01.value in forms_by_code or FormCode.F01.value in candidate_codes:
            guidance_codes.append(FormCode.F01.value)
        for code in sorted(candidate_codes):
            if code in FORM_REQUIREMENTS and code not in guidance_codes:
                guidance_codes.append(code)

        guidance: list[AutomatedFormGuidance] = []
        for code in guidance_codes:
            definition = FORM_REQUIREMENTS.get(code)
            if definition is None:
                continue
            related = [item for item in candidates if item.form_code == code]
            confirmed = {
                item.field_name
                for item in related
                if item.field_status in {"CONFIRMED", "APPLIED"}
            }
            pending = {
                item.field_name
                for item in related
                if item.field_status == "NEEDS_CONFIRMATION"
            }
            form = forms_by_code[code][0] if forms_by_code.get(code) else None
            values: dict = {}
            if form is not None:
                content = form.form_content
                if isinstance(content, dict) and isinstance(content.get("data"), dict):
                    values = content["data"]
            completed = {
                name for name, value in values.items() if value not in (None, "", [], {})
            }
            if code == FormCode.F03.value and "benchmark_land_no" in confirmed:
                completed.add("benchmark_land_id")
            completed.update(confirmed)
            required = set(definition.required_fields)
            missing = required - completed
            calculation_ready = bool(required) and not pending and not missing
            if pending:
                next_action = "CONFIRM_OR_REJECT_CANDIDATES"
            elif missing:
                next_action = "FILL_MISSING_REQUIRED_FIELDS"
            elif code == FormCode.F01.value:
                next_action = "CALL_F01_CALCULATE"
            else:
                next_action = "REVIEW_BEFORE_CALCULATION"
            form_id = None if form is None else form.form_instance_id
            base = (
                None
                if form_id is None
                else f"/api/v1/valuation/cases/{case_id}/forms/{form_id}/{code.lower()}"
            )
            guidance.append(
                AutomatedFormGuidance(
                    form_code=code,
                    form_instance_id=form_id,
                    required_fields=list(definition.required_fields),
                    confirmed_or_applied_fields=sorted(completed),
                    pending_confirmation_fields=sorted(pending),
                    missing_required_fields=sorted(missing),
                    calculation_ready=calculation_ready,
                    next_action=next_action,
                    fill_endpoint=base if code == FormCode.F01.value else None,
                    calculate_endpoint=(
                        None if base is None or code != FormCode.F01.value else f"{base}/calculate"
                    ),
                    validate_endpoint=(
                        None if base is None or code != FormCode.F01.value else f"{base}/validate"
                    ),
                )
            )
        return guidance

    async def _response(
        self,
        case_id: UUID,
        user: User,
        *,
        status: AutomatedWorkflowStatus,
        f03_form_instance_id: UUID,
        report_id: UUID | None,
        parcel_ids: list[UUID] | None = None,
        benchmark_land_ids: list[UUID] | None = None,
        document_results: list[AutomatedDocumentResult] | None = None,
        warnings: list[str] | None = None,
        ignored_duplicate_files: list[str] | None = None,
    ) -> AutomatedWorkflowResponse:
        case = await self.valuation.get_case(case_id, user)
        parcels = await self.valuation.list_parcels(case_id, user)
        benchmarks = await self.f03.list_benchmark_lands(case_id, user)
        # The workbench must always receive every active document and its latest
        # extraction.  Passing only the files from the most recent upload made
        # older candidates disappear from the UI even though they remained in
        # PostgreSQL.
        results = await self._document_results(case_id, user)
        candidates = [
            candidate
            for result in results
            if result.extraction is not None
            for candidate in result.extraction.candidates
        ]
        manual_field_values = {
            str(form.form_code): dict(
                (form.form_content or {}).get("manual_overrides") or {}
            )
            for form in await self.valuation.list_forms(case_id, user)
            if isinstance(form.form_content, dict)
            and isinstance(form.form_content.get("manual_overrides"), dict)
        }
        pending = sum(item.field_status == "NEEDS_CONFIRMATION" for item in candidates)
        draft_1_3 = None
        draft_1_6 = None
        if report_id is not None:
            base = f"/api/v1/valuation/cases/{case_id}/reports/{report_id}"
            draft_1_3 = f"{base}/draft-pages-1-3/download"
            draft_1_6 = f"{base}/draft-pages-1-6/download"
        form_guidance = await self._form_guidance(case_id, user, candidates)
        export_document = next(
            (
                item.document
                for item in reversed(results)
                if item.document.document_type == "candidate-confirmation-export"
                and item.document.is_active
            ),
            None,
        )
        current_warnings = list(dict.fromkeys(warnings or []))
        readiness_blockers: list[str] = []
        if report_id is not None:
            readiness = await ReportPageService(self.session).draft_readiness(
                case_id,
                report_id,
                user,
            )
            readiness_blockers = readiness.blocking_errors
        missing_items = self._workflow_missing_items(
            pending=pending,
            has_parcels=bool(parcels),
            has_benchmarks=bool(benchmarks),
            has_report=report_id is not None,
            land_use_type=case.land_use_type,
            readiness_blockers=readiness_blockers,
        )
        if pending:
            next_action = "REVIEW_CANDIDATES"
        elif any(item.missing_required_fields for item in form_guidance):
            next_action = "FILL_REQUIRED_FIELDS"
        elif any(item.calculation_ready for item in form_guidance):
            next_action = "RUN_FORM_CALCULATION"
        elif missing_items:
            next_action = "COMPLETE_WORKFLOW_REQUIREMENTS"
        else:
            next_action = "REVIEW_BEFORE_MANUAL_PDF_GENERATION"
        return AutomatedWorkflowResponse(
            status=status,
            case=CaseResponse.model_validate(case),
            parcel_ids=parcel_ids or [item.parcel_id for item in parcels],
            benchmark_land_ids=benchmark_land_ids
            or [item.benchmark_land_id for item in benchmarks],
            f03_form_instance_id=f03_form_instance_id,
            report_id=report_id,
            documents=results,
            candidates=candidates,
            pending_candidate_count=pending,
            blank_fields_remain=bool(missing_items),
            missing_items=missing_items,
            warnings=current_warnings,
            ignored_duplicate_files=ignored_duplicate_files or [],
            next_action=next_action,
            draft_pages_1_3_url=draft_1_3,
            draft_pages_1_6_url=draft_1_6,
            form_guidance=form_guidance,
            automatic_pdf_generation_enabled=False,
            automatic_confirmation_export_enabled=True,
            confirmation_export=(
                None
                if export_document is None
                else AutomatedConfirmationExport(
                    document_id=export_document.document_id,
                    filename=export_document.original_filename,
                    download_path=(
                        f"/api/v1/valuation/cases/{case_id}/documents/"
                        f"{export_document.document_id}/download"
                    ),
                )
            ),
            manual_field_values=manual_field_values,
        )
    @staticmethod
    def _workflow_missing_items(
        *,
        pending: int,
        has_parcels: bool,
        has_benchmarks: bool,
        has_report: bool,
        land_use_type: object,
        readiness_blockers: list[str],
    ) -> list[str]:
        missing: list[str] = []
        if pending:
            missing.append("AI_CANDIDATES_REQUIRE_CONFIRMATION")
        if not has_parcels:
            missing.append("PARCELS_REQUIRED")
        if not has_benchmarks:
            missing.append("BENCHMARK_LAND_REQUIRED")
        normalized_land_use = str(land_use_type or "").strip().upper()
        if not has_report and normalized_land_use in {"COMMERCIAL", "商業用地"}:
            missing.append("COMMERCIAL_REPORT_REQUIRED")
        missing.extend(readiness_blockers)
        return list(dict.fromkeys(missing))

    async def _document_results(
        self,
        case_id: UUID,
        user: User,
    ) -> list[AutomatedDocumentResult]:
        records = await self.documents.list_active_documents(case_id, user)
        results: list[AutomatedDocumentResult] = []
        for record in records:
            extraction = await self.extraction_repository.latest_for_document(
                case_id,
                record.document_id,
            )
            extraction_response = None
            if extraction is not None:
                candidates = await self.extraction_repository.list_candidates(
                    extraction.extraction_id
                )
                extraction_response = self._extraction_response(extraction, candidates)
            results.append(
                AutomatedDocumentResult(
                    document=DocumentResponse.model_validate(record),
                    detected_category=record.document_type,
                    category_source="SAVED_METADATA",
                    extraction=extraction_response,
                )
            )
        return results

    @staticmethod
    def _extraction_response(record, candidates) -> ExtractionResponse:
        response = ExtractionResponse.model_validate(record)
        response.candidates = [
            ExtractedFieldResponse.model_validate(candidate) for candidate in candidates
        ]
        return response
