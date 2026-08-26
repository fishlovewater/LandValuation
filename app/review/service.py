from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import AppError
from app.core.exceptions import ResourceNotFoundError
from app.review.repository import ReviewRepository
from app.review.schemas import ReviewCreate, ReviewListQuery, ReviewUpdate
from app.review.completeness import (
    CompletenessResult,
    evaluate_completeness,
    trusted_context_missing_requirement,
    trusted_preflight_to_missing,
    trusted_problem_to_missing,
)
from app.review.risks import FindingRisk, risk_level_for_findings
from app.review.decisions import (
    CaseDecisionCommand,
    FindingDecisionCommand,
    ReviewGateSummary,
    validate_case_decision,
    validate_finding_decision,
)
from app.review.reports import (
    ReportCase,
    ReportDecision,
    ReportRiskSummary,
    ReportRun,
    ReviewReportInput,
    build_review_report,
)
from app.review.schemas import FindingRead
from app.review.rule_selection import RuleCandidate, select_effective_rule
from app.review.trusted_inputs import (
    TrustedField,
    required_field_problems,
    trusted_fields_by_code,
    TrustedRunContext,
    prepare_trusted_rules,
    validate_rule_contracts,
)


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
        if payload.review_status in {
            "RETURNED_FOR_REVISION",
            "SUPPLEMENT_REQUIRED",
            "EXPERT_REVIEW",
            "APPROVED",
            "REVIEW_COMPLETED",
        }:
            raise AppError(
                "REVIEW_DECISION_INVALID",
                "人工決策狀態只能透過 decision API 變更",
                409,
            )
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
        if result.ready:
            trusted_items = await self._trusted_completeness_missing_items(
                review.case_id
            )
            if trusted_items:
                result = CompletenessResult(
                    ready=False,
                    items=result.items + trusted_items,
                    blocked_rule_codes=(
                        result.blocked_rule_codes
                        | frozenset(
                            code
                            for item in trusted_items
                            for code in item.blocked_rule_codes
                        )
                    ),
                )
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

    async def _trusted_completeness_missing_items(self, case_id):
        document = await self.repository.get_latest_original_document(case_id)
        if document is None:
            return (trusted_context_missing_requirement(),)

        extraction = await self.repository.get_latest_completed_extraction(
            document["document_id"], document["version_no"]
        )
        if extraction is None:
            return (trusted_context_missing_requirement(),)

        field_rows = await self.repository.list_official_extracted_fields(
            extraction["extraction_run_id"]
        )
        fields = trusted_fields_by_code(
            TrustedField(
                extracted_field_id=str(row["extracted_field_id"]),
                field_code=row["field_code"],
                field_path=row["field_path"],
                raw_text=row["raw_text"],
                normalized_value=row["normalized_value"],
                value_type=row["value_type"],
                page_number=row["page_number"],
                verification_status=row["verification_status"],
                is_official=row["is_official"],
            )
            for row in field_rows
        )
        case_context = await self.repository.get_case_rule_context(case_id)
        if case_context is None:
            return (trusted_context_missing_requirement(),)
        candidates = await self.repository.list_rule_candidates()
        candidates_by_id = {
            str(candidate["rule_version_id"]): candidate for candidate in candidates
        }
        selection = select_effective_rule(
            (
                RuleCandidate(
                    rule_version_id=str(candidate["rule_version_id"]),
                    status=candidate["status"],
                    effective_from=candidate["effective_from"],
                    effective_to=candidate["effective_to"],
                    case_type=candidate["applicable_case_type"],
                    district_code=candidate["applicable_district_code"],
                    priority=candidate["selection_priority"],
                )
                for candidate in candidates
            ),
            case_context["valuation_base_date"],
            case_context["case_type"],
            case_context["district_code"],
            case_context["form_codes"],
        )
        if selection.rule is None:
            return (trusted_context_missing_requirement(),)

        selected_candidate = candidates_by_id[selection.rule.rule_version_id]
        source_document_id = selected_candidate["source_document_id"]
        if source_document_id is None or await self.repository.get_rule_source(
            UUID(str(source_document_id))
        ) is None:
            return (trusted_context_missing_requirement(),)

        active_rules = await self.repository.list_active_rules(
            UUID(selection.rule.rule_version_id), case_context["form_codes"]
        )
        if not active_rules:
            return (trusted_context_missing_requirement(),)
        try:
            contracts = validate_rule_contracts(active_rules)
        except AppError as error:
            return (trusted_preflight_to_missing(error),)
        required_codes = {contract.target_field_code for contract in contracts}
        problems = required_field_problems(required_codes, fields)
        if problems:
            return tuple(
                trusted_problem_to_missing(problem)
                for problem in problems
            )
        try:
            prepare_trusted_rules(contracts, fields)
        except AppError as error:
            return (trusted_preflight_to_missing(error),)
        return ()

    async def list_missing_items(self, review_id):
        await self.get(review_id)
        return await self.repository.list_missing_items(review_id)

    async def request_supplement(self, review_id, due_at):
        await self.get(review_id)
        if due_at <= datetime.now(due_at.tzinfo):
            raise AppError("INVALID_DUE_AT", "補件期限必須晚於目前時間", 422)
        return await self.repository.request_supplement(review_id, due_at)

    async def _resolve_trusted_run_context(self, review) -> TrustedRunContext:
        document = await self.repository.get_latest_original_document(review.case_id)
        if document is None:
            raise AppError(
                "TRUSTED_INPUT_MISSING",
                "案件沒有可用的正式原始估價報告",
                409,
            )

        extraction_run = await self.repository.get_latest_completed_extraction(
            document["document_id"], document["version_no"]
        )
        if extraction_run is None:
            raise AppError(
                "TRUSTED_INPUT_MISSING",
                "正式原始估價報告尚無完成的欄位抽取結果",
                409,
            )

        field_rows = await self.repository.list_official_extracted_fields(
            extraction_run["extraction_run_id"]
        )
        fields = trusted_fields_by_code(
            TrustedField(
                extracted_field_id=str(row["extracted_field_id"]),
                field_code=row["field_code"],
                field_path=row["field_path"],
                raw_text=row["raw_text"],
                normalized_value=row["normalized_value"],
                value_type=row["value_type"],
                page_number=row["page_number"],
                verification_status=row["verification_status"],
                is_official=row["is_official"],
            )
            for row in field_rows
        )

        case_context = await self.repository.get_case_rule_context(review.case_id)
        if case_context is None:
            raise AppError(
                "RULE_SELECTION_CONFLICT",
                "案件不存在，無法選擇適用規則",
                409,
            )
        candidates = await self.repository.list_rule_candidates()
        candidates_by_id = {
            str(candidate["rule_version_id"]): candidate for candidate in candidates
        }
        selection = select_effective_rule(
            (
                RuleCandidate(
                    rule_version_id=str(candidate["rule_version_id"]),
                    status=candidate["status"],
                    effective_from=candidate["effective_from"],
                    effective_to=candidate["effective_to"],
                    case_type=candidate["applicable_case_type"],
                    district_code=candidate["applicable_district_code"],
                    priority=candidate["selection_priority"],
                )
                for candidate in candidates
            ),
            case_context["valuation_base_date"],
            case_context["case_type"],
            case_context["district_code"],
            case_context["form_codes"],
        )
        if selection.rule is None:
            raise AppError(
                "RULE_SELECTION_CONFLICT",
                "案件條件找不到可用的正式規則版本",
                409,
            )
        rule_version = candidates_by_id[selection.rule.rule_version_id]

        source_document_id = rule_version["source_document_id"]
        rule_source = (
            await self.repository.get_rule_source(UUID(str(source_document_id)))
            if source_document_id is not None
            else None
        )
        if rule_source is None:
            raise AppError(
                "RULE_SOURCE_UNAVAILABLE",
                "正式規則版本缺少已發布且已抽取的法規來源",
                409,
            )

        validation_rules = tuple(
            await self.repository.list_active_rules(
                UUID(selection.rule.rule_version_id), case_context["form_codes"]
            )
        )
        if not validation_rules:
            raise AppError(
                "RULE_SELECTION_CONFLICT",
                "正式規則版本沒有適用的啟用檢核規則",
                409,
            )

        contracts = validate_rule_contracts(validation_rules)
        required_codes = {contract.target_field_code for contract in contracts}
        problems = required_field_problems(required_codes, fields)
        if problems:
            problem = problems[0]
            raise AppError(
                problem.code,
                f"正式抽取欄位不可用：{problem.field_code}",
                409,
                {"field_code": problem.field_code},
            )
        prepared_rules = prepare_trusted_rules(contracts, fields)

        return TrustedRunContext(
            document=document,
            extraction_run=extraction_run,
            fields=fields,
            rule_version=rule_version,
            validation_rules=validation_rules,
            rule_source=rule_source,
            prepared_rules=prepared_rules,
        )

    @staticmethod
    def _source_evidence(document: dict, field: TrustedField):
        return [
            {
                "source_id": field.extracted_field_id,
                "extracted_field_id": field.extracted_field_id,
                "document_id": str(document["document_id"]),
                "document_version": document["version_no"],
                "page": field.page_number,
                "field_path": field.field_path,
                "excerpt": field.raw_text,
            }
        ]

    @staticmethod
    def _legal_basis(context: TrustedRunContext, rule: dict):
        return [
            {
                "rule_version_id": str(context.rule_version["rule_version_id"]),
                "rule_code": rule["rule_code"],
                "document_id": str(context.rule_source["document_id"]),
                "document_version": context.rule_source["version_no"],
                "checksum_sha256": context.rule_source["checksum_sha256"],
            }
        ]

    @staticmethod
    def _input_snapshot(review, context: TrustedRunContext) -> dict:
        checks = []
        for prepared_rule in context.prepared_rules:
            rule = prepared_rule.rule
            field = prepared_rule.field
            checks.append(
                {
                    "finding_code": f"{rule['rule_code']}:{field.extracted_field_id}",
                    "validation_rule_id": str(rule["validation_rule_id"]),
                    "rule_code": rule["rule_code"],
                    "extracted_field_id": field.extracted_field_id,
                    "document_id": str(context.document["document_id"]),
                    "document_version": context.document["version_no"],
                    "document_checksum": context.document["checksum_sha256"],
                    "page_number": field.page_number,
                    "field_path": field.field_path,
                    "reported_value": str(
                        prepared_rule.reported_rate
                        if prepared_rule.reported_rate is not None
                        else prepared_rule.reported_grade
                    ),
                    "rule_configuration": prepared_rule.configuration,
                }
            )
        return {
            "case_id": str(review.case_id),
            "rule_version_id": str(context.rule_version["rule_version_id"]),
            "document": {
                "document_id": str(context.document["document_id"]),
                "version_no": context.document["version_no"],
                "checksum_sha256": context.document["checksum_sha256"],
            },
            "extraction_run": {
                "extraction_run_id": str(context.extraction_run["extraction_run_id"]),
                "run_no": context.extraction_run["run_no"],
            },
            "validation_rule_ids": [
                str(rule["validation_rule_id"]) for rule in context.validation_rules
            ],
            "checks": checks,
        }

    async def create_run(self, review_id, actor_id, supersedes_by_code=None):
        review = await self.repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if await self.repository.active_run_exists(review_id):
            raise AppError("RUN_ALREADY_ACTIVE", "此案件已有執行中的檢核", 409)

        context = await self._resolve_trusted_run_context(review)
        input_snapshot = self._input_snapshot(review, context)

        review.review_status = ensure_transition(review.review_status, "ANALYZING")
        run = await self.repository.create_run(
            review,
            actor_id,
            UUID(str(context.rule_version["rule_version_id"])),
            input_snapshot,
        )
        findings = []
        for prepared_rule in context.prepared_rules:
            rule = prepared_rule.rule
            field = prepared_rule.field
            finding_code = f"{rule['rule_code']}:{field.extracted_field_id}"
            if rule["rule_code"] == "ADJUSTMENT_RATE":
                result = prepared_rule.adjustment_result
                if result is None:
                    raise RuntimeError("調整率規則未完成 trusted preflight")
                if result.within_tolerance:
                    run.passed_count += 1
                    continue
                machine_finding = await self.repository.create_validation_finding(
                    validation_run_id=run.validation_run_id,
                    validation_rule_id=rule["validation_rule_id"],
                    field_code=field.field_path,
                    severity=rule["severity"],
                    actual_value={"reported_rate": str(result.reported_rate)},
                    expected_value={"system_rate": str(result.system_rate)},
                    finding_message="報告調整率與規則計算結果不一致",
                )
                finding = await self.repository.create_finding(
                    review_id=review.review_id,
                    source_validation_finding_id=machine_finding.finding_id,
                    validation_run_id=run.validation_run_id,
                    finding_code=finding_code,
                    finding_type="RATE_OUT_OF_RANGE",
                    severity=rule["severity"],
                    title="調整率超出允許差異",
                    description="報告調整率與確定性重算結果不一致，需人工核對。",
                    status="OPEN",
                    document_id=context.document["document_id"],
                    document_version=context.document["version_no"],
                    page_number=field.page_number,
                    field_path=field.field_path,
                    source_evidence=self._source_evidence(context.document, field),
                    reported_text=field.raw_text,
                    reported_value=str(result.reported_rate),
                    legal_basis=self._legal_basis(context, rule),
                    reported_adjustment_rate=result.reported_rate,
                    system_adjustment_rate=result.system_rate,
                    comparison_result={
                        "difference": str(result.difference),
                        "tolerance": str(prepared_rule.tolerance),
                        "within_tolerance": False,
                    },
                    recommended_action={"action": "VERIFY_ADJUSTMENT_BASIS"},
                    ai_status="AI_EXPLANATION_UNAVAILABLE",
                    supersedes_finding_id=(supersedes_by_code or {}).get(finding_code),
                    rule_version_id=context.rule_version["rule_version_id"],
                )
                findings.append(finding)
                run.failed_count += 1
            elif rule["rule_code"] == "EXPERT_GRADE":
                reported_grade = prepared_rule.reported_grade
                system_grade = prepared_rule.system_grade
                if reported_grade == system_grade:
                    run.passed_count += 1
                    continue
                machine_finding = await self.repository.create_validation_finding(
                    validation_run_id=run.validation_run_id,
                    validation_rule_id=rule["validation_rule_id"],
                    field_code=field.field_path,
                    severity="MEDIUM",
                    actual_value={"reported_grade": reported_grade},
                    expected_value={"system_grade": system_grade},
                    finding_message="報告級距與規則建議級距不同，需專業判斷",
                )
                finding = await self.repository.create_finding(
                    review_id=review.review_id,
                    source_validation_finding_id=machine_finding.finding_id,
                    validation_run_id=run.validation_run_id,
                    finding_code=finding_code,
                    finding_type="EXPERT_GRADE_JUDGMENT",
                    severity="MEDIUM",
                    title="級距判定需專業覆核",
                    description="報告級距與規則建議級距不同，系統不自行取代估價專業判斷。",
                    status="OPEN",
                    document_id=context.document["document_id"],
                    document_version=context.document["version_no"],
                    page_number=field.page_number,
                    field_path=field.field_path,
                    source_evidence=self._source_evidence(context.document, field),
                    reported_text=field.raw_text,
                    reported_value=reported_grade,
                    legal_basis=self._legal_basis(context, rule),
                    reported_grade=reported_grade,
                    system_grade=system_grade,
                    comparison_result={"same_grade": False},
                    recommended_action={"action": "EXPERT_REVIEW"},
                    ai_status="AI_EXPLANATION_UNAVAILABLE",
                    supersedes_finding_id=(supersedes_by_code or {}).get(finding_code),
                    rule_version_id=context.rule_version["rule_version_id"],
                )
                findings.append(finding)
                run.warning_count += 1

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

    async def decide_finding(
        self, finding_id, payload, actor_id, request_id
    ):
        review = await self.repository.get(payload.review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if review.review_status not in {"REVIEW_REQUIRED", "EXPERT_REVIEW"}:
            raise AppError(
                "REVIEW_STATE_CONFLICT",
                "目前案件狀態不可變更疑點決策",
                409,
                {"current": review.review_status},
            )
        finding = await self.repository.get_finding_for_review(
            finding_id, payload.review_id, for_update=True
        )
        if finding is None:
            raise ResourceNotFoundError("審查疑點")
        resulting_status = validate_finding_decision(
            FindingDecisionCommand(
                payload.decision, payload.reason, payload.after_value
            )
        )
        before = {
            "status": finding.status,
            "recommended_action": finding.recommended_action,
        }
        finding.status = resulting_status
        decision = await self.repository.create_decision(
            review_id=finding.review_id,
            finding_id=finding.finding_id,
            decision=payload.decision,
            reason=payload.reason.strip(),
            decided_by_user_id=actor_id,
            request_id=request_id,
            before_value=before,
            after_value=payload.after_value or {"status": resulting_status},
        )
        counts = await self.repository.current_risk_counts(finding.review_id)
        review.high_count = counts["high"]
        review.medium_count = counts["medium"]
        review.low_count = counts["low"]
        review.current_risk_level = (
            "CRITICAL"
            if counts["critical"]
            else "HIGH"
            if counts["high"]
            else "MEDIUM"
            if counts["medium"]
            else "LOW"
        )
        await self.repository.session.flush()
        return decision

    async def decide_case(
        self,
        review_id,
        payload,
        actor_id,
        request_id,
        has_override_permission=False,
    ):
        review = await self.repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        unresolved = await self.repository.unresolved_high_count(review_id)
        resulting_status = validate_case_decision(
            CaseDecisionCommand(
                decision=payload.decision,
                reason=payload.reason,
                has_override_permission=has_override_permission,
                override_reason=payload.override_reason,
            ),
            ReviewGateSummary(unresolved),
        )
        before_status = review.review_status
        review.review_status = ensure_transition(before_status, resulting_status)
        reason = payload.reason.strip()
        if payload.override_reason and payload.override_reason.strip():
            reason = f"{reason}\n覆核理由：{payload.override_reason.strip()}"
        return await self.repository.create_decision(
            review_id=review_id,
            finding_id=None,
            decision=payload.decision,
            reason=reason,
            decided_by_user_id=actor_id,
            request_id=request_id,
            before_value={"review_status": before_status},
            after_value={"review_status": resulting_status},
        )

    async def list_decisions(self, review_id):
        await self.get(review_id)
        return await self.repository.list_decisions(review_id)

    async def rerun(self, review_id, actor_id):
        review = await self.repository.get(review_id)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        previous = []
        if review.latest_validation_run_id:
            previous = await self.repository.list_findings(
                review.latest_validation_run_id
            )
        supersedes = {item.finding_code: item.finding_id for item in previous}
        run, summary = await self.create_run(review_id, actor_id, supersedes)
        return run, summary

    async def build_report(self, validation_run_id):
        run = await self.get_run(validation_run_id)
        review = await self.get(run.review_id)
        case = await self.repository.get_case_report_data(run.case_id)
        findings = await self.repository.list_findings(validation_run_id)
        risk = await self.get_risk_summary(validation_run_id)
        decisions = await self.repository.list_decisions(review.review_id)
        data = ReviewReportInput(
            case=ReportCase(**case),
            run=ReportRun(
                validation_run_id=run.validation_run_id,
                run_no=run.run_no,
                run_status=run.run_status,
                rule_version_id=run.rule_version_id,
                model_id=run.model_id,
                prompt_version=run.prompt_version,
                started_at=run.started_at,
                completed_at=run.completed_at,
            ),
            review_status=review.review_status,
            missing_item_count=review.missing_item_count,
            findings=[
                FindingRead.model_validate(item).model_dump(mode="json")
                for item in findings
            ],
            risk_summary=ReportRiskSummary(
                overall_risk_level=risk.overall_risk_level,
                high_count=risk.high_count,
                medium_count=risk.medium_count,
                low_count=risk.low_count,
                missing_item_count=risk.missing_item_count,
                risk_reasons=risk.risk_reasons,
            ),
            decisions=[
                ReportDecision(
                    decision_id=item.decision_id,
                    finding_id=item.finding_id,
                    decision=item.decision,
                    reason=item.reason or "",
                    decided_by_user_id=item.decided_by_user_id,
                    decided_at=item.decided_at,
                    before_value=item.before_value,
                    after_value=item.after_value,
                )
                for item in decisions
            ],
        )
        return build_review_report(data)
