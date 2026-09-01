from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import (
    AssistantMessageRecord,
    AssistantSessionRecord,
    BenchmarkLandRecord,
    DocumentExtractionRecord,
    DocumentRecord,
    ExtractedFieldRecord,
)


class AssistantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self, record: AssistantSessionRecord
    ) -> AssistantSessionRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_session(self, session_id: UUID) -> AssistantSessionRecord | None:
        return await self.session.scalar(
            select(AssistantSessionRecord).where(
                AssistantSessionRecord.assistant_session_id == session_id
            )
        )

    async def save_session(
        self, record: AssistantSessionRecord
    ) -> AssistantSessionRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def next_message_no(self, session_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.max(AssistantMessageRecord.message_no)).where(
                AssistantMessageRecord.assistant_session_id == session_id
            )
        )
        return (latest or 0) + 1

    async def add_message(
        self, record: AssistantMessageRecord
    ) -> AssistantMessageRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def list_active_document_types(self, case_id: UUID) -> set[str]:
        values = await self.session.scalars(
            select(DocumentRecord.document_type).where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.is_active.is_(True),
            )
        )
        return set(values.all())

    async def candidate_counts(self, case_id: UUID) -> tuple[int, int]:
        latest_extraction_ids = self._latest_extraction_ids(case_id)
        rows = (
            await self.session.execute(
                select(ExtractedFieldRecord.field_status, func.count())
                .where(
                    ExtractedFieldRecord.case_id == case_id,
                    ExtractedFieldRecord.form_code == "F03",
                    ExtractedFieldRecord.extraction_id.in_(latest_extraction_ids),
                )
                .group_by(ExtractedFieldRecord.field_status)
            )
        ).all()
        counts = dict(rows)
        confirmed = counts.get("CONFIRMED", 0) + counts.get("APPLIED", 0)
        pending = counts.get("EXTRACTED", 0) + counts.get("NEEDS_CONFIRMATION", 0)
        return confirmed, pending

    async def list_candidate_summaries(self, case_id: UUID) -> list[dict]:
        latest_extraction_ids = self._latest_extraction_ids(case_id)
        records = list(
            (
                await self.session.scalars(
                    select(ExtractedFieldRecord)
                    .where(
                        ExtractedFieldRecord.case_id == case_id,
                        ExtractedFieldRecord.form_code == "F03",
                        ExtractedFieldRecord.extraction_id.in_(
                            latest_extraction_ids
                        ),
                    )
                    .order_by(ExtractedFieldRecord.created_at.desc())
                )
            ).all()
        )
        return [
            {
                "extracted_field_id": str(record.extracted_field_id),
                "field_name": record.field_name,
                "value": record.confirmed_value
                if record.field_status in {"CONFIRMED", "APPLIED"}
                else record.extracted_value,
                "confidence": str(record.confidence),
                "source_page": record.source_page,
                "source_text": record.source_text,
                "status": record.field_status,
            }
            for record in records
        ]

    @staticmethod
    def _latest_extraction_ids(case_id: UUID):
        ranked = (
            select(
                DocumentExtractionRecord.extraction_id,
                func.row_number()
                .over(
                    partition_by=DocumentExtractionRecord.document_id,
                    order_by=(
                        DocumentExtractionRecord.created_at.desc(),
                        DocumentExtractionRecord.extraction_id.desc(),
                    ),
                )
                .label("extraction_rank"),
            )
            .where(DocumentExtractionRecord.case_id == case_id)
            .subquery()
        )
        return select(ranked.c.extraction_id).where(
            ranked.c.extraction_rank == 1
        )

    async def get_confirmed_candidate(
        self, case_id: UUID, candidate_id: UUID
    ) -> ExtractedFieldRecord | None:
        return await self.session.scalar(
            select(ExtractedFieldRecord).where(
                ExtractedFieldRecord.case_id == case_id,
                ExtractedFieldRecord.extracted_field_id == candidate_id,
                ExtractedFieldRecord.form_code == "F03",
                ExtractedFieldRecord.field_status == "CONFIRMED",
            )
        )

    async def resolve_benchmark_land_no(
        self, case_id: UUID, benchmark_land_no: str
    ) -> UUID | None:
        return await self.session.scalar(
            select(BenchmarkLandRecord.benchmark_land_id).where(
                BenchmarkLandRecord.case_id == case_id,
                BenchmarkLandRecord.benchmark_land_no == benchmark_land_no,
                BenchmarkLandRecord.is_active.is_(True),
            )
        )

    async def mark_candidate_applied(
        self,
        record: ExtractedFieldRecord,
        form_instance_id: UUID,
    ) -> None:
        from datetime import UTC, datetime

        record.field_status = "APPLIED"
        record.applied_form_instance_id = form_instance_id
        record.applied_at = datetime.now(UTC)
        await self.session.flush()
