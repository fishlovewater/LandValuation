from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.auth.dependencies import CurrentUser, DbSession
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
from app.storage.dependencies import Storage

router = APIRouter(prefix="/history", tags=["history"])
TEST_UI = Path(__file__).with_name("test_ui") / "index.html"


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
            "文件資料存在，但目前無法從物件儲存取得檔案",
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
