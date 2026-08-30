"""Persistence for correction requests, items, settings, and resubmissions."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.review.models import CorrectionRequest, CorrectionRequestItem


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
            statement = statement.with_for_update()
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
            statement = statement.with_for_update()
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
