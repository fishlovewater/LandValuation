from io import BytesIO
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.storage.service import StorageService
from app.storage.paths import build_generated_report_object_key
from app.valuation.documents.repository import DocumentRepository
from app.valuation.documents.service import safe_filename
from app.valuation.models import CaseEventRecord, DocumentRecord
from app.valuation.operations.report_builder import build_f03_report_pdf
from app.valuation.pdf_errors import build_pdf_safely
from app.valuation.operations.repository import OperationsRepository
from app.valuation.operations.schemas import ReportResponse
from app.valuation.service import ValuationService


class ReportService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageService,
        repository: OperationsRepository | None = None,
        document_repository: DocumentRepository | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.repository = repository or OperationsRepository(session)
        self.documents = document_repository or DocumentRepository(session)
        self.valuation = ValuationService(session)

    async def generate_f03(
        self,
        case_id: UUID,
        form_instance_id: UUID,
        user: User,
        request_id: UUID | None,
    ) -> ReportResponse:
        case = await self.valuation._owned_editable_case(case_id, user)
        form = await self.repository.get_form(case_id, form_instance_id)
        if form is None:
            raise ResourceNotFoundError("估價表")
        if form.form_code != "F03":
            raise AppError("FORM_TYPE_MISMATCH", "此報表端點只接受 F03 表單", 422)
        if form.form_status not in {"READY", "CHECKED", "FINAL"}:
            raise AppError(
                "FORM_NOT_READY",
                "F03 必須先完成計算、通過檢核並提交為 READY 才能產生正式 PDF",
                409,
            )

        if request_id is not None:
            event = await self.repository.event_for_request(
                case_id, "F03_REPORT_GENERATED", request_id
            )
            if event is not None:
                document_id = UUID(event.event_data["document_id"])
                existing = await self.documents.get(case_id, document_id)
                if existing is not None:
                    return self.response(
                        existing,
                        form_instance_id,
                        UUID(event.event_data["validation_run_id"]),
                        UUID(event.event_data["calculation_id"]),
                        request_id,
                    )

        draft = await self.repository.get_f03_draft(case_id, form_instance_id)
        if draft is None:
            raise ResourceNotFoundError("F03 草稿")
        calculation = await self.repository.latest_calculation(case_id, form_instance_id)
        if calculation is None:
            raise AppError("CALCULATION_REQUIRED", "請先執行 F03 計算", 409)
        validation = await self.repository.latest_validation_run(case_id, form_instance_id)
        if validation is None or validation.run_status != "COMPLETED":
            raise AppError("VALIDATION_REQUIRED", "請先執行 F03 製作前檢核", 409)
        if validation.failed_count > 0:
            raise AppError(
                "REPORT_BLOCKED_BY_VALIDATION",
                "檢核仍有 ERROR，正式 PDF 已阻擋；請修正後重新計算與檢核",
                409,
                {"validation_run_id": str(validation.validation_run_id)},
            )
        ruleset_snapshot = validation.ruleset_snapshot or {}
        if ruleset_snapshot.get("calculation_id") != str(calculation.valuation_id):
            raise AppError(
                "VALIDATION_STALE",
                "檢核結果不是針對目前最新計算，請重新檢核",
                409,
            )

        benchmark_land = await self.repository.get_benchmark_land(
            case_id, draft.benchmark_land_id
        )
        if benchmark_land is None:
            raise AppError("F03_BENCHMARK_CONFLICT", "找不到 F03 比準地", 422)
        parcel = await self.repository.get_parcel(case_id, benchmark_land.parcel_id)
        if parcel is None:
            raise AppError("F03_PARCEL_CONFLICT", "找不到 F03 比準地宗地", 422)

        existing_output = (
            None
            if form.output_document_id is None
            else await self.documents.get(case_id, form.output_document_id)
        )
        group_id = (
            existing_output.document_group_id if existing_output is not None else uuid4()
        )
        version_no = await self.documents.next_version(case_id, group_id)
        document_id = uuid4()
        filename = safe_filename(f"F03_{case.case_no}_v{version_no}.pdf")
        object_key = build_generated_report_object_key(
            case_id, group_id, document_id, version_no, filename
        )
        snapshot = calculation.calculation_snapshot

        pdf_bytes = build_pdf_safely(
            build_f03_report_pdf,
            {
                "case_no": case.case_no,
                "case_title": case.case_title,
                "valuation_base_date": draft.valuation_base_date.isoformat(),
                "city_code": case.city_code,
                "district_code": case.district_code,
                "form_version": form.version_no,
                "benchmark_land_no": benchmark_land.benchmark_land_no,
                "price_zone_no": benchmark_land.price_zone_no,
                "parcel_display": (
                    f"{parcel.section_name}／{parcel.subsection_name or '—'}／{parcel.land_no}"
                ),
                "area_sqm": format(parcel.area_sqm, "f"),
                "comparison_price": (
                    None if draft.comparison_price is None else format(draft.comparison_price, "f")
                ),
                "comparison_weight": format(draft.comparison_weight, "f"),
                "income_price": (
                    None if draft.income_price is None else format(draft.income_price, "f")
                ),
                "income_weight": format(draft.income_weight, "f"),
                "benchmark_land_price": format(calculation.unit_price, "f"),
                "formula_version": snapshot["formula_version"],
                "calculation_id": calculation.valuation_id,
                "ruleset_version": (
                    f"{ruleset_snapshot.get('rule_set_code')}:v{ruleset_snapshot.get('version_no')}"
                ),
                "validation_summary": (
                    f"{validation.passed_count}／{validation.warning_count}／{validation.failed_count}"
                ),
                "validation_run_id": validation.validation_run_id,
                "request_id": request_id,
            }
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
                    document_type="generated-report",
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
            form.output_document_id = document.document_id
            form.updated_by_user_id = user.user_id
            await self.repository.save_form(form)
            await self.repository.create_event(
                CaseEventRecord(
                    case_id=case_id,
                    event_type="F03_REPORT_GENERATED",
                    event_data={
                        "document_id": str(document.document_id),
                        "form_instance_id": str(form_instance_id),
                        "calculation_id": str(calculation.valuation_id),
                        "validation_run_id": str(validation.validation_run_id),
                        "version_no": version_no,
                        "object_key": document.object_key,
                    },
                    occurred_by_user_id=user.user_id,
                    request_id=request_id,
                )
            )
        except Exception:
            await self.storage.delete(object_key)
            raise
        return self.response(
            document,
            form_instance_id,
            validation.validation_run_id,
            calculation.valuation_id,
            request_id,
        )

    async def get_document(
        self, case_id: UUID, document_id: UUID, user: User
    ) -> DocumentRecord:
        await self.valuation.get_case(case_id, user)
        document = await self.documents.get(case_id, document_id)
        if document is None or document.document_type != "generated-report":
            raise ResourceNotFoundError("F03 PDF 報表")
        return document

    @staticmethod
    def response(
        document: DocumentRecord,
        form_instance_id: UUID,
        validation_run_id: UUID,
        calculation_id: UUID,
        request_id: UUID | None,
    ) -> ReportResponse:
        return ReportResponse(
            document_id=document.document_id,
            case_id=document.case_id,
            form_instance_id=form_instance_id,
            validation_run_id=validation_run_id,
            calculation_id=calculation_id,
            filename=document.original_filename,
            mime_type=document.mime_type,
            version_no=document.version_no,
            bucket_name=document.bucket_name,
            object_key=document.object_key,
            checksum_sha256=document.checksum_sha256,
            file_size_bytes=document.file_size_bytes,
            download_path=(
                f"/api/v1/valuation/cases/{document.case_id}/reports/"
                f"{document.document_id}/download"
            ),
            request_id=request_id,
        )
