from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import DocumentExtractionRecord, ExtractedFieldRecord


class ExtractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_extraction(
        self, record: DocumentExtractionRecord
    ) -> DocumentExtractionRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def save_extraction(
        self, record: DocumentExtractionRecord
    ) -> DocumentExtractionRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def add_candidates(self, records: list[ExtractedFieldRecord]) -> None:
        self.session.add_all(records)
        await self.session.flush()

    async def candidate_field_names(
        self, extraction_id: UUID, form_code: str
    ) -> set[str]:
        values = await self.session.scalars(
            select(ExtractedFieldRecord.field_name).where(
                ExtractedFieldRecord.extraction_id == extraction_id,
                ExtractedFieldRecord.form_code == form_code,
            )
        )
        return set(values.all())

    async def latest_for_document(
        self, case_id: UUID, document_id: UUID
    ) -> DocumentExtractionRecord | None:
        return await self.session.scalar(
            select(DocumentExtractionRecord)
            .where(
                DocumentExtractionRecord.case_id == case_id,
                DocumentExtractionRecord.document_id == document_id,
            )
            .order_by(DocumentExtractionRecord.created_at.desc())
            .limit(1)
        )

    async def list_candidates(self, extraction_id: UUID) -> list[ExtractedFieldRecord]:
        statement = (
            select(ExtractedFieldRecord)
            .where(ExtractedFieldRecord.extraction_id == extraction_id)
            .order_by(ExtractedFieldRecord.field_name)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_candidate(
        self, case_id: UUID, extraction_id: UUID, candidate_id: UUID
    ) -> ExtractedFieldRecord | None:
        return await self.session.scalar(
            select(ExtractedFieldRecord).where(
                ExtractedFieldRecord.case_id == case_id,
                ExtractedFieldRecord.extraction_id == extraction_id,
                ExtractedFieldRecord.extracted_field_id == candidate_id,
            )
        )

    async def save_candidate(self, record: ExtractedFieldRecord) -> None:
        await self.session.flush()
        await self.session.refresh(record)

    async def apply_candidate(
        self, record: ExtractedFieldRecord, form_instance_id: UUID
    ) -> None:
        related_records = await self.session.scalars(
            select(ExtractedFieldRecord)
            .where(
                ExtractedFieldRecord.case_id == record.case_id,
                ExtractedFieldRecord.field_name == record.field_name,
            )
            .with_for_update()
        )
        for related_record in related_records.all():
            if (
                related_record.extracted_field_id != record.extracted_field_id
                and related_record.field_status == "APPLIED"
            ):
                related_record.field_status = "CONFIRMED"
                related_record.applied_form_instance_id = None
                related_record.applied_at = None

        record.field_status = "APPLIED"
        record.applied_form_instance_id = form_instance_id
        record.applied_at = datetime.now(UTC)
        await self.session.flush()
