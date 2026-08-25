from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import DbSession, require_permissions
from app.review.repository import ReviewRepository
from app.review.schemas import (
    ReviewAssign,
    ReviewCreate,
    ReviewList,
    ReviewListQuery,
    ReviewPriority,
    ReviewRead,
    ReviewUpdate,
)
from app.review.service import ReviewService

router = APIRouter(prefix="/review", tags=["review"])


def service_for(session: DbSession) -> ReviewService:
    return ReviewService(ReviewRepository(session))


@router.post("/cases", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review_case(
    payload: ReviewCreate,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).create(payload, user.user_id)


@router.get("/cases", response_model=ReviewList)
async def list_review_cases(
    session: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_reviewer_id: UUID | None = None,
    risk_level: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_permissions("review.execute")),
) -> ReviewList:
    query = ReviewListQuery(
        status=status_filter,
        assigned_reviewer_id=assigned_reviewer_id,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )
    items, total = await service_for(session).list(query)
    return ReviewList(items=items, total=total, limit=limit, offset=offset)


@router.get("/cases/{review_id}", response_model=ReviewRead)
async def get_review_case(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).get(review_id)


@router.patch("/cases/{review_id}", response_model=ReviewRead)
async def update_review_case(
    review_id: UUID,
    payload: ReviewUpdate,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).update(review_id, payload)


@router.post("/cases/{review_id}/assign", response_model=ReviewRead)
async def assign_review_case(
    review_id: UUID,
    payload: ReviewAssign,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).assign(review_id, payload.reviewer_id)


@router.post("/cases/{review_id}/priority", response_model=ReviewRead)
async def prioritize_review_case(
    review_id: UUID,
    payload: ReviewPriority,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).set_priority(
        review_id, payload.priority, payload.reason, user.user_id
    )
