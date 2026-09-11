from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.background import BackgroundTasks
from fastapi.responses import StreamingResponse

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.core.config import get_settings
from app.core.document_text_preview import (
    DocumentTextPreview,
    DocumentTextPreviewTooLargeError,
    preview_storage_docx,
)
from app.core.exceptions import AppError, StorageError
from app.core.spreadsheet_preview import (
    SpreadsheetPreview,
    SpreadsheetPreviewTooLargeError,
    preview_storage_xlsx,
)
from app.storage.dependencies import Storage
from app.valuation.documents.schemas import (
    DocumentCategory,
    DocumentCategoryUpdate,
    DocumentResponse,
)
from app.valuation.documents.service import DocumentService

router = APIRouter()

DocumentUploader = Annotated[User, Depends(require_permissions("document.upload"))]
DocumentDownloader = Annotated[User, Depends(require_permissions("document.download"))]
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post(
    "/cases/{case_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    case_id: UUID,
    session: DbSession,
    storage: Storage,
    user: DocumentUploader,
    category: Annotated[DocumentCategory, Form()],
    file: Annotated[UploadFile, File()],
    document_group_id: Annotated[UUID | None, Form()] = None,
) -> DocumentResponse:
    record = await DocumentService(session, storage).upload(
        case_id,
        category,
        file,
        user,
        document_group_id,
    )
    return DocumentResponse.model_validate(record)


@router.get(
    "/cases/{case_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_documents(
    case_id: UUID,
    session: DbSession,
    storage: Storage,
    user: DocumentDownloader,
) -> list[DocumentResponse]:
    records = await DocumentService(session, storage).list_documents(case_id, user)
    return [DocumentResponse.model_validate(record) for record in records]


@router.delete(
    "/cases/{case_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_source_document(
    case_id: UUID,
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user: DocumentUploader,
) -> Response:
    await DocumentService(session, storage).delete_source_document(
        case_id, document_id, user
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/cases/{case_id}/documents/{document_id}/category",
    response_model=DocumentResponse,
)
async def reclassify_source_document(
    case_id: UUID,
    document_id: UUID,
    payload: DocumentCategoryUpdate,
    session: DbSession,
    storage: Storage,
    user: DocumentUploader,
) -> DocumentResponse:
    record = await DocumentService(session, storage).reclassify_source_document(
        case_id, document_id, payload.category, user
    )
    return DocumentResponse.model_validate(record)


@router.get("/cases/{case_id}/documents/{document_id}/download")
async def download_document(
    case_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    session: DbSession,
    storage: Storage,
    user: DocumentDownloader,
):
    service = DocumentService(session, storage)
    record = await service.get_document(case_id, document_id, user)
    response = await storage.download(record.object_key)

    def close_response() -> None:
        response.close()
        response.release_conn()

    background_tasks.add_task(close_response)
    encoded = quote(record.original_filename)
    return StreamingResponse(
        response.stream(64 * 1024),
        media_type=record.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        background=background_tasks,
    )


@router.get(
    "/cases/{case_id}/documents/{document_id}/spreadsheet-preview",
    response_model=SpreadsheetPreview,
)
async def preview_spreadsheet_document(
    case_id: UUID,
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user: DocumentDownloader,
) -> SpreadsheetPreview:
    record = await DocumentService(session, storage).get_document(case_id, document_id, user)
    if record.mime_type != "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        raise AppError("PREVIEW_NOT_SUPPORTED", "此文件不是可預覽的 Excel 活頁簿", 415)
    max_bytes = get_settings().document_preview_max_bytes
    if record.file_size_bytes > max_bytes:
        raise AppError("PREVIEW_TOO_LARGE", "Excel 檔案過大，請下載後查看完整內容", 413)
    try:
        return await preview_storage_xlsx(storage, record.object_key, max_bytes=max_bytes)
    except SpreadsheetPreviewTooLargeError as exc:
        raise AppError("PREVIEW_TOO_LARGE", "Excel 檔案過大，請下載後查看完整內容", 413) from exc
    except StorageError as exc:
        raise AppError("DOCUMENT_OBJECT_MISSING", "文件資料存在，但目前無法從物件儲存取得檔案", 404) from exc


@router.get(
    "/cases/{case_id}/documents/{document_id}/text-preview",
    response_model=DocumentTextPreview,
)
async def preview_text_document(
    case_id: UUID,
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user: DocumentDownloader,
) -> DocumentTextPreview:
    record = await DocumentService(session, storage).get_document(case_id, document_id, user)
    if record.mime_type != DOCX_MIME_TYPE:
        raise AppError("PREVIEW_NOT_SUPPORTED", "此文件不是可提供文字預覽的 DOCX 文件", 415)
    max_bytes = get_settings().document_preview_max_bytes
    if record.file_size_bytes > max_bytes:
        raise AppError("PREVIEW_TOO_LARGE", "DOCX 檔案過大，請下載後查看完整內容", 413)
    try:
        return await preview_storage_docx(storage, record.object_key, max_bytes=max_bytes)
    except DocumentTextPreviewTooLargeError as exc:
        raise AppError("PREVIEW_TOO_LARGE", "DOCX 檔案過大，請下載後查看完整內容", 413) from exc
    except StorageError as exc:
        raise AppError("DOCUMENT_OBJECT_MISSING", "文件資料存在，但目前無法從物件儲存取得檔案", 404) from exc
