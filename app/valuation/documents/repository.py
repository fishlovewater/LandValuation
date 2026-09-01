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
        return await self.session.scalar(
            select(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.checksum_sha256 == checksum_sha256,
            )
            .order_by(
                DocumentRecord.is_active.desc(),
                DocumentRecord.version_no.desc(),
            )
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

    async def create(self, record: DocumentRecord) -> DocumentRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record
