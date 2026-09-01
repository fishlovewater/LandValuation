from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.background import BackgroundTasks
from fastapi.responses import StreamingResponse

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.storage.dependencies import Storage
from app.valuation.documents.schemas import DocumentCategory, DocumentResponse
from app.valuation.documents.service import DocumentService

router = APIRouter()

DocumentUploader = Annotated[User, Depends(require_permissions("document.upload"))]
DocumentDownloader = Annotated[User, Depends(require_permissions("document.download"))]


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
