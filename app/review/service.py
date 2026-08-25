from app.core.exceptions import AppError
from app.core.exceptions import ResourceNotFoundError
from app.review.repository import ReviewRepository
from app.review.schemas import ReviewCreate, ReviewListQuery, ReviewUpdate


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "RECEIVED": frozenset({"PREPROCESSING"}),
    "PREPROCESSING": frozenset({"PENDING_MATERIALS", "READY_FOR_REVIEW"}),
    "PENDING_MATERIALS": frozenset({"PREPROCESSING"}),
    "READY_FOR_REVIEW": frozenset({"ANALYZING"}),
    "ANALYZING": frozenset({"REVIEW_REQUIRED"}),
    "REVIEW_REQUIRED": frozenset(
        {
            "RETURNED_FOR_REVISION",
            "SUPPLEMENT_REQUIRED",
            "EXPERT_REVIEW",
            "APPROVED",
        }
    ),
    "RETURNED_FOR_REVISION": frozenset({"PREPROCESSING"}),
    "SUPPLEMENT_REQUIRED": frozenset({"PREPROCESSING"}),
    "EXPERT_REVIEW": frozenset({"REVIEW_REQUIRED"}),
    "APPROVED": frozenset({"REVIEW_COMPLETED"}),
    "REVIEW_COMPLETED": frozenset(),
}


def ensure_transition(current: str, target: str) -> str:
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise AppError(
            "REVIEW_STATE_CONFLICT",
            f"審查狀態不可由 {current} 轉為 {target}",
            409,
            {"current": current, "target": target},
        )
    return target


class ReviewService:
    def __init__(self, repository: ReviewRepository) -> None:
        self.repository = repository

    async def create(self, payload: ReviewCreate, actor_id):
        return await self.repository.create(payload, actor_id)

    async def get(self, review_id):
        review = await self.repository.get(review_id)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        return review

    async def list(self, query: ReviewListQuery):
        return await self.repository.list(query)

    async def update(self, review_id, payload: ReviewUpdate):
        review = await self.repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        review.review_status = ensure_transition(
            review.review_status, payload.review_status
        )
        await self.repository.session.flush()
        return review

    async def assign(self, review_id, reviewer_id):
        try:
            return await self.repository.assign(review_id, reviewer_id)
        except LookupError as exc:
            raise ResourceNotFoundError("審查案件") from exc

    async def set_priority(self, review_id, priority, reason, actor_id):
        try:
            return await self.repository.set_priority(
                review_id, priority, reason, actor_id
            )
        except LookupError as exc:
            raise ResourceNotFoundError("審查案件") from exc
