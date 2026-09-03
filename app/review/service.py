from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.exceptions import AppError
from app.core.exceptions import ResourceNotFoundError
from app.review.repository import ReviewRepository
from app.review.correction_repository import CorrectionRepository
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
    FindingTriageCommand,
    FindingValueContext,
    ReviewGateSummary,
    build_finding_after_value,
    validate_case_decision,
    validate_finding_decision,
    validate_finding_triage,
)
from app.review.reports import (
    ReportCase,
    ReportCorrectionItem,
    ReportCorrectionRequest,
    ReportDecision,
    ReportHistoryEvent,
    ReportRiskSummary,
    ReportRun,
    ReportUrgency,
    ReviewReportInput,
    build_review_report,
)
from app.review.urgency import classify_urgency
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
from app.valuation.submissions.snapshot import SNAPSHOT_SCHEMA_VERSION


def _first_present(*values):
    return next((value for value in values if value is not None), None)


def _decision_has_final_value(decision) -> bool:
    if decision is None or not isinstance(decision.after_value, dict):
        return False
    source = decision.after_value.get("selection_source")
    value = decision.after_value.get("value")
    return source in {"REPORTED", "SYSTEM", "REVIEWER"} and (
        not isinstance(value, str) or bool(value.strip())
    ) and value is not None


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "RECEIVED": frozenset({"PREPROCESSING"}),
    "PREPROCESSING": frozenset({"PENDING_MATERIALS", "READY_FOR_REVIEW"}),
    "PENDING_MATERIALS": frozenset({"PREPROCESSING"}),
    "READY_FOR_REVIEW": frozenset({"PREPROCESSING", "ANALYZING"}),
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

    @staticmethod
    def _trusted_field(row: dict) -> TrustedField:
        return TrustedField(
            extracted_field_id=str(row["extracted_field_id"]),
            form_code=row["form_code"],
            field_name=row["field_name"],
            confirmed_value=row["confirmed_value"],
            source_page=row["source_page"],
            source_text=row["source_text"],
            confidence=row["confidence"],
            field_status=row["field_status"],
            confirmed_by_user_id=(
                str(row["confirmed_by_user_id"])
                if row["confirmed_by_user_id"] is not None
                else None
            ),
            confirmed_at=row["confirmed_at"],
        )

    @staticmethod
    def _trusted_field_from_submission(item: dict) -> TrustedField:
        """Adapt one server-built Submission Snapshot field to Review input."""
        return TrustedField(
            extracted_field_id=str(item["extracted_field_id"]),
            form_code=item["form_code"],
            field_name=item["field_name"],
            confirmed_value=item["confirmed_value"],
            source_page=item.get("source_page"),
            source_text=item.get("source_text"),
            confidence=item.get("confidence"),
            field_status="APPLIED",
            confirmed_by_user_id=(
                str(item["confirmed_by_user_id"])
                if item.get("confirmed_by_user_id") is not None
                else None
            ),
            confirmed_at=item.get("confirmed_at"),
        )

    @staticmethod
    def _invalid_submission_snapshot() -> AppError:
        return AppError(
            "SUBMISSION_SNAPSHOT_INVALID",
            "送審快照缺少可供審查的完整欄位證據",
            409,
        )

    @classmethod
    def _snapshot_trusted_inputs(
        cls, snapshot: dict | None
    ) -> tuple[dict, tuple[TrustedField, ...]]:
        """Validate and extract the immutable document/field input boundary."""
        invalid = cls._invalid_submission_snapshot
        if not isinstance(snapshot, dict):
            raise invalid()
        if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise invalid()

        applied_fields = snapshot.get("applied_fields")
        documents = snapshot.get("documents")
        if not isinstance(applied_fields, list) or not applied_fields:
            raise invalid()
        if not isinstance(documents, list) or not documents:
            raise invalid()

        documents_by_id = {}
        for document in documents:
            if not isinstance(document, dict):
                raise invalid()
            document_id = document.get("document_id")
            if not isinstance(document_id, str) or not document_id:
                raise invalid()
            if any(
                document.get(key) in (None, "")
                for key in (
                    "document_type",
                    "version_no",
                    "document_group_id",
                    "checksum_sha256",
                )
            ):
                raise invalid()
            if document_id in documents_by_id:
                raise invalid()
            documents_by_id[document_id] = document

        trusted_fields = []
        for item in applied_fields:
            if not isinstance(item, dict):
                raise invalid()
            required_keys = {
                "extracted_field_id",
                "document_id",
                "form_code",
                "field_name",
                "confirmed_value",
                "confidence",
                "field_status",
                "confirmed_by_user_id",
                "confirmed_at",
            }
            if not required_keys.issubset(item):
                raise invalid()
            if (
                not isinstance(item["extracted_field_id"], str)
                or not item["extracted_field_id"]
                or not isinstance(item["document_id"], str)
                or not item["document_id"]
                or not isinstance(item["form_code"], str)
                or not item["form_code"]
                or not isinstance(item["field_name"], str)
                or not item["field_name"]
                or item["confirmed_value"] is None
                or item["confidence"] is None
                or item["field_status"] != "APPLIED"
                or not isinstance(item["confirmed_by_user_id"], str)
                or not item["confirmed_by_user_id"]
                or not isinstance(item["confirmed_at"], str)
                or not item["confirmed_at"]
                or item["document_id"] not in documents_by_id
            ):
                raise invalid()
            trusted_fields.append(cls._trusted_field_from_submission(item))

        document = dict(documents_by_id[applied_fields[0]["document_id"]])
        return document, tuple(trusted_fields)

    async def _trusted_completeness_missing_items(self, case_id):
        document = await self.repository.get_latest_original_document(case_id)
        if document is None:
            return (trusted_context_missing_requirement(),)

        field_rows = await self.repository.list_applied_confirmed_extracted_fields(
            case_id
        )
        fields = trusted_fields_by_code(
            self._trusted_field(row)
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
        if (
            await self._usable_rule_source(
                selected_candidate, case_context["valuation_base_date"]
            )
            is None
        ):
            return (
                trusted_preflight_to_missing(
                    AppError(
                        "RULE_SOURCE_UNAVAILABLE",
                        "正式規則版本缺少適用且可用的法規來源",
                        409,
                    )
                ),
            )

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

    async def _usable_rule_source(
        self, rule_version: dict, valuation_base_date: date
    ):
        source_document_id = rule_version["source_document_id"]
        if source_document_id is None:
            return None
        return await self.repository.get_rule_source(
            UUID(str(source_document_id)), valuation_base_date
        )

    async def list_missing_items(self, review_id):
        await self.get(review_id)
        return await self.repository.list_missing_items(review_id)

    async def request_supplement(self, review_id, due_at):
        await self.get(review_id)
        if due_at <= datetime.now(due_at.tzinfo):
            raise AppError("INVALID_DUE_AT", "補件期限必須晚於目前時間", 422)
        return await self.repository.request_supplement(review_id, due_at)

    async def _resolve_trusted_run_context(self, review) -> TrustedRunContext:
        if review.latest_submission_id is not None:
            snapshot = await self.repository.get_submission_snapshot(
                review.latest_submission_id
            )
            document, official_fields = self._snapshot_trusted_inputs(snapshot)
        else:
            document = await self.repository.get_latest_original_document(
                review.case_id
            )
            if document is None:
                raise AppError(
                    "TRUSTED_INPUT_MISSING",
                    "案件沒有可用的正式原始估價報告",
                    409,
                )

            field_rows = await self.repository.list_applied_confirmed_extracted_fields(
                review.case_id
            )
            official_fields = tuple(
                self._trusted_field(row)
                for row in field_rows
            )
        fields = trusted_fields_by_code(official_fields)

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

        rule_source = await self._usable_rule_source(
            rule_version, case_context["valuation_base_date"]
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
            fields=fields,
            official_fields=official_fields,
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
                "field_code": field.field_code,
                "document_id": str(document["document_id"]),
                "document_version": document["version_no"],
                "page": field.page_number,
                "field_path": field.field_path,
                "bounding_box": ReviewService._json_value(field.bounding_box),
                "excerpt": field.raw_text,
                "verification_status": field.verification_status,
            }
        ]

    @staticmethod
    def _finding_code(rule: dict) -> str:
        return f"{rule['rule_version_id']}:{rule['validation_rule_id']}"

    @staticmethod
    def _legal_basis(context: TrustedRunContext, rule: dict):
        return [
            {
                "rule_version_id": str(context.rule_version["rule_version_id"]),
                "rule_set_code": context.rule_version["rule_set_code"],
                "version_name": context.rule_version["version_name"],
                "version_no": context.rule_version["version_no"],
                "rule_code": rule["rule_code"],
                "rule_name": rule["rule_name"],
                "document_id": str(context.rule_source["document_id"]),
                "document_version": context.rule_source["version_no"],
                "checksum_sha256": context.rule_source["checksum_sha256"],
                "effective_from": ReviewService._json_value(
                    context.rule_source["effective_from"]
                ),
                "effective_to": ReviewService._json_value(
                    context.rule_source["effective_to"]
                ),
            }
        ]

    @staticmethod
    def _json_value(value):
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {
                str(key): ReviewService._json_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [ReviewService._json_value(item) for item in value]
        return value

    @staticmethod
    def _field_snapshot(field: TrustedField) -> dict:
        return {
            "extracted_field_id": field.extracted_field_id,
            "field_code": field.field_code,
            "raw_value": field.raw_text,
            "normalized_value": ReviewService._json_value(field.normalized_value),
            "value_type": field.value_type,
            "verification_status": field.verification_status,
            "verified_by_user_id": field.verified_by_user_id,
            "verified_at": ReviewService._json_value(field.verified_at),
            "page": field.page_number,
            "bounding_box": ReviewService._json_value(field.bounding_box),
            "confidence": ReviewService._json_value(field.confidence),
            "is_official": field.is_official,
            "field_path": field.field_path,
            "excerpt": field.raw_text,
        }

    @staticmethod
    def _input_snapshot(review, case: dict, context: TrustedRunContext) -> dict:
        checks = []
        for prepared_rule in context.prepared_rules:
            rule = prepared_rule.rule
            field = prepared_rule.field
            checks.append(
                {
                    "finding_code": ReviewService._finding_code(rule),
                    "validation_rule_id": str(rule["validation_rule_id"]),
                    "rule_code": rule["rule_code"],
                    **ReviewService._field_snapshot(field),
                    "reported_value": str(
                        prepared_rule.reported_rate
                        if prepared_rule.reported_rate is not None
                        else prepared_rule.reported_grade
                    ),
                    "rule_configuration": ReviewService._json_value(
                        prepared_rule.configuration
                    ),
                }
            )
        return {
            "case": {
                key: ReviewService._json_value(value) for key, value in case.items()
            },
            "document": {
                "document_id": str(context.document["document_id"]),
                "version_no": context.document["version_no"],
                "document_group_id": ReviewService._json_value(
                    context.document["document_group_id"]
                ),
                "checksum_sha256": context.document["checksum_sha256"],
            },
            **(
                {
                    "extraction_run": {
                        "extraction_run_id": str(context.extraction_run["extraction_run_id"]),
                        "run_no": context.extraction_run["run_no"],
                        "extractor_name": context.extraction_run["extractor_name"],
                        "extractor_version": context.extraction_run["extractor_version"],
                    }
                }
                if context.extraction_run is not None
                else {
                    "trusted_input_source": {
                        "field_status": "APPLIED",
                        "value_column": "confirmed_value",
                    }
                }
            ),
            "field_snapshots": ReviewService._official_field_snapshots(
                context.official_fields
            ),
            "rule_version": {
                "rule_version_id": str(context.rule_version["rule_version_id"]),
                "status": context.rule_version["status"],
                "effective_from": ReviewService._json_value(
                    context.rule_version["effective_from"]
                ),
                "effective_to": ReviewService._json_value(
                    context.rule_version["effective_to"]
                ),
                "applicable_case_type": context.rule_version["applicable_case_type"],
                "applicable_district_code": context.rule_version[
                    "applicable_district_code"
                ],
                "selection_priority": context.rule_version["selection_priority"],
            },
            "rule_source": {
                "document_id": str(context.rule_source["document_id"]),
                "document_version": context.rule_source["version_no"],
                "checksum_sha256": context.rule_source["checksum_sha256"],
                "effective_from": ReviewService._json_value(
                    context.rule_source["effective_from"]
                ),
                "effective_to": ReviewService._json_value(
                    context.rule_source["effective_to"]
                ),
            },
            "validation_rules": [
                {
                    "validation_rule_id": str(prepared_rule.rule["validation_rule_id"]),
                    "rule_code": prepared_rule.rule["rule_code"],
                    "target_form_code": prepared_rule.rule["target_form_code"],
                    "target_table": prepared_rule.rule["target_table"],
                    "target_field_code": prepared_rule.rule["target_field_code"],
                    "severity": prepared_rule.rule["severity"],
                    "configuration": ReviewService._json_value(
                        prepared_rule.configuration
                    ),
                    "target": prepared_rule.rule["target_field_code"],
                }
                for prepared_rule in context.prepared_rules
            ],
            "validation_rule_ids": [
                str(rule["validation_rule_id"]) for rule in context.validation_rules
            ],
            "checks": checks,
        }

    @staticmethod
    def _official_field_snapshots(fields: tuple[TrustedField, ...]):
        snapshots = []
        field_ids = set()
        for field in fields:
            if field.extracted_field_id in field_ids:
                continue
            field_ids.add(field.extracted_field_id)
            snapshots.append(ReviewService._field_snapshot(field))
        return snapshots

    async def create_run(
        self, review_id, actor_id, supersedes_by_rule_id=None, locked_review=None
    ):
        review = locked_review
        if review is None:
            review = await self.repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if await self.repository.active_run_exists(review_id):
            raise AppError("RUN_ALREADY_ACTIVE", "此案件已有執行中的檢核", 409)

        context = await self._resolve_trusted_run_context(review)
        case = await self.repository.get_case_report_data(review.case_id)
        input_snapshot = self._input_snapshot(review, case, context)

        review.review_status = ensure_transition(review.review_status, "ANALYZING")
        run = await self.repository.create_run(
            review,
            actor_id,
            UUID(str(context.rule_version["rule_version_id"])),
            input_snapshot,
            submission_id=review.latest_submission_id,
        )
        findings = []
        for prepared_rule in context.prepared_rules:
            rule = prepared_rule.rule
            field = prepared_rule.field
            finding_code = self._finding_code(rule)
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
                    field_code=field.field_code,
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
                    supersedes_finding_id=(supersedes_by_rule_id or {}).get(
                        str(rule["validation_rule_id"])
                    ),
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
                    field_code=field.field_code,
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
                    supersedes_finding_id=(supersedes_by_rule_id or {}).get(
                        str(rule["validation_rule_id"])
                    ),
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
        run.completed_at = max(now, run.started_at)
        review.latest_validation_run_id = run.validation_run_id
        review.current_risk_level = risk.level
        review.high_count = risk.high_count
        review.medium_count = risk.medium_count
        review.low_count = risk.low_count
        review.review_status = ensure_transition("ANALYZING", "REVIEW_REQUIRED")
        run.input_snapshot = {
            **run.input_snapshot,
            "report_context": {
                "review_status": review.review_status,
                "missing_item_count": review.missing_item_count,
            },
        }
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

    async def triage_finding(self, finding_id, payload, actor_id, request_id):
        """Confirm, dismiss, or escalate a finding without selecting a value."""
        review = await self.repository.get(payload.review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        if review.review_status not in {"REVIEW_REQUIRED", "EXPERT_REVIEW"}:
            raise AppError(
                "REVIEW_STATE_CONFLICT",
                "目前案件狀態不可判定疑點",
                409,
                {"current": review.review_status},
            )
        finding = await self.repository.get_finding_for_review(
            finding_id, payload.review_id, for_update=True
        )
        if finding is None:
            raise ResourceNotFoundError("審查疑點")
        if (
            finding.validation_run_id != review.latest_validation_run_id
            or finding.status != "OPEN"
        ):
            raise AppError(
                "FINDING_DECISION_CONFLICT",
                "疑點不是最新待判定項目",
                409,
                {"current": finding.status},
            )
        status = validate_finding_triage(
            FindingTriageCommand(payload.decision, payload.reason)
        )
        before = {"status": finding.status}
        finding.status = status
        decision = await self.repository.create_decision(
            review_id=review.review_id,
            finding_id=finding.finding_id,
            decision=status,
            reason=payload.reason.strip(),
            decided_by_user_id=actor_id,
            request_id=request_id,
            before_value=before,
            after_value={"status": status},
        )
        await self._refresh_review_risk_counts(review)
        await self.repository.session.flush()
        return decision

    async def _refresh_review_risk_counts(self, review) -> None:
        counts = await self.repository.current_risk_counts(review.review_id)
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
        if finding.status != "OPEN":
            raise AppError(
                "FINDING_DECISION_CONFLICT",
                "疑點已完成決策，不可再次變更",
                409,
                {"current": finding.status},
            )
        command = FindingDecisionCommand(
            payload.decision, payload.reason, payload.after_value
        )
        resulting_status = validate_finding_decision(command)
        after_value = build_finding_after_value(
            command,
            FindingValueContext(
                field_path=finding.field_path,
                reported_value=_first_present(
                    finding.reported_value,
                    finding.reported_adjustment_rate,
                    finding.reported_grade,
                ),
                system_value=_first_present(
                    finding.system_adjustment_rate,
                    finding.system_grade,
                ),
            ),
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
            after_value=after_value or {"status": resulting_status},
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
        summary = (
            await self._approval_gate_summary(review)
            if payload.decision == "APPROVED"
            else ReviewGateSummary(True, 0, 0, 0)
        )
        resulting_status = validate_case_decision(
            CaseDecisionCommand(
                decision=payload.decision,
                reason=payload.reason,
                has_override_permission=has_override_permission,
                override_reason=payload.override_reason,
            ),
            summary,
        )
        before_status = review.review_status
        if resulting_status == "APPROVED":
            ensure_transition(before_status, "APPROVED")
            ensure_transition("APPROVED", "REVIEW_COMPLETED")
            review.review_status = "REVIEW_COMPLETED"
            review.completed_at = datetime.now(UTC)
        else:
            review.review_status = ensure_transition(before_status, resulting_status)
        reason = payload.reason.strip()
        if payload.override_reason and payload.override_reason.strip():
            reason = f"{reason}\n覆核理由：{payload.override_reason.strip()}"
        after_value = {"review_status": review.review_status}
        if review.latest_validation_run_id is not None:
            after_value["validation_run_id"] = str(review.latest_validation_run_id)
        return await self.repository.create_decision(
            review_id=review_id,
            finding_id=None,
            decision=payload.decision,
            reason=reason,
            decided_by_user_id=actor_id,
            request_id=request_id,
            before_value={"review_status": before_status},
            after_value=after_value,
        )

    async def _approval_gate_summary(self, review) -> ReviewGateSummary:
        run = (
            await self.repository.get_run(review.latest_validation_run_id)
            if review.latest_validation_run_id
            else None
        )
        missing = await self.repository.list_missing_items(
            review.review_id, open_only=True
        )
        findings = (
            await self.repository.list_findings(review.latest_validation_run_id)
            if run
            else []
        )
        decisions = {
            item.finding_id: item
            for item in await self.repository.list_decisions(review.review_id)
            if item.finding_id is not None
        }
        unresolved = [
            item
            for item in findings
            if item.status in {"OPEN", "REQUIRES_SUPPLEMENT", "EXPERT_REVIEW"}
        ]
        final_statuses = {"ACCEPTED", "REJECTED", "PARTIALLY_ACCEPTED"}
        invalid_values = [
            item
            for item in findings
            if item.status in final_statuses
            and not _decision_has_final_value(decisions.get(item.finding_id))
        ]
        return ReviewGateSummary(
            has_completed_run=bool(run and run.run_status == "COMPLETED"),
            open_missing_count=len(missing),
            unresolved_finding_count=len(unresolved),
            invalid_value_count=len(invalid_values),
        )

    async def list_decisions(self, review_id):
        await self.get(review_id)
        return await self.repository.list_decisions(review_id)

    async def rerun(self, review_id, actor_id):
        review = await self.repository.get(review_id, for_update=True)
        if review is None:
            raise ResourceNotFoundError("審查案件")
        previous = []
        if review.latest_validation_run_id:
            previous = await self.repository.list_finding_rule_links(
                review.review_id,
                review.latest_validation_run_id
            )
        duplicate_rule_ids = set()
        supersedes = {}
        for finding_id, validation_rule_id in previous:
            rule_id = str(validation_rule_id)
            if rule_id in supersedes:
                duplicate_rule_ids.add(rule_id)
            else:
                supersedes[rule_id] = finding_id
        for rule_id in duplicate_rule_ids:
            supersedes.pop(rule_id, None)
        run, summary = await self.create_run(
            review_id,
            actor_id,
            supersedes,
            locked_review=review,
        )
        return run, summary

    async def build_report(self, validation_run_id):
        run = await self.get_run(validation_run_id)
        review = await self.get(run.review_id)
        findings = await self.repository.list_findings(validation_run_id)
        risk = await self.get_risk_summary(validation_run_id)
        finding_ids = {item.finding_id for item in findings}
        decisions = [
            item
            for item in await self.repository.list_decisions(review.review_id)
            if item.finding_id in finding_ids
            or (
                item.finding_id is None
                and isinstance(item.after_value, dict)
                and item.after_value.get("validation_run_id")
                == str(validation_run_id)
            )
        ]
        report_context = run.input_snapshot.get("report_context")
        case_context = run.input_snapshot.get("case")
        if not isinstance(report_context, dict) or not isinstance(case_context, dict):
            raise AppError(
                "HISTORICAL_RUN_CONTEXT_UNAVAILABLE",
                "舊檢核批次缺少不可變的報表脈絡",
                409,
            )
        corrections = CorrectionRepository(self.repository.session)
        run_document = run.input_snapshot.get("document")
        run_document_id = (
            str(run_document.get("document_id"))
            if isinstance(run_document, dict) and run_document.get("document_id")
            else None
        )
        report_requests = []
        history = []
        for request in await corrections.list_requests(review.review_id):
            belongs_to_run = request.based_on_validation_run_id == validation_run_id
            if request.response_document_id is not None and run_document_id is not None:
                belongs_to_run = belongs_to_run or (
                    str(request.response_document_id) == run_document_id
                )
            if not belongs_to_run:
                continue
            items = await corrections.list_items(request.correction_request_id)
            report_requests.append(
                ReportCorrectionRequest(
                    correction_request_id=request.correction_request_id,
                    request_no=request.request_no,
                    status=request.status,
                    due_at=request.due_at,
                    message=request.message,
                    base_document_id=request.base_document_id,
                    base_document_version=request.base_document_version,
                    response_document_id=request.response_document_id,
                    response_document_version=request.response_document_version,
                    sent_at=request.sent_at,
                    resubmitted_at=request.resubmitted_at,
                    rechecked_at=request.rechecked_at,
                    items=[
                        ReportCorrectionItem(
                            finding_id=item.finding_id,
                            finding_code=item.finding_code,
                            severity=item.severity,
                            page_number=item.page_number,
                            reported_text=item.reported_text,
                            reported_value=item.reported_value,
                            legal_basis=item.legal_basis_snapshot,
                            source_evidence=item.source_evidence_snapshot,
                            issue_summary=item.issue_summary,
                            requested_correction=item.requested_correction,
                            recheck_outcome=item.recheck_outcome,
                            resulting_finding_id=item.resulting_finding_id,
                        )
                        for item in items
                    ],
                )
            )
            history.append(
                ReportHistoryEvent(
                    event_type="CORRECTION_CREATED",
                    occurred_at=request.created_at,
                    actor_id=request.created_by_user_id,
                    reason=request.message,
                )
            )
            if request.sent_at is not None:
                history.append(
                    ReportHistoryEvent(
                        event_type="CORRECTION_SENT",
                        occurred_at=request.sent_at,
                        actor_id=request.sent_by_user_id,
                        reason=request.message,
                    )
                )
            if request.resubmitted_at is not None:
                history.append(
                    ReportHistoryEvent(
                        event_type="CORRECTION_RESUBMITTED",
                        occurred_at=request.resubmitted_at,
                        actor_id=request.resubmitted_by_user_id,
                        reason=f"新版文件 v{request.response_document_version}",
                    )
                )
            if request.rechecked_at is not None:
                history.append(
                    ReportHistoryEvent(
                        event_type="CORRECTION_RECHECKED",
                        occurred_at=request.rechecked_at,
                        actor_id=request.rechecked_by_user_id,
                        reason=None,
                    )
                )
        thresholds = await corrections.urgency_thresholds()
        urgency = classify_urgency(review.due_at, datetime.now(UTC), thresholds)
        data = ReviewReportInput(
            case=ReportCase(**case_context),
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
            review_status=report_context["review_status"],
            missing_item_count=report_context["missing_item_count"],
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
            urgency=ReportUrgency(
                level=urgency.level,
                remaining_days=urgency.remaining_days,
                due_at=review.due_at,
            ),
            correction_requests=report_requests,
            history=sorted(history, key=lambda item: item.occurred_at),
        )
        return build_review_report(data)
