from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.review.correction_repository import CorrectionRepository
from app.review.models import Review
from app.review.repository import ReviewRepository
from app.valuation.models import CaseRecord, ReviewSubmissionRecord
from app.valuation.submissions.schemas import (
    HandoffCorrectionItemRead,
    HandoffCorrectionRead,
    HandoffMissingItemRead,
    HandoffSubmissionRead,
    ValuationReviewHandoffRead,
)


STATUS_LABELS = {
    "DRAFT": "製作中",
    "PROCESSING": "製作中",
    "IN_REVIEW": "審查中",
    "REVISION_REQUIRED": "退回補正",
    "REVIEW_COMPLETED": "審查完成",
}


class ValuationReviewHandoffService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.corrections = CorrectionRepository(session)
        self.reviews = ReviewRepository(session)

    async def get(self, case_id: UUID, actor: User) -> ValuationReviewHandoffRead:
        case = await self.session.scalar(
            select(CaseRecord).where(CaseRecord.case_id == case_id)
        )
        if case is None:
            raise ResourceNotFoundError("估價案件")
        if case.created_by_user_id != actor.user_id:
            raise PermissionDeniedError("只能查看自己建立的估價案件")

        review = await self.session.scalar(
            select(Review).where(Review.case_id == case_id)
        )
        if review is None:
            return ValuationReviewHandoffRead(
                case_id=case_id,
                case_status=case.case_status,
                display_status=STATUS_LABELS.get(case.case_status, "製作中"),
                review_id=None,
                review_status=None,
                latest_submission=None,
                correction=None,
                missing_items=[],
            )

        submission = None
        if review.latest_submission_id is not None:
            submission = await self.session.scalar(
                select(ReviewSubmissionRecord).where(
                    ReviewSubmissionRecord.submission_id
                    == review.latest_submission_id,
                    ReviewSubmissionRecord.review_id == review.review_id,
                    ReviewSubmissionRecord.case_id == case_id,
                )
            )

        request = await self.corrections.active_for_review(review.review_id)
        correction = None
        if request is not None and request.status in {"SENT", "RESUBMITTED"}:
            items = await self.corrections.list_items(request.correction_request_id)
            correction = HandoffCorrectionRead(
                correction_request_id=request.correction_request_id,
                request_no=request.request_no,
                status=request.status,
                due_at=request.due_at,
                message=request.message,
                items=[
                    HandoffCorrectionItemRead.model_validate(item) for item in items
                ],
            )

        missing = await self.reviews.list_missing_items(review.review_id, open_only=True)
        return ValuationReviewHandoffRead(
            case_id=case_id,
            case_status=case.case_status,
            display_status=STATUS_LABELS.get(case.case_status, case.case_status),
            review_id=review.review_id,
            review_status=review.review_status,
            latest_submission=(
                None
                if submission is None
                else HandoffSubmissionRead.model_validate(submission)
            ),
            correction=correction,
            missing_items=[HandoffMissingItemRead.model_validate(item) for item in missing],
        )
