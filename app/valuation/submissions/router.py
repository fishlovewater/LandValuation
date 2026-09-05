from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import DbSession, require_permissions
from app.valuation.submissions.schemas import (
    SubmitForReviewCommand,
    SubmitForReviewResult,
    ValuationReviewHandoffRead,
)
from app.valuation.submissions.handoff_service import ValuationReviewHandoffService
from app.valuation.submissions.service import SubmissionService

router = APIRouter()


@router.post(
    "/cases/{case_id}/submit-for-review",
    response_model=SubmitForReviewResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_for_review(
    case_id: UUID,
    payload: SubmitForReviewCommand,
    session: DbSession,
    user=Depends(require_permissions("valuation.submit_review")),
) -> SubmitForReviewResult:
    return await SubmissionService(session).submit(case_id, payload, user)


@router.get(
    "/cases/{case_id}/review-handoff",
    response_model=ValuationReviewHandoffRead,
)
async def get_review_handoff(
    case_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("case.read")),
) -> ValuationReviewHandoffRead:
    return await ValuationReviewHandoffService(session).get(case_id, user)
