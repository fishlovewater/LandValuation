from datetime import UTC, datetime

from app.core.exceptions import AppError
from app.core.exceptions import ResourceNotFoundError
from app.review.repository import ReviewRepository
from app.review.schemas import ReviewCreate, ReviewListQuery, ReviewUpdate
from app.review.completeness import evaluate_completeness
from app.review.recalculation import recalculate_adjustment_rate
from app.review.risks import FindingRisk, risk_level_for_findings


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

    async def check_completeness(self, review_id, actor_id):
        review = await self.repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if review.review_status in {"RECEIVED", "PENDING_MATERIALS"}:
            review.review_status = ensure_transition(
                review.review_status, "PREPROCESSING"
            )
        if review.review_status != "PREPROCESSING":
            raise AppError(
                "REVIEW_STATE_CONFLICT",
                "目前狀態不可執行文件完整性檢查",
                409,
                {"current": review.review_status},
            )

        snapshot = await self.repository.load_case_snapshot(review.case_id)
        result = evaluate_completeness(snapshot)
        items = await self.repository.sync_missing_items(
            review_id, result.items, actor_id
        )
        review.missing_item_count = len(items)
        review.review_status = ensure_transition(
            "PREPROCESSING",
            "READY_FOR_REVIEW" if result.ready else "PENDING_MATERIALS",
        )
        await self.repository.session.flush()
        return result, review, items

    async def list_missing_items(self, review_id):
        await self.get(review_id)
        return await self.repository.list_missing_items(review_id)

    async def request_supplement(self, review_id, due_at):
        await self.get(review_id)
        if due_at <= datetime.now(due_at.tzinfo):
            raise AppError("INVALID_DUE_AT", "補件期限必須晚於目前時間", 422)
        return await self.repository.request_supplement(review_id, due_at)

    async def create_run(self, review_id, payload, actor_id):
        review = await self.repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if await self.repository.active_run_exists(review_id):
            raise AppError("RUN_ALREADY_ACTIVE", "此案件已有執行中的檢核", 409)
        review.review_status = ensure_transition(
            review.review_status, "ANALYZING"
        )
        run = await self.repository.create_run(review, payload, actor_id)
        findings = []
        for check in payload.adjustment_checks:
            result = recalculate_adjustment_rate(
                check.reported_rate, check.system_rate, check.tolerance
            )
            if result.within_tolerance:
                run.passed_count += 1
                continue
            machine_finding = await self.repository.create_validation_finding(
                validation_run_id=run.validation_run_id,
                validation_rule_id=check.validation_rule_id,
                field_code=check.field_path,
                severity="HIGH",
                actual_value={"reported_rate": str(result.reported_rate)},
                expected_value={"system_rate": str(result.system_rate)},
                finding_message="報告調整率與規則計算結果不一致",
            )
            finding = await self.repository.create_finding(
                review_id=review.review_id,
                source_validation_finding_id=machine_finding.finding_id,
                validation_run_id=run.validation_run_id,
                finding_code=check.finding_code,
                finding_type="RATE_OUT_OF_RANGE",
                severity="HIGH",
                title="調整率超出允許差異",
                description="報告調整率與確定性重算結果不一致，需人工核對。",
                status="OPEN",
                document_id=check.document_id,
                document_version=check.document_version,
                page_number=check.page_number,
                field_path=check.field_path,
                source_evidence=check.source_evidence,
                reported_text=check.reported_text,
                reported_value=str(result.reported_rate),
                legal_basis=check.legal_basis,
                reported_adjustment_rate=result.reported_rate,
                system_adjustment_rate=result.system_rate,
                comparison_result={
                    "difference": str(result.difference),
                    "tolerance": str(check.tolerance),
                    "within_tolerance": False,
                },
                recommended_action={"action": "VERIFY_ADJUSTMENT_BASIS"},
                ai_status="AI_EXPLANATION_UNAVAILABLE",
                rule_version_id=payload.rule_version_id,
            )
            findings.append(finding)
            run.failed_count += 1

        risk = risk_level_for_findings(
            [FindingRisk(item.finding_type, item.severity) for item in findings]
        )
        summary = await self.repository.create_risk_summary(
            review_id=review.review_id,
            validation_run_id=run.validation_run_id,
            overall_risk_level=risk.level,
            risk_score={"LOW": 20, "MEDIUM": 50, "HIGH": 80, "CRITICAL": 100}.get(
                risk.level, 0
            ),
            summary=f"本次檢核產生 {len(findings)} 筆未解決疑點。",
            category_scores={"deterministic_findings": len(findings)},
            high_count=risk.high_count,
            medium_count=risk.medium_count,
            low_count=risk.low_count,
            missing_item_count=review.missing_item_count,
            risk_reasons=sorted({item.finding_type for item in findings}),
        )
        now = datetime.now(UTC)
        run.run_status = "COMPLETED"
        run.completed_at = now
        review.latest_validation_run_id = run.validation_run_id
        review.current_risk_level = risk.level
        review.high_count = risk.high_count
        review.medium_count = risk.medium_count
        review.low_count = risk.low_count
        review.review_status = ensure_transition("ANALYZING", "REVIEW_REQUIRED")
        await self.repository.session.flush()
        await self.repository.session.refresh(run)
        return run, summary

    async def list_runs(self, review_id):
        await self.get(review_id)
        return await self.repository.list_runs(review_id)

    async def get_run(self, validation_run_id):
        run = await self.repository.get_run(validation_run_id)
        if run is None:
            raise ResourceNotFoundError("檢核批次")
        return run

    async def list_findings(self, validation_run_id):
        await self.get_run(validation_run_id)
        return await self.repository.list_findings(validation_run_id)

    async def get_finding(self, finding_id):
        finding = await self.repository.get_finding(finding_id)
        if finding is None:
            raise ResourceNotFoundError("審查疑點")
        return finding

    async def get_risk_summary(self, validation_run_id):
        await self.get_run(validation_run_id)
        summary = await self.repository.get_risk_summary(validation_run_id)
        if summary is None:
            raise ResourceNotFoundError("風險摘要")
        return summary
