from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import permission_codes
from app.core.exceptions import AppError, PermissionDeniedError, ResourceNotFoundError
from app.valuation.models import ReviewSubmissionRecord
from app.valuation.submissions.repository import SubmissionRepository
from app.valuation.submissions.schemas import (
    SubmitForReviewCommand,
    SubmitForReviewResult,
)
from app.valuation.submissions.snapshot import (
    build_submission_snapshot,
    snapshot_fingerprint,
)


class SubmissionService:
    def __init__(
        self,
        session: AsyncSession | None,
        repository: SubmissionRepository | None = None,
    ) -> None:
        self.repository = repository or SubmissionRepository(session)

    async def submit(
        self,
        case_id: UUID,
        command: SubmitForReviewCommand,
        actor: User,
    ) -> SubmitForReviewResult:
        case = await self.repository.lock_case(case_id)
        if case is None:
            raise ResourceNotFoundError("估價案件")
        self._require_submit_authority(case, actor)

        existing = await self.repository.find_by_request(case_id, command.request_id)
        if existing is not None:
            self._require_matching_request(existing, command)
            return self._result(existing, case.case_status)

        if case.case_status not in {"PROCESSING", "REVISION_REQUIRED"}:
            raise AppError(
                "CASE_SUBMISSION_STATE_CONFLICT",
                "案件目前狀態不可送審",
                409,
                {"case_status": case.case_status},
            )

        locked_review = await self.repository.lock_review_for_case(case_id)
        inputs = await self.repository.load_submission_inputs(case_id, command)
        self._validate_readiness(inputs, command)

        snapshot = build_submission_snapshot(
            case_version=inputs.case_version,
            submitted_by_user_id=actor.user_id,
            request_id=command.request_id,
            applied_fields=inputs.applied_fields,
            calculations=inputs.calculations,
            documents=inputs.documents,
            validation=inputs.validation,
        )
        fingerprint = snapshot_fingerprint(snapshot)

        if locked_review is None:
            locked_review = await self.repository.create_review(case_id, actor.user_id)
        review = locked_review.review
        latest_submission = locked_review.latest_submission
        review.form_instance_id = inputs.report_form.form_instance_id
        review.validation_run_id = inputs.source_validation_run.validation_run_id
        submission_no = 1 if latest_submission is None else latest_submission.submission_no + 1
        submission = ReviewSubmissionRecord(
            submission_id=uuid4(),
            review_id=review.review_id,
            case_id=case_id,
            submission_no=submission_no,
            submitted_by_user_id=actor.user_id,
            submitted_at=datetime.now(UTC),
            source_validation_run_id=command.source_validation_run_id,
            source_report_document_id=command.source_report_document_id,
            input_snapshot=snapshot,
            input_fingerprint=fingerprint,
            supersedes_submission_id=(
                None if latest_submission is None else latest_submission.submission_id
            ),
            request_id=command.request_id,
        )
        await self.repository.create_submission(submission)
        review.latest_submission = submission
        review.review_status = "RECEIVED"
        case.case_status = "IN_REVIEW"
        await self.repository.record_case_event(
            case_id,
            "SUBMITTED_FOR_REVIEW",
            command.request_id,
            {
                "submission_id": str(submission.submission_id),
                "submission_no": submission.submission_no,
                "review_id": str(review.review_id),
                "source_validation_run_id": str(command.source_validation_run_id),
                "source_report_document_id": str(command.source_report_document_id),
                "input_fingerprint": fingerprint,
                "submitted_by_user_id": str(actor.user_id),
            },
        )
        await self.repository.session.flush()
        return self._result(submission, case.case_status)

    @staticmethod
    def _require_submit_authority(case, actor: User) -> None:
        if case.created_by_user_id != actor.user_id:
            raise PermissionDeniedError("只有案件建立者可以送審")
        if "valuation.submit_review" not in permission_codes(actor):
            raise PermissionDeniedError()

    @staticmethod
    def _require_matching_request(
        existing: ReviewSubmissionRecord, command: SubmitForReviewCommand
    ) -> None:
        if (
            existing.source_validation_run_id != command.source_validation_run_id
            or existing.source_report_document_id != command.source_report_document_id
            or existing.input_snapshot.get("case_version")
            != command.expected_case_version
        ):
            raise AppError(
                "SUBMISSION_REQUEST_CONFLICT",
                "相同 request_id 不可搭配不同送審內容",
                409,
            )

    @staticmethod
    def _validate_readiness(inputs, command: SubmitForReviewCommand) -> None:
        if inputs.authoritative_report_form is None:
            raise ResourceNotFoundError("完整估價報告")
        if inputs.case_version != command.expected_case_version:
            raise AppError("CASE_VERSION_CONFLICT", "案件版本已變更", 409)
        if inputs.source_validation_run is None:
            raise ResourceNotFoundError("送審檢核結果")
        if inputs.source_validation_run.run_status != "COMPLETED":
            raise AppError(
                "SUBMISSION_VALIDATION_NOT_COMPLETED",
                "送審前必須完成來源檢核",
                422,
            )
        if inputs.source_validation_run.failed_count > 0:
            raise AppError(
                "SUBMISSION_VALIDATION_NOT_PASSED",
                "送審前來源檢核不得有未通過項目",
                422,
            )
        if (
            inputs.source_report_document is None
            or inputs.report_form is None
            or inputs.report_form.form_instance_id
            != inputs.authoritative_report_form.form_instance_id
            or inputs.report_form.version_no
            != inputs.authoritative_report_form.version_no
            or inputs.report_form.output_document_id
            != command.source_report_document_id
        ):
            raise ResourceNotFoundError("完整估價報告")
        if inputs.report_form.form_status != "FINAL":
            raise AppError(
                "SUBMISSION_REPORT_NOT_FINAL",
                "送審前必須產生正式完整估價報告",
                422,
            )
        if not inputs.applied_fields:
            raise AppError(
                "SUBMISSION_APPLIED_FIELDS_REQUIRED",
                "送審前必須套用至少一筆已確認欄位",
                422,
            )
        if any(field["confirmed_value"] is None for field in inputs.applied_fields):
            raise AppError(
                "SUBMISSION_APPLIED_VALUE_REQUIRED",
                "送審前所有已套用欄位都必須有已確認值",
                422,
            )
        if not inputs.calculations:
            raise AppError(
                "SUBMISSION_CALCULATION_REQUIRED",
                "送審前必須完成正式計算",
                422,
            )

    @staticmethod
    def _result(
        submission: ReviewSubmissionRecord, case_status: str) -> SubmitForReviewResult:
        return SubmitForReviewResult(
            submission_id=submission.submission_id,
            submission_no=submission.submission_no,
            review_id=submission.review_id,
            case_status=case_status,
            submitted_at=submission.submitted_at,
        )
