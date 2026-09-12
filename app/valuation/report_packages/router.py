from io import BytesIO
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.core.exceptions import AppError
from app.storage.dependencies import Storage
from app.valuation.report_packages.schemas import (
    ReportPackageCreate,
    ReportPackageResponse,
    ReportDraftReadinessResponse,
    ReportProgressResponse,
    ReportRequirementsResponse,
    ReportType,
    ReportTypeResponse,
)
from app.valuation.report_packages.draft_pdf_builder import (
    build_three_page_draft_pdf,
    build_three_page_source_preserved_draft_pdf,
)
from app.valuation.report_packages.complete_draft_pdf_builder import (
    build_six_page_draft_pdf,
)
from app.valuation.pdf_errors import build_pdf_safely
from app.valuation.report_packages.page_schemas import (
    F02DraftUpdate,
    F02PageResponse,
    F02RFDraftUpdate,
    F02RFPageResponse,
    S01DraftUpdate,
    S01PageResponse,
)
from app.valuation.report_packages.page_service import ReportPageService
from app.valuation.report_packages.formal_schemas import (
    FormalCalculationRequest,
    FormalCalculationResponse,
    FormalReportRequest,
    FormalReportResponse,
    FormalValidationResponse,
    FormalWorkflowStatusResponse,
    TemplateExportResponse,
)
from app.valuation.report_packages.formal_service import FormalReportService
from app.valuation.report_packages.formal_xlsx_builder import XLSX_MIME_TYPE
from app.valuation.report_packages.service import ReportPackageService

router = APIRouter()

MAX_MAP_PREVIEW_BYTES = 30 * 1024 * 1024


def _read_and_close_minio_response(response) -> bytes:
    try:
        return response.read()
    finally:
        response.close()
        release = getattr(response, "release_conn", None)
        if callable(release):
            release()

ValuationReader = Annotated[User, Depends(require_permissions("valuation.read"))]
ValuationEditor = Annotated[User, Depends(require_permissions("valuation.update"))]
ReportPreviewDownloader = Annotated[
    User,
    Depends(require_permissions("document.download")),
]


def request_uuid(request: Request) -> UUID | None:
    try:
        return UUID(str(request.state.request_id))
    except (ValueError, TypeError, AttributeError):
        return None


@router.get("/report-types", response_model=list[ReportTypeResponse])
async def list_report_types(user: ValuationReader) -> list[ReportTypeResponse]:
    del user
    return ReportPackageService.list_report_types()


@router.get(
    "/report-types/{report_type}/requirements",
    response_model=ReportRequirementsResponse,
)
async def get_report_requirements(
    report_type: ReportType,
    user: ValuationReader,
) -> ReportRequirementsResponse:
    del user
    return ReportPackageService.requirements(report_type)


