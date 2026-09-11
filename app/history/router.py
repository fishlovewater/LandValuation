from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.auth.dependencies import CurrentUser, DbSession
from app.core.document_text_preview import (
    DocumentTextPreview,
    DocumentTextPreviewTooLargeError,
    preview_storage_docx,
)
from app.core.exceptions import AppError, StorageError
from app.core.config import get_settings
from app.history.schemas import (
    DateField,
    HistoryCaseDetail,
    HistoryCasePage,
    HistoryResult,
    HistorySearchParams,
    HistorySort,
    SortOrder,
)
from app.history.service import HistoryService
from app.core.spreadsheet_preview import (
    XLS_MIME_TYPE,
    XLSX_MIME_TYPE,
    SpreadsheetPreview,
    SpreadsheetPreviewTooLargeError,
    preview_storage_spreadsheet,
)
from app.storage.dependencies import Storage

router = APIRouter(prefix="/history", tags=["history"])
TEST_UI = Path(__file__).with_name("test_ui") / "index.html"
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/test-ui", include_in_schema=False)
async def history_test_ui():
    if get_settings().app_env.lower() != "development":
        raise AppError("RESOURCE_NOT_FOUND", "找不到指定的頁面", 404)
    return FileResponse(TEST_UI, media_type="text/html; charset=utf-8")


@router.get("/cases", response_model=HistoryCasePage)
async def search_cases(
    session: DbSession,
    user: CurrentUser,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    city_code: Annotated[str | None, Query(max_length=20)] = None,
    district_code: Annotated[str | None, Query(max_length=20)] = None,
    section_name: Annotated[str | None, Query(max_length=100)] = None,
    result: HistoryResult | None = None,
    date_field: DateField = "updated_at",
    date_from: date | None = None,
    date_to: date | None = None,
    sort: HistorySort = "updated_at",
    order: SortOrder = "desc",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HistoryCasePage:
    params = HistorySearchParams(
        keyword=keyword,
        city_code=city_code,
        district_code=district_code,
        section_name=section_name,
        result=result,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        order=order,
        offset=offset,
        limit=limit,
    )
    return await HistoryService(session).search(params, user)


@router.get("/cases/{case_id}", response_model=HistoryCaseDetail)
async def get_case_history(
    case_id: UUID,
    session: DbSession,
    user: CurrentUser,
) -> HistoryCaseDetail:
    return await HistoryService(session).detail(case_id, user)


@router.get("/documents/{document_id}/download")
async def download_history_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    session: DbSession,
    storage: Storage,
    user: CurrentUser,
):
    document = await HistoryService(session).document(document_id, user)
    try:
        response = await storage.download(document["object_key"])
    except StorageError as exc:
        raise AppError(
            "DOCUMENT_OBJECT_MISSING",
            "文件目前無法下載，請稍後再試。",
            404,
        ) from exc

    def close_response() -> None:
        response.close()
        response.release_conn()

    background_tasks.add_task(close_response)
    encoded = quote(document["original_filename"])
    return StreamingResponse(
        response.stream(64 * 1024),
        media_type=document["mime_type"],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        background=background_tasks,
    )


@router.get(
    "/documents/{document_id}/spreadsheet-preview",
    response_model=SpreadsheetPreview,
)
async def preview_history_spreadsheet(
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user: CurrentUser,
) -> SpreadsheetPreview:
    document = await HistoryService(session).document(document_id, user)
    if document["mime_type"] not in {XLSX_MIME_TYPE, XLS_MIME_TYPE}:
        raise AppError("PREVIEW_NOT_SUPPORTED", "此文件不是可預覽的 Excel 活頁簿", 415)
    max_bytes = get_settings().document_preview_max_bytes
    if document["file_size_bytes"] > max_bytes:
        raise AppError("PREVIEW_TOO_LARGE", "Excel 檔案過大，請下載後查看完整內容", 413)
    try:
        return await preview_storage_spreadsheet(
            storage,
            document["object_key"],
            mime_type=document["mime_type"],
            max_bytes=max_bytes,
        )
    except SpreadsheetPreviewTooLargeError as exc:
        raise AppError("PREVIEW_TOO_LARGE", "Excel 檔案過大，請下載後查看完整內容", 413) from exc
    except StorageError as exc:
        raise AppError("DOCUMENT_OBJECT_MISSING", "文件目前無法讀取，請稍後再試。", 404) from exc


@router.get(
    "/documents/{document_id}/text-preview",
    response_model=DocumentTextPreview,
)
async def preview_history_text_document(
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user: CurrentUser,
) -> DocumentTextPreview:
    document = await HistoryService(session).document(document_id, user)
    if document["mime_type"] != DOCX_MIME_TYPE:
        raise AppError("PREVIEW_NOT_SUPPORTED", "此文件不是可提供文字預覽的 DOCX 文件", 415)
    max_bytes = get_settings().document_preview_max_bytes
    if document["file_size_bytes"] > max_bytes:
        raise AppError("PREVIEW_TOO_LARGE", "DOCX 檔案過大，請下載後查看完整內容", 413)
    try:
        return await preview_storage_docx(storage, document["object_key"], max_bytes=max_bytes)
    except DocumentTextPreviewTooLargeError as exc:
        raise AppError("PREVIEW_TOO_LARGE", "DOCX 檔案過大，請下載後查看完整內容", 413) from exc
    except StorageError as exc:
        raise AppError("DOCUMENT_OBJECT_MISSING", "文件目前無法讀取，請稍後再試。", 404) from exc
