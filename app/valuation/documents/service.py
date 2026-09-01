import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.storage.service import StorageService
from app.valuation.documents.repository import DocumentRepository
from app.valuation.documents.schemas import DocumentCategory
from app.valuation.models import DocumentRecord
from app.valuation.service import ValuationService

SAFE_FILENAME_PATTERN = re.compile(r"[^\w.()\-\u4e00-\u9fff]+", re.UNICODE)
MAP_DOCUMENT_CATEGORIES = {
    DocumentCategory.MAP_SECTION_SKETCH,
    DocumentCategory.MAP_ZONING,
    DocumentCategory.MAP_LAND_VALUE_SECTION,
}
MAP_PREVIEW_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
}


def safe_filename(filename: str | None) -> str:
    original = Path(filename or "upload.bin").name
    cleaned = SAFE_FILENAME_PATTERN.sub("_", original).strip("._")
    return cleaned[:180] or "upload.bin"


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageService,
        repository: DocumentRepository | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.repository = repository or DocumentRepository(session)
        self.valuation = ValuationService(session)

    async def upload(
        self,
        case_id: UUID,
        category: DocumentCategory,
        file: UploadFile,
        user: User,
        document_group_id: UUID | None = None,
    ) -> DocumentRecord:
        await self.valuation._owned_editable_case(case_id, user)
        if not file.content_type:
            raise AppError("MIME_TYPE_REQUIRED", "上傳檔案必須提供 MIME type", 422)
        if (
            category in MAP_DOCUMENT_CATEGORIES
            and file.content_type.lower() not in MAP_PREVIEW_MIME_TYPES
        ):
            raise AppError(
                "MAP_MIME_TYPE_UNSUPPORTED",
                "三張正式附圖只接受 PDF、PNG 或 JPEG",
                422,
            )

        group_id = document_group_id or uuid4()
        if document_group_id is not None:
            latest = await self.repository.latest_in_group(case_id, group_id)
            if latest is None:
                raise ResourceNotFoundError("文件版本群組")
            if latest.document_type != category.value:
                raise AppError(
                    "DOCUMENT_CATEGORY_CONFLICT",
                    "新版本的文件類型必須與原文件一致",
                    409,
                )

        version_no = await self.repository.next_version(case_id, group_id)
        document_id = uuid4()
        filename = safe_filename(file.filename)
        object_key = (
            f"cases/{case_id}/{category.value}/{group_id}/"
            f"v{version_no}/{document_id}_{filename}"
        )

        await file.seek(0)
        file.file.seek(0, 2)
        length = file.file.tell()
        file.file.seek(0)
        if length <= 0:
            raise AppError("EMPTY_FILE", "不可上傳空白檔案", 422)

        uploaded = await self.storage.upload(
            object_key,
            file.file,
            length,
            content_type=file.content_type,
        )
        try:
            await self.repository.deactivate_group(case_id, group_id)
            record = DocumentRecord(
                document_id=document_id,
                document_group_id=group_id,
                case_id=case_id,
                document_type=category.value,
                original_filename=Path(file.filename or filename).name[:255],
                mime_type=file.content_type,
                bucket_name=str(uploaded["bucket_name"]),
                object_key=str(uploaded["object_key"]),
                checksum_sha256=str(uploaded["checksum_sha256"]),
                file_size_bytes=int(uploaded["file_size_bytes"]),
                storage_etag=str(uploaded["etag"]),
                version_no=version_no,
                uploaded_by_user_id=user.user_id,
                is_active=True,
            )
            return await self.repository.create(record)
        except Exception:
            await self.storage.delete(object_key)
            raise

    async def list_documents(
        self, case_id: UUID, user: User
    ) -> list[DocumentRecord]:
        await self.valuation.get_case(case_id, user)
        return await self.repository.list_for_case(case_id)

    async def get_document(
        self, case_id: UUID, document_id: UUID, user: User
    ) -> DocumentRecord:
        await self.valuation.get_case(case_id, user)
        record = await self.repository.get(case_id, document_id)
        if record is None:
            raise ResourceNotFoundError("文件")
        return record