@router.post(
    "/cases/{case_id}/report-packages",
    response_model=ReportPackageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_report_package(
    case_id: UUID,
    payload: ReportPackageCreate,
    session: DbSession,
    user: ValuationEditor,
) -> ReportPackageResponse:
    return await ReportPackageService(session).create(case_id, payload, user)


@router.get(
    "/cases/{case_id}/reports/{report_id}",
    response_model=ReportPackageResponse,
)
async def get_report_package(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> ReportPackageResponse:
    return await ReportPackageService(session).get(case_id, report_id, user)


@router.get(
    "/cases/{case_id}/report-progress",
    response_model=ReportProgressResponse,
)
async def get_report_progress(
    case_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> ReportProgressResponse:
    return await ReportPackageService(session).progress(case_id, user)


@router.get(
    "/cases/{case_id}/reports/{report_id}/pages/S01",
    response_model=S01PageResponse,
)
async def get_s01_report_page(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> S01PageResponse:
    return await ReportPageService(session).get_s01(case_id, report_id, user)


@router.patch(
    "/cases/{case_id}/reports/{report_id}/pages/S01",
    response_model=S01PageResponse,
)
async def update_s01_report_page(
    case_id: UUID,
    report_id: UUID,
    payload: S01DraftUpdate,
    session: DbSession,
    user: ValuationEditor,
) -> S01PageResponse:
    return await ReportPageService(session).update_s01(
        case_id, report_id, payload, user
    )


@router.get(
    "/cases/{case_id}/reports/{report_id}/pages/F02-RF",
    response_model=F02RFPageResponse,
)
async def get_f02_rf_report_page(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> F02RFPageResponse:
    return await ReportPageService(session).get_f02_rf(case_id, report_id, user)


@router.patch(
    "/cases/{case_id}/reports/{report_id}/pages/F02-RF",
    response_model=F02RFPageResponse,
)
async def update_f02_rf_report_page(
    case_id: UUID,
    report_id: UUID,
    payload: F02RFDraftUpdate,
    session: DbSession,
    user: ValuationEditor,
) -> F02RFPageResponse:
    return await ReportPageService(session).update_f02_rf(
        case_id, report_id, payload, user
    )


@router.post(
    "/cases/{case_id}/reports/{report_id}/pages/F02-RF/apply-extracted-candidates",
    response_model=F02RFPageResponse,
    summary="將 AI 已確認因素欄位自動套用至 F02-RF 表單",
    description=(
        "將文件擷取流程（analyze-fields + confirm）中已確認的 F02-RF 因素等級，"
        "一次性寫入 F02-RF 表單草稿，並將候選欄位狀態更新為 APPLIED。"
    ),
)
async def apply_extracted_candidates_to_f02_rf(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    user: ValuationEditor,
) -> F02RFPageResponse:
    return await ReportPageService(session).apply_extracted_candidates(
        case_id, report_id, user
    )


@router.get(
    "/cases/{case_id}/reports/{report_id}/pages/F02",
    response_model=F02PageResponse,
)
async def get_f02_report_page(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> F02PageResponse:
    return await ReportPageService(session).get_f02(case_id, report_id, user)


@router.patch(
    "/cases/{case_id}/reports/{report_id}/pages/F02",
    response_model=F02PageResponse,
)
async def update_f02_report_page(
    case_id: UUID,
    report_id: UUID,
    payload: F02DraftUpdate,
    session: DbSession,
    user: ValuationEditor,
) -> F02PageResponse:
    return await ReportPageService(session).update_f02(
        case_id, report_id, payload, user
    )


@router.get(
    "/cases/{case_id}/reports/{report_id}/draft-pages-1-3/download",
    response_class=StreamingResponse,
)
async def download_three_page_draft_preview(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    storage: Storage,
    user: ReportPreviewDownloader,
):
    service = ReportPageService(session)
    data = await service.draft_pdf_data(case_id, report_id, user)
    source = await service.filled_template_source_document(
        case_id,
        report_id,
        user,
    )
    source_mode = "STRUCTURED_DRAFT_OVERLAY"
    if source is None:
        pdf_bytes = build_pdf_safely(build_three_page_draft_pdf, data)
    else:
        if source.file_size_bytes > MAX_MAP_PREVIEW_BYTES:
            raise AppError(
                "FILLED_REPORT_SOURCE_TOO_LARGE",
                "已填寫查估書來源超過 30 MB 預覽上限",
                422,
            )
        if source.bucket_name != storage.bucket:
            raise AppError(
                "FILLED_REPORT_STORAGE_BUCKET_MISMATCH",
                "已填寫查估書來源的 MinIO bucket metadata 不一致",
                422,
            )
        response = await storage.download(source.object_key)
        source_bytes = await run_in_threadpool(_read_and_close_minio_response, response)
        pdf_bytes = build_pdf_safely(
            build_three_page_source_preserved_draft_pdf,
            source_bytes,
            source_is_user_upload=True,
        )
        source_mode = "FILLED_TEMPLATE_SOURCE_PRESERVED"
    filename = f"report_{report_id}_pages_1_3_DRAFT.pdf"
    encoded = quote(filename)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "X-Report-Status": "DRAFT",
            "X-Report-Scope": "PAGES_1_3_ONLY",
            "X-Report-Source-Mode": source_mode,
        },
    )


@router.get(
    "/cases/{case_id}/reports/{report_id}/draft-readiness",
    response_model=ReportDraftReadinessResponse,
)
async def get_report_draft_readiness(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> ReportDraftReadinessResponse:
    return await ReportPageService(session).draft_readiness(
        case_id, report_id, user
    )


@router.get(
    "/cases/{case_id}/reports/{report_id}/draft-pages-1-6/download",
    response_class=StreamingResponse,
)
async def download_six_page_draft_preview(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    storage: Storage,
    user: ReportPreviewDownloader,
):
    service = ReportPageService(session)
    data = await service.draft_pdf_data(case_id, report_id, user)
    records = await service.draft_map_documents(case_id, report_id, user)
    map_documents: dict[str, dict] = {}
    for document_type, record in records.items():
        if record.file_size_bytes > MAX_MAP_PREVIEW_BYTES:
            raise AppError(
                "MAP_PREVIEW_FILE_TOO_LARGE",
                f"{document_type} 超過六頁草稿預覽的 30 MB 上限",
                422,
            )
        if record.bucket_name != storage.bucket:
            raise AppError(
                "MAP_STORAGE_BUCKET_MISMATCH",
                f"{document_type} 的 MinIO bucket metadata 不一致",
                422,
            )
        response = await storage.download(record.object_key)
        content = await run_in_threadpool(_read_and_close_minio_response, response)
        map_documents[document_type] = {
            "filename": record.original_filename,
            "mime_type": record.mime_type,
            "uploaded_at": record.uploaded_at.isoformat(),
            "content": content,
        }

    pdf_bytes = build_pdf_safely(build_six_page_draft_pdf, data, map_documents)
    filename = f"report_{report_id}_pages_1_6_DRAFT.pdf"
    encoded = quote(filename)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "X-Report-Status": "DRAFT",
            "X-Report-Scope": "PAGES_1_6_WITH_UPLOADED_MAPS_OR_PLACEHOLDERS",
        },
    )


@router.post(
    "/cases/{case_id}/reports/{report_id}/formal-calculation",
    response_model=FormalCalculationResponse,
    summary="依已發布規則計算 F02-RF 與 F02",
)
async def calculate_complete_report(
    case_id: UUID,
    report_id: UUID,
    payload: FormalCalculationRequest,
    session: DbSession,
    user: ValuationEditor,
) -> FormalCalculationResponse:
    del payload
    return await FormalReportService(session).calculate(case_id, report_id, user)


@router.get(
    "/cases/{case_id}/reports/{report_id}/formal-status",
    response_model=FormalWorkflowStatusResponse,
    summary="讀取既有正式檢核與報告成果",
)
async def get_formal_workflow_status(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    storage: Storage,
    user: ValuationReader,
) -> FormalWorkflowStatusResponse:
    return await FormalReportService(session, storage).status(case_id, report_id, user)


@router.post(
    "/cases/{case_id}/reports/{report_id}/formal-validation",
    response_model=FormalValidationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="執行整份六頁正式檢核",
)
async def validate_complete_report(
    case_id: UUID,
    report_id: UUID,
    request: Request,
    session: DbSession,
    storage: Storage,
    user: ValuationEditor,
) -> FormalValidationResponse:
    return await FormalReportService(session, storage).validate(
        case_id, report_id, user, request_uuid(request)
    )



@router.post(
    "/cases/{case_id}/reports/{report_id}/template-exports",
    response_model=list[TemplateExportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="產生三份正式 Excel 範本成果",
)
async def generate_template_exports(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    storage: Storage,
    user: ValuationEditor,
) -> list[TemplateExportResponse]:
    return await FormalReportService(session, storage).generate_template_exports(
        case_id, report_id, user
    )


@router.post(
    "/cases/{case_id}/reports/{report_id}/formal-pdf",
    response_model=FormalReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="產生並保存正式六頁 PDF",
)
async def generate_complete_report(
    case_id: UUID,
    report_id: UUID,
    payload: FormalReportRequest,
    request: Request,
    session: DbSession,
    storage: Storage,
    user: ValuationEditor,
) -> FormalReportResponse:
    return await FormalReportService(session, storage).generate(
        case_id,
        report_id,
        set(payload.acknowledged_warning_codes),
        user,
        request_uuid(request),
    )


@router.get("/cases/{case_id}/complete-reports/{document_id}/download")
async def download_complete_report(
    case_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    session: DbSession,
    storage: Storage,
    user: ReportPreviewDownloader,
):
    document = await FormalReportService(session, storage).get_generated_document(
        case_id, document_id, user
    )
    response = await storage.download(document.object_key)

    def close_response() -> None:
        response.close()
        release = getattr(response, "release_conn", None)
        if callable(release):
            release()

    background_tasks.add_task(close_response)
    encoded = quote(document.original_filename)
    return StreamingResponse(
        response.stream(64 * 1024),
        media_type=document.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        background=background_tasks,
    )


@router.get("/cases/{case_id}/reports/{report_id}/formal-xlsx/download")
async def download_formal_report_xlsx(
    case_id: UUID,
    report_id: UUID,
    session: DbSession,
    user: ReportPreviewDownloader,
):
    xlsx_bytes, filename = await FormalReportService(session).export_xlsx(
        case_id, report_id, user
    )
    encoded = quote(filename)
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type=XLSX_MIME_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "X-Report-Status": "FINAL",
            "X-Report-Format": "STRUCTURED_DATA_EXPORT",
        },
    )
