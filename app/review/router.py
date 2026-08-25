from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import DbSession, require_permissions
from app.review.repository import ReviewRepository
from app.review.schemas import (
    ReviewAssign,
    ReviewCreate,
    ReviewList,
    ReviewListQuery,
    CompletenessResponse,
    FindingRead,
    MissingItemRead,
    ReviewPriority,
    ReviewRead,
    ReviewStatus,
    ReviewUpdate,
    RiskLevel,
    RiskSummaryRead,
    RunCreate,
    SupplementRequest,
    ValidationRunRead,
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
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    assigned_reviewer_id: UUID | None = None,
    risk_level: RiskLevel | None = None,
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


@router.post(
    "/cases/{review_id}/completeness-check", response_model=CompletenessResponse
)
async def check_review_completeness(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> CompletenessResponse:
    result, review, items = await service_for(session).check_completeness(
        review_id, user.user_id
    )
    return CompletenessResponse(
        ready=result.ready,
        review_status=review.review_status,
        missing_item_count=review.missing_item_count,
        blocked_rule_codes=sorted(result.blocked_rule_codes),
        items=items,
    )


@router.get("/cases/{review_id}/missing-items", response_model=list[MissingItemRead])
async def list_review_missing_items(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[MissingItemRead]:
    return await service_for(session).list_missing_items(review_id)


@router.post(
    "/cases/{review_id}/supplement-request", response_model=list[MissingItemRead]
)
async def request_review_supplement(
    review_id: UUID,
    payload: SupplementRequest,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[MissingItemRead]:
    return await service_for(session).request_supplement(review_id, payload.due_at)


@router.post(
    "/cases/{review_id}/runs",
    response_model=ValidationRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_review_run(
    review_id: UUID,
    payload: RunCreate,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ValidationRunRead:
    run, _summary = await service_for(session).create_run(
        review_id, payload, user.user_id
    )
    return run


@router.get("/cases/{review_id}/runs", response_model=list[ValidationRunRead])
async def list_review_runs(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[ValidationRunRead]:
    return await service_for(session).list_runs(review_id)


@router.get("/runs/{validation_run_id}", response_model=ValidationRunRead)
async def get_review_run(
    validation_run_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ValidationRunRead:
    return await service_for(session).get_run(validation_run_id)


@router.get("/runs/{validation_run_id}/findings", response_model=list[FindingRead])
async def list_run_findings(
    validation_run_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[FindingRead]:
    return await service_for(session).list_findings(validation_run_id)


@router.get("/findings/{finding_id}", response_model=FindingRead)
async def get_review_finding(
    finding_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> FindingRead:
    return await service_for(session).get_finding(finding_id)


@router.get(
    "/runs/{validation_run_id}/risk-summary", response_model=RiskSummaryRead
)
async def get_run_risk_summary(
    validation_run_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> RiskSummaryRead:
    return await service_for(session).get_risk_summary(validation_run_id)
