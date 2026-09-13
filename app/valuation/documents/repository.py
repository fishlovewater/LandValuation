from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import DocumentRecord


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_case(self, case_id: UUID) -> list[DocumentRecord]:
        statement = (
            select(DocumentRecord)
            .where(DocumentRecord.case_id == case_id)
            .order_by(
                DocumentRecord.document_group_id,
                DocumentRecord.version_no.desc(),
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def list_active_for_case(self, case_id: UUID) -> list[DocumentRecord]:
        statement = (
            select(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.is_active.is_(True),
            )
            .order_by(DocumentRecord.uploaded_at, DocumentRecord.document_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def get(self, case_id: UUID, document_id: UUID) -> DocumentRecord | None:
        return await self.session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_id == document_id,
            )
        )

    async def latest_in_group(
        self, case_id: UUID, document_group_id: UUID
    ) -> DocumentRecord | None:
        return await self.session.scalar(
            select(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_group_id == document_group_id,
            )
            .order_by(DocumentRecord.version_no.desc())
            .limit(1)
        )

    async def next_version(self, case_id: UUID, document_group_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.max(DocumentRecord.version_no)).where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_group_id == document_group_id,
            )
        )
        return (latest or 0) + 1

    async def get_by_checksum(
        self,
        case_id: UUID,
        checksum_sha256: str,
    ) -> DocumentRecord | None:
        # Removed source files remain in the audit trail, but must not block a
        # user from uploading the same file again.
        return await self.session.scalar(
            select(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.checksum_sha256 == checksum_sha256,
                DocumentRecord.is_active.is_(True),
            )
            .order_by(
                DocumentRecord.version_no.desc(),
            )
            .limit(1)
        )

    async def get_inactive_by_checksum(
        self,
        case_id: UUID,
        checksum_sha256: str,
    ) -> DocumentRecord | None:
        return await self.session.scalar(
            select(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.checksum_sha256 == checksum_sha256,
                DocumentRecord.is_active.is_(False),
            )
            .order_by(DocumentRecord.uploaded_at.desc())
            .limit(1)
        )

    async def deactivate_group(self, case_id: UUID, document_group_id: UUID) -> None:
        await self.session.execute(
            update(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_group_id == document_group_id,
                DocumentRecord.is_active.is_(True),
            )
            .values(is_active=False)
        )

    async def deactivate_document(self, case_id: UUID, document_id: UUID) -> bool:
        result = await self.session.execute(
            update(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_id == document_id,
                DocumentRecord.is_active.is_(True),
            )
            .values(is_active=False)
        )
        return result.rowcount == 1

    async def create(self, record: DocumentRecord) -> DocumentRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def overwrite_generated_document(
        self,
        record: DocumentRecord,
        *,
        location_id: UUID | None,
        document_type: str,
        original_filename: str,
        mime_type: str,
        bucket_name: str,
        object_key: str,
        checksum_sha256: str,
        file_size_bytes: int,
        storage_etag: str,
        uploaded_by_user_id: UUID | None,
    ) -> DocumentRecord:
        """Replace a regenerable output without creating a competing version.

        Working Excel templates are derived artifacts, not user source files.
        Keeping one stable record per template scope makes a retry an overwrite
        and prevents a stale or parallel request from violating the document
        group/version uniqueness constraint.
        """

        record.location_id = location_id
        record.document_type = document_type
        record.original_filename = original_filename
        record.mime_type = mime_type
        record.bucket_name = bucket_name
        record.object_key = object_key
        record.checksum_sha256 = checksum_sha256
        record.file_size_bytes = file_size_bytes
        record.storage_etag = storage_etag
        record.uploaded_by_user_id = uploaded_by_user_id
        record.is_active = True
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def reclassify(
        self, record: DocumentRecord, category: str
    ) -> DocumentRecord:
        record.document_type = category
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def reactivate(
        self,
        record: DocumentRecord,
        *,
        document_type: str,
        original_filename: str,
        mime_type: str,
        bucket_name: str,
        object_key: str,
        file_size_bytes: int,
        storage_etag: str,
        version_no: int,
        uploaded_by_user_id: UUID | None,
    ) -> DocumentRecord:
        record.document_type = document_type
        record.original_filename = original_filename
        record.mime_type = mime_type
        record.bucket_name = bucket_name
        record.object_key = object_key
        record.file_size_bytes = file_size_bytes
        record.storage_etag = storage_etag
        record.version_no = version_no
        record.uploaded_by_user_id = uploaded_by_user_id
        record.is_active = True
        await self.session.flush()
        await self.session.refresh(record)
        return record
