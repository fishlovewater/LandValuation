"""Persistence for correction requests, items, settings, and resubmissions."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.review.models import (
    CorrectionRequest,
    CorrectionRequestItem,
    UrgencySettings,
)
from app.review.urgency import UrgencyThresholds


class CorrectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_request_no(self, review_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(CorrectionRequest.request_no), 0) + 1).where(
                CorrectionRequest.review_id == review_id
            )
        )
        return int(value or 1)

    async def active_for_review(
        self, review_id: UUID, for_update: bool = False
    ) -> CorrectionRequest | None:
        statement = select(CorrectionRequest).where(
            CorrectionRequest.review_id == review_id,
            CorrectionRequest.status != "RECHECKED",
        )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return await self.session.scalar(statement)

    async def create_request(self, **values) -> CorrectionRequest:
        request = CorrectionRequest(**values)
        self.session.add(request)
        await self.session.flush()
        await self.session.refresh(request)
        return request

    async def create_items(self, rows: list[dict]) -> list[CorrectionRequestItem]:
        items = [CorrectionRequestItem(**row) for row in rows]
        self.session.add_all(items)
        await self.session.flush()
        for item in items:
            await self.session.refresh(item)
        return items

    async def get_request(
        self, correction_request_id: UUID, for_update: bool = False
    ) -> CorrectionRequest | None:
        statement = select(CorrectionRequest).where(
            CorrectionRequest.correction_request_id == correction_request_id
        )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return await self.session.scalar(statement)

    async def list_items(
        self, correction_request_id: UUID
    ) -> list[CorrectionRequestItem]:
        statement = (
            select(CorrectionRequestItem)
            .where(
                CorrectionRequestItem.correction_request_id == correction_request_id
            )
            .order_by(CorrectionRequestItem.correction_request_item_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_requests(self, review_id: UUID) -> list[CorrectionRequest]:
        statement = (
            select(CorrectionRequest)
            .where(CorrectionRequest.review_id == review_id)
            .order_by(
                CorrectionRequest.request_no,
                CorrectionRequest.correction_request_id,
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def valid_resubmission_document(
        self,
        case_id: UUID,
        base_document_id: UUID,
        base_document_version: int,
        document_id: UUID,
        document_version: int,
    ) -> dict | None:
        """Return the resubmission document only when ownership+lineage hold.

        Requires: same case, active, matching payload version, version greater
        than the base version, and same document_group_id as the base document.
        """
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT d.document_id, d.version_no, d.document_group_id
                    FROM valuation.documents d
                    JOIN valuation.documents base
                      ON base.document_id = :base_document_id
                    WHERE d.document_id = :document_id
                      AND d.case_id = :case_id
                      AND d.is_active = true
                      AND d.version_no = :document_version
                      AND d.version_no > :base_document_version
                      AND d.document_group_id = base.document_group_id
                    """
                ),
                {
                    "case_id": case_id,
                    "base_document_id": base_document_id,
                    "base_document_version": base_document_version,
                    "document_id": document_id,
                    "document_version": document_version,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def external_resubmission_extraction_state(
        self,
        case_id: UUID,
        document_id: UUID,
    ) -> dict | None:
        """Return the latest extraction state used to gate an external return.

        External correction documents are mutable intake until OCR/text extraction
        has completed and every candidate from that latest extraction has been
        explicitly confirmed/applied or rejected.  Registration as the formal
        correction return is therefore a server-side state transition, not merely
        a UI convention.
        """
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT de.extraction_id,
                           de.extraction_status,
                           count(ef.extracted_field_id) FILTER (
                             WHERE ef.field_status IS NULL
                                OR ef.field_status NOT IN ('APPLIED', 'CONFIRMED', 'REJECTED')
                           ) AS pending_candidate_count
                    FROM (
                        SELECT extraction_id, extraction_status
                        FROM valuation.document_extractions
                        WHERE case_id = :case_id
                          AND document_id = :document_id
                        ORDER BY created_at DESC, extraction_id DESC
                        LIMIT 1
                    ) de
                    LEFT JOIN valuation.extracted_fields ef
                      ON ef.extraction_id = de.extraction_id
                    GROUP BY de.extraction_id, de.extraction_status
                    """
                ),
                {"case_id": case_id, "document_id": document_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def get_urgency_settings(
        self, for_update: bool = False
    ) -> UrgencySettings | None:
        statement = select(UrgencySettings).where(UrgencySettings.settings_id == 1)
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return await self.session.scalar(statement)

    async def update_urgency_settings(
        self, urgent_days: int, due_soon_days: int, actor_id: UUID
    ) -> UrgencySettings:
        settings = await self.get_urgency_settings(for_update=True)
        if settings is None:
            settings = UrgencySettings(settings_id=1)
            self.session.add(settings)
        settings.urgent_days = urgent_days
        settings.due_soon_days = due_soon_days
        settings.updated_by_user_id = actor_id
        settings.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(settings)
        return settings

    async def urgency_thresholds(self) -> UrgencyThresholds:
        settings = await self.get_urgency_settings()
        if settings is None:
            return UrgencyThresholds()
        return UrgencyThresholds(settings.urgent_days, settings.due_soon_days)

    async def count_active_requests(self, review_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(CorrectionRequest)
            .where(
                CorrectionRequest.review_id == review_id,
                CorrectionRequest.status != "RECHECKED",
            )
        )
        return int(value or 0)

    async def count_non_rechecked_requests(self, review_id: UUID) -> int:
        return await self.count_active_requests(review_id)

    async def count_not_evaluated_items(self, review_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(CorrectionRequestItem)
            .join(
                CorrectionRequest,
                CorrectionRequest.correction_request_id
                == CorrectionRequestItem.correction_request_id,
            )
            .where(
                CorrectionRequest.review_id == review_id,
                CorrectionRequestItem.recheck_outcome == "NOT_EVALUATED",
            )
        )
        return int(value or 0)
