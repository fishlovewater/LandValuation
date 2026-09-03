from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import DbSession, require_permissions
from app.valuation.submissions.schemas import (
    SubmitForReviewCommand,
    SubmitForReviewResult,
)
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
