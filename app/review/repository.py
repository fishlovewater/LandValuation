from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.review.models import Review
from app.review.schemas import ReviewCreate, ReviewListQuery


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: ReviewCreate, started_by_user_id: UUID) -> Review:
        values = payload.model_dump(exclude_none=True)
        review = Review(
            **values,
            review_status="RECEIVED",
            started_by_user_id=started_by_user_id,
        )
        self.session.add(review)
        await self.session.flush()
        await self.session.refresh(review)
        return review

    async def get(self, review_id: UUID, for_update: bool = False) -> Review | None:
        statement = select(Review).where(Review.review_id == review_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list(self, query: ReviewListQuery) -> tuple[list[Review], int]:
        filters = []
        if query.status is not None:
            filters.append(Review.review_status == query.status)
        if query.assigned_reviewer_id is not None:
            filters.append(Review.assigned_reviewer_id == query.assigned_reviewer_id)
        if query.risk_level is not None:
            filters.append(Review.current_risk_level == query.risk_level)

        total = await self.session.scalar(
            select(func.count()).select_from(Review).where(*filters)
        )
        now = datetime.now(UTC)
        risk_rank = case(
            (Review.current_risk_level == "CRITICAL", 4),
            (Review.current_risk_level == "HIGH", 3),
            (Review.current_risk_level == "MEDIUM", 2),
            (Review.current_risk_level == "LOW", 1),
            else_=0,
        )
        overdue_rank = case(
            (Review.due_at.is_not(None) & (Review.due_at < now), 1), else_=0
        )
        statement = (
            select(Review)
            .where(*filters)
            .order_by(
                Review.manual_priority.desc(),
                overdue_rank.desc(),
                risk_rank.desc(),
                Review.due_at.asc().nulls_last(),
                Review.received_at.asc(),
                Review.review_id.asc(),
            )
            .limit(query.limit)
            .offset(query.offset)
        )
        reviews = list((await self.session.scalars(statement)).all())
        return reviews, int(total or 0)

    async def assign(self, review_id: UUID, reviewer_id: UUID) -> Review:
        review = await self.get(review_id, for_update=True)
        if review is None:
            raise LookupError(review_id)
        review.assigned_reviewer_id = reviewer_id
        await self.session.flush()
        return review

    async def set_priority(
        self,
        review_id: UUID,
        priority: int,
        reason: str,
        actor_id: UUID,
    ) -> Review:
        del actor_id  # reserved for the append-only audit event in the decision slice
        review = await self.get(review_id, for_update=True)
        if review is None:
            raise LookupError(review_id)
        review.manual_priority = priority
        review.manual_priority_reason = reason
        await self.session.flush()
        return review
