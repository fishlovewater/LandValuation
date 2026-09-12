"""Transactional orchestration for correction draft, send, resubmit, recheck."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import AppError, ResourceNotFoundError
from app.review.corrections import (
    CorrectionGateSummary,
    ReviewCompletionSummary,
    build_correction_item_snapshot,
    validate_correction_send,
    validate_review_completion,
)
from app.review.correction_repository import CorrectionRepository
from app.review.repository import ReviewRepository
from app.review.schemas import CorrectionResubmissionCreate
from app.review.service import ensure_transition, ReviewService
from app.review.status_policy import (
    REVIEW_COMPLETION_STATUSES,
    REVIEW_CORRECTION_RECHECK_STATUSES,
    REVIEW_CORRECTION_REQUEST_STATUSES,
    ensure_review_status_allowed,
)


# Finding statuses that block a correction request from being sent.
_OPEN_STATUSES = {"OPEN", "REQUIRES_SUPPLEMENT"}
_EXPERT_STATUSES = {"EXPERT_REVIEW"}
_CONFIRMED_STATUS = "CONFIRMED_ISSUE"


class CorrectionService:
    def __init__(
        self,
        review_repository: ReviewRepository,
        correction_repository: CorrectionRepository,
        review_service=None,
    ) -> None:
        self.review_repository = review_repository
        self.corrections = correction_repository
        self._review_service = review_service

    @staticmethod
    def _submission_base_document(provenance: dict | None) -> dict | None:
        """Project the correction base document from the immutable submission.

        ``get_submission_provenance_by_id`` returns submission-level metadata,
        not a document row. The correction lineage must therefore use the
        matching document version frozen inside the submission snapshot.
        """
        if not isinstance(provenance, dict):
            return None
        source_document_id = provenance.get("source_report_document_id")
        snapshot = provenance.get("input_snapshot")
        documents = snapshot.get("documents") if isinstance(snapshot, dict) else None
        if source_document_id is None or not isinstance(documents, list):
            return None
        try:
            normalized_source_id = UUID(str(source_document_id))
        except (TypeError, ValueError):
            return None
        for document in documents:
            if not isinstance(document, dict):
                continue
            try:
                document_id = UUID(str(document.get("document_id")))
            except (TypeError, ValueError):
                continue
            if document_id != normalized_source_id:
                continue
            version_no = document.get("version_no")
            if (
                isinstance(version_no, bool)
                or not isinstance(version_no, int)
                or version_no < 1
            ):
                return None
            return {
                "document_id": normalized_source_id,
                "version_no": version_no,
            }
        return None

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
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_CORRECTION_REQUEST_STATUSES,
            action="建立修正通知",
        )
        if payload.due_at <= datetime.now(payload.due_at.tzinfo):
            raise AppError("CORRECTION_DUE_AT_INVALID", "修正期限必須晚於目前時間", 422)
        summary, confirmed = await self._gate_inputs(review)
        validate_correction_send(summary)

        latest_submission_id = getattr(review, "latest_submission_id", None)
        if latest_submission_id is not None:
            provenance = await self.review_repository.get_submission_provenance_by_id(
                latest_submission_id,
                review_id=review.review_id,
                case_id=review.case_id,
            )
            base_document = self._submission_base_document(provenance)
            if base_document is None:
                raise AppError(
                    "CORRECTION_BASE_DOCUMENT_SUBMISSION_INVALID",
                    "目前送審版本不存在、來源文件遺失或不屬於此審查案件",
                    409,
                )
        else:
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
        request_probe = await self.corrections.get_request(request_id)
        if request_probe is None:
            raise ResourceNotFoundError("修正通知")
        review_probe = await self.review_repository.get(request_probe.review_id)
        if review_probe is None:
            raise ResourceNotFoundError("審查案件")
        case = await self.review_repository.get_case(
            review_probe.case_id, for_update=True
        )
        if case is None:
            raise ResourceNotFoundError("估價案件")
        review = await self.review_repository.get(
            request_probe.review_id, for_update=True
        )
        if review is None:
            raise ResourceNotFoundError("審查案件")
        request = await self.corrections.get_request(request_id, for_update=True)
        if request is None:
            raise ResourceNotFoundError("修正通知")
        if review.case_id != case.case_id or request.review_id != review.review_id:
            raise AppError(
                "CORRECTION_REQUEST_OWNERSHIP_CONFLICT",
                "修正通知與審查案件關聯已變更",
                409,
            )
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_CORRECTION_REQUEST_STATUSES,
            action="送出修正通知",
        )
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
        case.case_status = "REVISION_REQUIRED"
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

    async def register_latest_resubmission(
        self,
        review_id: UUID,
        payload: CorrectionResubmissionCreate,
        actor_id: UUID,
    ):
        case, review = await self._lock_review_context(review_id)
        request = await self.corrections.active_for_review(
            review_id, for_update=True
        )
        if request is None:
            raise AppError(
                "CORRECTION_RESUBMISSION_INVALID",
                "找不到等待補正的修正通知",
                409,
            )
        if request.review_id != review.review_id:
            raise AppError(
                "CORRECTION_REQUEST_OWNERSHIP_CONFLICT",
                "修正通知與審查案件關聯已變更",
                409,
            )
        return await self._register_locked_resubmission(
            request, payload, actor_id, case=case, review=review
        )

    async def register_resubmission(self, request_id, payload, actor_id):
        case, review, request = await self._lock_request_context(request_id)
        return await self._register_locked_resubmission(
            request, payload, actor_id, case=case, review=review
        )

    async def _lock_review_context(self, review_id: UUID):
        review_probe = await self.review_repository.get(review_id)
        if review_probe is None:
            raise ResourceNotFoundError("審查案件")
        case = await self.review_repository.get_case(
            review_probe.case_id, for_update=True
        )
        if case is None:
            raise ResourceNotFoundError("估價案件")
        review = await self.review_repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if review.case_id != case.case_id:
            raise AppError(
                "CORRECTION_REQUEST_OWNERSHIP_CONFLICT",
                "修正通知與審查案件關聯已變更",
                409,
            )
        return case, review

    async def _lock_request_context(self, request_id):
        request_probe = await self.corrections.get_request(request_id)
        if request_probe is None:
            raise ResourceNotFoundError("修正通知")
        case, review = await self._lock_review_context(request_probe.review_id)
        request = await self.corrections.get_request(request_id, for_update=True)
        if request is None:
            raise ResourceNotFoundError("修正通知")
        if request.review_id != review.review_id:
            raise AppError(
                "CORRECTION_REQUEST_OWNERSHIP_CONFLICT",
                "修正通知與審查案件關聯已變更",
                409,
            )
        return case, review, request

    async def _register_locked_resubmission(
        self,
        request,
        payload: CorrectionResubmissionCreate,
        actor_id: UUID,
        *,
        case=None,
        review=None,
    ):
        if request.status != "SENT":
            raise AppError(
                "CORRECTION_RESUBMISSION_INVALID",
                "只有已送出且尚未回件的修正通知可登記新版文件",
                409,
            )
        if review is None:
            review = await self.review_repository.get(request.review_id)
            if review is None:
                raise ResourceNotFoundError("審查案件")
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_CORRECTION_RECHECK_STATUSES,
            action="登記修正版回件",
        )
        if case is None:
            case = await self.review_repository.get_case(review.case_id)
            if case is None:
                raise ResourceNotFoundError("估價案件")
        document = await self.corrections.valid_resubmission_document(
            case_id=review.case_id,
            base_document_id=request.base_document_id,
            base_document_version=request.base_document_version,
            document_id=payload.document_id,
            document_version=payload.document_version,
        )
        if document is None:
            raise AppError(
                "CORRECTION_RESUBMISSION_INVALID",
                "回件文件必須屬於同一案件、版本更新且沿革一致",
                409,
            )
        if getattr(case, "case_type", None) == "EXTERNAL_REVIEW":
            extraction = await self.corrections.external_resubmission_extraction_state(
                review.case_id,
                document["document_id"],
            )
            if extraction is None or extraction["extraction_status"] != "COMPLETED":
                raise AppError(
                    "EXTERNAL_RESUBMISSION_EXTRACTION_REQUIRED",
                    "外部修正版必須先完成 OCR／文字擷取，才能登記為正式回件",
                    409,
                )
            if int(extraction["pending_candidate_count"] or 0) > 0:
                raise AppError(
                    "EXTERNAL_RESUBMISSION_CONFIRMATION_REQUIRED",
                    "外部修正版仍有待確認欄位，請完成欄位確認後再登記回件",
                    409,
                )
        request.response_document_id = document["document_id"]
        request.response_document_version = document["version_no"]
        request.resubmitted_by_user_id = actor_id
        request.resubmitted_at = datetime.now(UTC)
        request.status = "RESUBMITTED"
        await self.corrections.session.flush()
        return request

    async def recheck(self, request_id, actor_id):
        _case, review, request = await self._lock_request_context(request_id)
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_CORRECTION_RECHECK_STATUSES,
            action="執行新版重檢",
        )
        if request.status != "RESUBMITTED":
            raise AppError(
                "CORRECTION_RECHECK_INVALID",
                "只有已回件的修正通知可執行新版重檢",
                409,
            )
        # Registering a response document does not create the immutable
        # Valuation submission that Review must execute.  For submitted
        # Reviews, refuse to rerun the same snapshot; the Valuation submit
        # flow must first create a newer Submission and update this pointer.
        previous_run = await self.review_repository.get_run(
            request.based_on_validation_run_id
        )
        previous_submission_id = (
            None
            if previous_run is None
            else getattr(previous_run, "submission_id", None)
        )
        latest_submission_id = getattr(review, "latest_submission_id", None)
        if previous_submission_id is not None and (
            latest_submission_id is None
            or latest_submission_id == previous_submission_id
        ):
            raise AppError(
                "REVIEW_RESUBMISSION_REQUIRED",
                "回件後必須先由估價流程建立較新的送審版本",
                409,
            )
        if latest_submission_id is not None:
            latest_submission = (
                await self.review_repository.get_submission_provenance_by_id(
                    latest_submission_id,
                    review_id=review.review_id,
                    case_id=review.case_id,
                )
            )
            if latest_submission is None:
                raise AppError(
                    "CORRECTION_RECHECK_SUBMISSION_INVALID",
                    "目前送審版本不存在或不屬於此審查案件",
                    409,
                )
            if (
                latest_submission.get("source_report_document_id")
                != request.response_document_id
            ):
                raise AppError(
                    "CORRECTION_RECHECK_DOCUMENT_MISMATCH",
                    "新版回件文件與目前送審版本不一致，無法執行新版重檢",
                    409,
                )

        request.status = "RECHECKING"
        await self.corrections.session.flush()

        # Move the review back through preprocessing and completeness before the
        # run, exactly like a normal revised-version re-analysis.
        if review.review_status == "RETURNED_FOR_REVISION":
            review.review_status = ensure_transition(
                review.review_status, "PREPROCESSING"
            )
            await self.review_repository.session.flush()
        result, review, _items = await self._review_service.check_completeness(
            review.review_id, actor_id
        )
        if not result.ready:
            # Revert to RESUBMITTED and surface the normal missing-item response.
            request.status = "RESUBMITTED"
            await self.corrections.session.flush()
            return None, result

        run, summary = await self._review_service.rerun(review.review_id, actor_id)

        new_findings = await self.review_repository.list_findings(
            run.validation_run_id
        )
        by_supersedes: dict = {}
        for finding in new_findings:
            if finding.supersedes_finding_id is not None:
                by_supersedes.setdefault(finding.supersedes_finding_id, []).append(
                    finding
                )

        now = datetime.now(UTC)
        items = await self.corrections.list_items(request.correction_request_id)
        for item in items:
            matches = by_supersedes.get(item.finding_id, [])
            if len(matches) > 1:
                item.recheck_outcome = "NOT_EVALUATED"
                item.resulting_finding_id = None
            elif len(matches) == 1:
                item.recheck_outcome = "STILL_PRESENT"
                item.resulting_finding_id = matches[0].finding_id
            else:
                item.recheck_outcome = "RESOLVED"
                item.resulting_finding_id = None
            item.rechecked_at = now

        request.status = "RECHECKED"
        request.rechecked_by_user_id = actor_id
        request.rechecked_at = now
        await self.corrections.session.flush()
        return run, summary

    async def _completion_summary(self, review) -> ReviewCompletionSummary:
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
        missing = await self.review_repository.list_missing_items(
            review.review_id, open_only=True
        )
        from app.review.demo_policy import ADVISORY_ITEM_CODES
        if await ReviewService(self.review_repository)._demo_advisory(review):
            missing = [item for item in missing if item.item_code not in ADVISORY_ITEM_CODES]
        open_count = sum(1 for f in findings if f.status in _OPEN_STATUSES)
        confirmed = sum(1 for f in findings if f.status == _CONFIRMED_STATUS)
        expert = sum(1 for f in findings if f.status in _EXPERT_STATUSES)
        return ReviewCompletionSummary(
            has_completed_run=bool(run and run.run_status == "COMPLETED"),
            open_missing_count=len(missing),
            open_finding_count=open_count,
            confirmed_finding_count=confirmed,
            expert_finding_count=expert,
            active_request_count=await self.corrections.count_active_requests(
                review.review_id
            ),
            non_rechecked_request_count=0,
            not_evaluated_item_count=await self.corrections.count_not_evaluated_items(
                review.review_id
            ),
        )

    async def complete_review(self, review_id, reason, actor_id, audit_request_id):
        review_probe = await self.review_repository.get(review_id)
        if review_probe is None:
            raise ResourceNotFoundError("審查案件")
        case = await self.review_repository.get_case(
            review_probe.case_id, for_update=True
        )
        if case is None:
            raise ResourceNotFoundError("估價案件")
        review = await self.review_repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if review.case_id != case.case_id:
            raise AppError(
                "REVIEW_CASE_OWNERSHIP_CONFLICT",
                "審查案件與估價案件關聯已變更",
                409,
            )
        if review.review_status == "REVIEW_COMPLETED":
            raise AppError(
                "REVIEW_ALREADY_COMPLETED",
                "審查案件已完成，不可重複核定",
                409,
            )
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_COMPLETION_STATUSES,
            action="完成審查",
        )
        run = (
            await self.review_repository.get_run(review.latest_validation_run_id)
            if review.latest_validation_run_id
            else None
        )
        if run is not None and getattr(run, "submission_id", None) != getattr(
            review, "latest_submission_id", None
        ):
            raise AppError(
                "REVIEW_SUBMISSION_STALE",
                "審查批次不是目前送審版本，請重新執行最新版本檢核",
                409,
            )
        summary = await self._completion_summary(review)
        validate_review_completion(reason, summary)
        if await ReviewService(self.review_repository)._demo_advisory(review):
            reason = "Demo 展示完成（缺件及未執行規則仍保留，不代表正式審查通過）。" + reason
        before_status = review.review_status
        decision = await self.review_repository.create_decision(
            review_id=review.review_id,
            finding_id=None,
            decision="APPROVED",
            reason=reason.strip(),
            decided_by_user_id=actor_id,
            request_id=audit_request_id,
            before_value={"review_status": before_status},
            after_value={
                "review_status": "REVIEW_COMPLETED",
                "validation_run_id": str(review.latest_validation_run_id),
            },
        )
        review.review_status = "REVIEW_COMPLETED"
        case.case_status = "REVIEW_COMPLETED"
        review.completed_at = datetime.now(UTC)
        await self.review_repository.session.flush()
        return decision
