"""Transactional orchestration for correction draft, send, resubmit, recheck."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import AppError, ResourceNotFoundError
from app.review.corrections import (
    CorrectionGateSummary,
    build_correction_item_snapshot,
    validate_correction_send,
)
from app.review.correction_repository import CorrectionRepository
from app.review.repository import ReviewRepository
from app.review.service import ensure_transition


# Finding statuses that block a correction request from being sent.
_OPEN_STATUSES = {"OPEN", "REQUIRES_SUPPLEMENT"}
_EXPERT_STATUSES = {"EXPERT_REVIEW"}
_CONFIRMED_STATUS = "CONFIRMED_ISSUE"


class CorrectionService:
    def __init__(
        self,
        review_repository: ReviewRepository,
        correction_repository: CorrectionRepository,
    ) -> None:
        self.review_repository = review_repository
        self.corrections = correction_repository

    async def _gate_inputs(self, review) -> tuple[CorrectionGateSummary, list]:
        run = (
            await self.review_repository.get_run(review.latest_validation_run_id)
            if review.latest_validation_run_id
            else None
        )
        findings = (
            await self.review_repository.list_findings(
                review.latest_validation_run_id
            )
            if run
            else []
        )
        open_count = sum(1 for f in findings if f.status in _OPEN_STATUSES)
        expert_count = sum(1 for f in findings if f.status in _EXPERT_STATUSES)
        confirmed = [f for f in findings if f.status == _CONFIRMED_STATUS]
        active = await self.corrections.active_for_review(review.review_id)
        summary = CorrectionGateSummary(
            has_completed_run=bool(run and run.run_status == "COMPLETED"),
            open_count=open_count,
            confirmed_count=len(confirmed),
            expert_count=expert_count,
            has_active_request=active is not None,
        )
        return summary, confirmed

    async def create_draft(self, review_id, payload, actor_id):
        review = await self.review_repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if payload.due_at <= datetime.now(payload.due_at.tzinfo):
            raise AppError("CORRECTION_DUE_AT_INVALID", "修正期限必須晚於目前時間", 422)
        summary, confirmed = await self._gate_inputs(review)
        validate_correction_send(summary)

        base_document = await self.review_repository.get_latest_original_document(
            review.case_id
        )
        if base_document is None:
            raise AppError("CORRECTION_BASE_DOCUMENT_MISSING", "案件沒有正式原始文件", 409)

        request_no = await self.corrections.next_request_no(review.review_id)
        request = await self.corrections.create_request(
            review_id=review.review_id,
            request_no=request_no,
            based_on_validation_run_id=review.latest_validation_run_id,
            status="DRAFT",
            due_at=payload.due_at,
            message=payload.message.strip(),
            base_document_id=base_document["document_id"],
            base_document_version=base_document["version_no"],
            created_by_user_id=actor_id,
        )
        rows = []
        for finding in confirmed:
            snapshot = build_correction_item_snapshot(finding)
            snapshot["correction_request_id"] = request.correction_request_id
            rows.append(snapshot)
        await self.corrections.create_items(rows)
        return request

    async def send(self, request_id, actor_id, audit_request_id):
        request = await self.corrections.get_request(request_id, for_update=True)
        if request is None:
            raise ResourceNotFoundError("修正通知")
        review = await self.review_repository.get(request.review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if request.status != "DRAFT":
            raise AppError("CORRECTION_REQUEST_STATE_CONFLICT", "只有草稿可送出", 409)
        if request.based_on_validation_run_id != review.latest_validation_run_id:
            raise AppError(
                "CORRECTION_REQUEST_STALE",
                "修正通知不是基於最新一次審查",
                409,
            )
        # Recompute the gate from current state; a concurrent request would fail.
        summary, _ = await self._gate_inputs(review)
        # The draft itself is the active request, so ignore its own presence.
        summary = CorrectionGateSummary(
            has_completed_run=summary.has_completed_run,
            open_count=summary.open_count,
            confirmed_count=summary.confirmed_count,
            expert_count=summary.expert_count,
            has_active_request=False,
        )
        validate_correction_send(summary)

        now = datetime.now(UTC)
        request.status = "SENT"
        request.sent_by_user_id = actor_id
        request.sent_at = now

        before_status = review.review_status
        review.review_status = ensure_transition(
            before_status, "RETURNED_FOR_REVISION"
        )
        await self.review_repository.create_decision(
            review_id=review.review_id,
            finding_id=None,
            decision="RETURNED_FOR_REVISION",
            reason=f"送出第 {request.request_no} 次修正通知",
            decided_by_user_id=actor_id,
            request_id=audit_request_id,
            before_value={"review_status": before_status},
            after_value={
                "review_status": review.review_status,
                "correction_request_id": str(request.correction_request_id),
            },
        )
        await self.corrections.session.flush()
        return request
