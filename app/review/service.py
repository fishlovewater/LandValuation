from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import re
from uuid import UUID

from app.core.exceptions import AppError
from app.core.exceptions import ResourceNotFoundError
from app.review.repository import ReviewRepository
from app.review.demo_policy import allow_missing_materials, advisory_completeness, ADVISORY_ITEM_CODES
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
    ReportInputDocument,
    ReportInputProvenance,
    ReportRiskSummary,
    ReportRun,
    ReportUrgency,
    ReviewReportInput,
    build_review_report,
)
from app.review.urgency import classify_urgency
from app.review.schemas import FindingRead
from app.review.status_policy import (
    REVIEW_MUTABLE_STATUSES,
    REVIEW_SUPPLEMENT_REQUEST_STATUSES,
    REVIEW_TRIAGE_STATUSES,
    ensure_review_status_allowed,
)
from app.review.rule_selection import (
    RuleCandidate,
    rule_versions_are_handoff_compatible,
    select_effective_rule,
)
from app.review.trusted_inputs import (
    TrustedField,
    required_field_problems,
    trusted_fields_by_code,
    TrustedRunContext,
    prepare_trusted_rules,
    validate_rule_contracts,
)
from app.valuation.submissions.snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    normalize_snapshot_value,
    snapshot_fingerprint,
)


_MISSING_FINGERPRINT = object()
_EXECUTION_CONTEXT_SCHEMA_VERSION = "valuation-review-execution-v1"
_EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION = "excel-template-handoff-v2"
_LEGACY_EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION = "excel-template-handoff-v1"
_EXTERNAL_REVIEW_INPUT_SCHEMA_VERSION = "external-review-input-v1"


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
        del payload, actor_id
        raise AppError(
            "LEGACY_REVIEW_CREATE_DISABLED",
            "平台案件只能由正式送審流程建立審查；外部案件請使用外部案件建立功能",
            409,
        )

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
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_MUTABLE_STATUSES,
            action="更新審查案件",
        )
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
        review = await self.get(review_id)
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_MUTABLE_STATUSES,
            action="變更審查人員",
        )
        try:
            return await self.repository.assign(review_id, reviewer_id)
        except LookupError as exc:
            raise ResourceNotFoundError("審查案件") from exc

    async def set_priority(self, review_id, priority, reason, actor_id):
        review = await self.get(review_id)
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_MUTABLE_STATUSES,
            action="調整案件優先順序",
        )
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

        submitted_inputs = None
        if review.latest_submission_id is not None:
            submitted_inputs = await self._load_submitted_snapshot(review)
            result = CompletenessResult(
                ready=True,
                items=(),
                blocked_rule_codes=frozenset(),
            )
        else:
            snapshot = await self.repository.load_case_snapshot(review.case_id)
            result = evaluate_completeness(snapshot)
        demo_advisory = await self._demo_advisory(review)
        if demo_advisory:
            result = advisory_completeness(result)
        if result.ready and not demo_advisory:
            trusted_items = await self._trusted_completeness_missing_items(
                review, submitted_inputs
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
        demo_prefix = "Demo：此缺件不阻擋智慧審查；相關檢核可能未執行。"
        for item in items:
            if hasattr(item, "reason"):
                reason = (item.reason or "").removeprefix(demo_prefix)
                advisory_item = item.item_code in {"DOC_LAND_REGISTER", "DOC_CADASTRAL_MAP", "FIELD_PARCEL_AREA"}
                item.reason = (demo_prefix if demo_advisory and advisory_item else "") + reason
        review.missing_item_count = len(items)
        review.review_status = ensure_transition(
            "PREPROCESSING",
            "READY_FOR_REVIEW" if result.ready else "PENDING_MATERIALS",
        )
        await self.repository.session.flush()
        return result, review, items

    async def _demo_advisory(self, review):
        if not allow_missing_materials("EXTERNAL_REVIEW", submitted=getattr(review, "latest_submission_id", None) is not None):
            return False
        case = await self.repository.get_case(review.case_id)
        return allow_missing_materials(getattr(case, "case_type", None))

    @staticmethod
    def _trusted_field(row: dict) -> TrustedField:
        return TrustedField(
            extracted_field_id=str(row["extracted_field_id"]),
            document_id=(
                str(row["document_id"])
                if row.get("document_id") is not None
                else None
            ),
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
            document_id=str(item["document_id"]),
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
        cls,
        snapshot: dict | None,
        input_fingerprint: str | None | object = _MISSING_FINGERPRINT,
    ) -> tuple[dict, tuple[TrustedField, ...]]:
        """Validate and extract the immutable document/field input boundary."""
        invalid = cls._invalid_submission_snapshot
        if not isinstance(snapshot, dict):
            raise invalid()

        top_level_keys = {
            "schema_version",
            "case_version",
            "submitted_by_user_id",
            "request_id",
            "applied_fields",
            "calculations",
            "documents",
            "validation",
        }
        if not top_level_keys.issubset(snapshot) or set(snapshot) - (
            top_level_keys | {"execution_context"}
        ):
            raise invalid()
        if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise invalid()

        case_version = snapshot.get("case_version")
        if isinstance(case_version, bool) or not isinstance(case_version, int):
            raise invalid()
        if case_version < 1:
            raise invalid()

        def valid_uuid(value) -> bool:
            if not isinstance(value, str) or not value.strip():
                return False
            try:
                UUID(value)
            except (AttributeError, TypeError, ValueError):
                return False
            return True

        def valid_timestamp(value) -> bool:
            if not isinstance(value, str) or not value.strip():
                return False
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return False
            return parsed.tzinfo is not None and parsed.utcoffset() is not None

        def valid_json_value(value) -> bool:
            if isinstance(value, float):
                return False
            if isinstance(value, dict):
                return all(
                    isinstance(key, str) and valid_json_value(item)
                    for key, item in value.items()
                )
            if isinstance(value, list):
                return all(valid_json_value(item) for item in value)
            return value is None or isinstance(value, (str, int, bool, Decimal))

        def valid_confidence(value) -> bool:
            if isinstance(value, bool) or isinstance(value, float):
                return False
            if not isinstance(value, (str, int, Decimal)):
                return False
            try:
                parsed = Decimal(str(value))
            except (InvalidOperation, ValueError):
                return False
            return parsed.is_finite() and Decimal("0") <= parsed <= Decimal("1")

        if not valid_uuid(snapshot.get("submitted_by_user_id")):
            raise invalid()
        if not valid_uuid(snapshot.get("request_id")):
            raise invalid()
        if not isinstance(snapshot.get("calculations"), dict):
            raise invalid()
        if not isinstance(snapshot.get("validation"), dict):
            raise invalid()
        if not valid_json_value(snapshot["calculations"]):
            raise invalid()
        if not valid_json_value(snapshot["validation"]):
            raise invalid()
        execution_context = snapshot.get("execution_context")
        execution_schema = None
        if execution_context is not None:
            if not isinstance(execution_context, dict) or not valid_json_value(
                execution_context
            ):
                raise invalid()
            execution_schema = execution_context.get("schema_version")
            if execution_schema not in {
                _EXECUTION_CONTEXT_SCHEMA_VERSION,
                _EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION,
                _LEGACY_EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION,
            }:
                raise invalid()

        if input_fingerprint is not _MISSING_FINGERPRINT:
            if not isinstance(input_fingerprint, str) or not re.fullmatch(
                r"[0-9a-f]{64}", input_fingerprint
            ):
                raise invalid()
            try:
                calculated_fingerprint = snapshot_fingerprint(snapshot)
            except (TypeError, ValueError, OverflowError):
                raise invalid()
            if calculated_fingerprint != input_fingerprint:
                raise invalid()

        applied_fields = snapshot.get("applied_fields")
        documents = snapshot.get("documents")
        excel_handoff = execution_schema in {
            _EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION,
            _LEGACY_EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION,
        }
        if not isinstance(applied_fields, list) or (
            not applied_fields and not excel_handoff
        ):
            raise invalid()
        if not isinstance(documents, list) or not documents:
            raise invalid()

        document_keys = {
            "document_id",
            "document_type",
            "original_filename",
            "mime_type",
            "version_no",
            "document_group_id",
            "checksum_sha256",
            "file_size_bytes",
            "uploaded_at",
            "is_active",
        }
        documents_by_id = {}
        for document in documents:
            if not isinstance(document, dict):
                raise invalid()
            if set(document) != document_keys:
                raise invalid()
            document_id = document.get("document_id")
            if not valid_uuid(document_id):
                raise invalid()
            if not isinstance(document.get("document_type"), str) or not document[
                "document_type"
            ].strip():
                raise invalid()
            if not isinstance(document.get("original_filename"), str) or not document[
                "original_filename"
            ].strip():
                raise invalid()
            if not isinstance(document.get("mime_type"), str) or not document[
                "mime_type"
            ].strip():
                raise invalid()
            version_no = document.get("version_no")
            if isinstance(version_no, bool) or not isinstance(version_no, int):
                raise invalid()
            if version_no < 1:
                raise invalid()
            if not valid_uuid(document.get("document_group_id")):
                raise invalid()
            if not isinstance(document.get("checksum_sha256"), str) or not re.fullmatch(
                r"[0-9a-f]{64}", document["checksum_sha256"]
            ):
                raise invalid()
            file_size_bytes = document.get("file_size_bytes")
            if (
                isinstance(file_size_bytes, bool)
                or not isinstance(file_size_bytes, int)
                or file_size_bytes < 0
            ):
                raise invalid()
            if not valid_timestamp(document.get("uploaded_at")):
                raise invalid()
            if not isinstance(document.get("is_active"), bool):
                raise invalid()
            if document_id in documents_by_id:
                raise invalid()
            documents_by_id[document_id] = document

        trusted_fields = []
        field_keys = {
            "extracted_field_id",
            "document_id",
            "form_code",
            "field_name",
            "confirmed_value",
            "source_page",
            "source_text",
            "confidence",
            "field_status",
            "confirmed_by_user_id",
            "confirmed_at",
        }
        field_ids = set()
        for item in applied_fields:
            if not isinstance(item, dict):
                raise invalid()
            if set(item) != field_keys:
                raise invalid()
            extracted_field_id = item.get("extracted_field_id")
            document_id = item.get("document_id")
            if (
                not valid_uuid(extracted_field_id)
                or extracted_field_id in field_ids
                or not valid_uuid(document_id)
                or document_id not in documents_by_id
                or not isinstance(item["form_code"], str)
                or not item["form_code"].strip()
                or not isinstance(item["field_name"], str)
                or not item["field_name"].strip()
                or item["confirmed_value"] is None
                or not valid_json_value(item["confirmed_value"])
                or (
                    item["source_page"] is not None
                    and (
                        isinstance(item["source_page"], bool)
                        or not isinstance(item["source_page"], int)
                        or item["source_page"] < 1
                    )
                )
                or (
                    item["source_text"] is not None
                    and not isinstance(item["source_text"], str)
                )
                or not valid_confidence(item["confidence"])
                or item["field_status"] != "APPLIED"
                or not valid_uuid(item["confirmed_by_user_id"])
                or not valid_timestamp(item["confirmed_at"])
            ):
                raise invalid()
            field_ids.add(extracted_field_id)
            trusted_fields.append(cls._trusted_field_from_submission(item))

        if applied_fields:
            primary_document_id = applied_fields[0]["document_id"]
        elif execution_schema == _EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION:
            report_context = execution_context.get("report")
            if not isinstance(report_context, dict):
                raise invalid()
            primary_document_id = report_context.get("primary_document_id")
        else:
            source_document_ids = execution_context.get("source_document_ids")
            if not isinstance(source_document_ids, list) or not source_document_ids:
                raise invalid()
            primary_document_id = source_document_ids[0]
        if primary_document_id not in documents_by_id:
            raise invalid()
        document = dict(documents_by_id[primary_document_id])
        return document, tuple(trusted_fields)

    @classmethod
    def _snapshot_trusted_run_context(
        cls,
        review,
        snapshot: dict,
        official_fields: tuple[TrustedField, ...],
    ) -> TrustedRunContext:
        """Adapt a submitted Snapshot into the Review execution boundary.

        A Review with ``latest_submission_id`` is deliberately isolated from
        the mutable Valuation tables.  The handoff builder stores all values
        needed by deterministic Review execution under ``execution_context``;
        this adapter validates that shape and then prepares rules from those
        copied values only.
        """
        invalid = cls._invalid_submission_snapshot
        context = snapshot.get("execution_context")
        if not isinstance(context, dict):
            raise invalid()
        context_schema = context.get("schema_version")
        if context_schema == _LEGACY_EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION:
            raise AppError(
                "SUBMISSION_EXECUTION_CONTEXT_INCOMPLETE",
                "這筆送審資料使用舊版 Excel 交接格式，缺少可執行的凍結審查上下文，請重新送審。",
                409,
            )
        excel_handoff = context_schema == _EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION
        context_keys = {
            "schema_version",
            "case",
            "source_validation_run",
            "report",
            "rule_selection",
        }
        if set(context) != context_keys or context_schema not in {
            _EXECUTION_CONTEXT_SCHEMA_VERSION,
            _EXCEL_EXECUTION_CONTEXT_SCHEMA_VERSION,
        }:
            raise invalid()

        def require_dict(parent: dict, key: str, keys: set[str]) -> dict:
            value = parent.get(key)
            if not isinstance(value, dict) or set(value) != keys:
                raise invalid()
            return value

        def require_uuid(value) -> str:
            if not isinstance(value, str) or not value.strip():
                raise invalid()
            try:
                return str(UUID(value))
            except (AttributeError, TypeError, ValueError):
                raise invalid()

        def require_text(value, *, allow_empty: bool = False) -> str:
            if not isinstance(value, str) or (not allow_empty and not value.strip()):
                raise invalid()
            return value

        def require_int(value, *, minimum: int = 0) -> int:
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise invalid()
            return value

        def require_date(value, *, allow_none: bool = True):
            if value is None and allow_none:
                return None
            if not isinstance(value, str) or not value.strip():
                raise invalid()
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                raise invalid()
            return value

        def require_timestamp(value, *, allow_none: bool = True):
            if value is None and allow_none:
                return None
            if not isinstance(value, str) or not value.strip():
                raise invalid()
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                raise invalid()
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise invalid()
            return value

        case_context = require_dict(
            context,
            "case",
            {
                "case_id",
                "case_no",
                "case_title",
                "case_type",
                "district_code",
                "valuation_base_date",
                "form_codes",
            },
        )
        if require_uuid(case_context["case_id"]) != str(review.case_id):
            raise invalid()
        for key in ("case_no", "case_title", "case_type", "district_code"):
            require_text(case_context[key])
        require_date(case_context["valuation_base_date"], allow_none=False)
        form_codes = case_context["form_codes"]
        if (
            not isinstance(form_codes, list)
            or not form_codes
            or any(not isinstance(code, str) or not code.strip() for code in form_codes)
            or len(form_codes) != len(set(form_codes))
        ):
            raise invalid()

        source_run = require_dict(
            context,
            "source_validation_run",
            {
                "validation_run_id",
                "case_id",
                "form_instance_id",
                "run_status",
                "passed_count",
                "warning_count",
                "failed_count",
                "rule_version_id",
                "input_snapshot",
                "ruleset_snapshot",
                "completed_at",
            },
        )
        source_run_id = require_uuid(source_run["validation_run_id"])
        if require_uuid(source_run["case_id"]) != str(review.case_id):
            raise invalid()
        source_form_id = require_uuid(source_run["form_instance_id"])
        if source_run["run_status"] != "COMPLETED":
            raise invalid()
        for key in ("passed_count", "warning_count", "failed_count"):
            require_int(source_run[key])
        if source_run["failed_count"] != 0 and not excel_handoff:
            raise invalid()
        if not isinstance(source_run["input_snapshot"], dict) or not source_run["input_snapshot"]:
            raise invalid()
        if not isinstance(source_run["ruleset_snapshot"], dict) or not source_run["ruleset_snapshot"]:
            raise invalid()
        require_timestamp(source_run["completed_at"], allow_none=False)
        source_rule_version_id = require_uuid(source_run["rule_version_id"])

        report = context.get("report")
        if not isinstance(report, dict):
            raise invalid()
        form_keys = {
            "form_instance_id",
            "case_id",
            "form_code",
            "version_no",
            "form_status",
            "output_document_id",
            "form_content",
        }

        def validate_form_snapshot(
            form: dict,
            *,
            require_final: bool,
            require_output: bool,
        ) -> dict:
            if not isinstance(form, dict) or set(form) != form_keys:
                raise invalid()
            form_id = require_uuid(form["form_instance_id"])
            if require_uuid(form["case_id"]) != str(review.case_id):
                raise invalid()
            require_text(form["form_code"])
            require_int(form["version_no"], minimum=1)
            require_text(form["form_status"])
            if require_final and form["form_status"] != "FINAL":
                raise invalid()
            output_document_id = form["output_document_id"]
            if require_output:
                output_document_id = require_uuid(output_document_id)
            elif output_document_id is not None:
                output_document_id = require_uuid(output_document_id)
            if not isinstance(form["form_content"], dict):
                raise invalid()
            return {
                **form,
                "form_instance_id": form_id,
                "case_id": str(review.case_id),
                "output_document_id": output_document_id,
            }

        documents = {
            str(item["document_id"]): dict(item) for item in snapshot["documents"]
        }
        immutable_document_keys = (
            "document_type",
            "original_filename",
            "mime_type",
            "version_no",
            "document_group_id",
            "checksum_sha256",
            "file_size_bytes",
            "uploaded_at",
            "is_active",
        )
        document_keys = {
            "document_id",
            "case_id",
            "document_type",
            "original_filename",
            "mime_type",
            "version_no",
            "document_group_id",
            "checksum_sha256",
            "file_size_bytes",
            "uploaded_at",
            "is_active",
        }

        def validate_document_snapshot(document: dict) -> tuple[str, dict]:
            if not isinstance(document, dict) or set(document) != document_keys:
                raise invalid()
            document_id = require_uuid(document["document_id"])
            if require_uuid(document["case_id"]) != str(review.case_id):
                raise invalid()
            for key in ("document_type", "original_filename", "mime_type"):
                require_text(document[key])
            require_int(document["version_no"], minimum=1)
            require_uuid(document["document_group_id"])
            if not isinstance(document["checksum_sha256"], str) or not re.fullmatch(
                r"[0-9a-f]{64}", document["checksum_sha256"]
            ):
                raise invalid()
            require_int(document["file_size_bytes"])
            require_timestamp(document["uploaded_at"], allow_none=False)
            if not isinstance(document["is_active"], bool) or not document["is_active"]:
                raise invalid()
            snapshot_document = documents.get(document_id)
            if snapshot_document is None or any(
                snapshot_document[key] != document[key]
                for key in immutable_document_keys
            ):
                raise invalid()
            return document_id, snapshot_document

        if excel_handoff:
            if set(report) != {
                "authoritative_form",
                "primary_document_id",
                "template_documents",
            }:
                raise invalid()
            authoritative_form = validate_form_snapshot(
                report["authoritative_form"],
                require_final=False,
                require_output=False,
            )
            report_form = authoritative_form
            if source_form_id != report_form["form_instance_id"]:
                raise invalid()
            primary_document_id = require_uuid(report["primary_document_id"])
            template_documents = report["template_documents"]
            if not isinstance(template_documents, list) or not template_documents:
                raise invalid()
            template_ids = set()
            for template_document in template_documents:
                template_id, _snapshot_template = validate_document_snapshot(
                    template_document
                )
                if (
                    template_document["document_type"] != "generated-template-xlsx"
                    or template_id in template_ids
                ):
                    raise invalid()
                template_ids.add(template_id)
            if primary_document_id not in template_ids:
                raise invalid()
            snapshot_document = documents[primary_document_id]
        else:
            if set(report) != {"form", "authoritative_form", "document"}:
                raise invalid()
            report_form = validate_form_snapshot(
                report["form"], require_final=True, require_output=True
            )
            authoritative_form = validate_form_snapshot(
                report["authoritative_form"], require_final=True, require_output=True
            )
            if (
                report_form["form_instance_id"]
                != authoritative_form["form_instance_id"]
                or report_form["version_no"] != authoritative_form["version_no"]
                or report_form["form_code"] != authoritative_form["form_code"]
                or report_form["output_document_id"]
                != authoritative_form["output_document_id"]
                or source_form_id != report_form["form_instance_id"]
            ):
                raise invalid()
            report_document_id, snapshot_document = validate_document_snapshot(
                report["document"]
            )
            if report_form["output_document_id"] != report_document_id:
                raise invalid()

        for item in official_fields:
            if item.document_id is None or str(item.document_id) not in documents:
                raise invalid()
            if item.form_code not in form_codes:
                raise invalid()

        rule_selection = context.get("rule_selection")
        legacy_selection_keys = {"rule_version", "rule_source", "validation_rules"}
        paired_selection_keys = legacy_selection_keys | {"source_rule_version"}
        if (
            not isinstance(rule_selection, dict)
            or set(rule_selection) not in (legacy_selection_keys, paired_selection_keys)
        ):
            raise invalid()

        rule_version_keys = {
            "rule_version_id",
            "rule_set_code",
            "version_no",
            "version_name",
            "status",
            "effective_from",
            "effective_to",
            "applicable_case_type",
            "applicable_district_code",
            "selection_priority",
            "source_document_id",
        }
        rule_version_keys_with_summary = rule_version_keys | {"import_summary"}

        def validate_rule_version_snapshot(key: str) -> dict:
            value = rule_selection.get(key)
            if (
                not isinstance(value, dict)
                or set(value) not in (rule_version_keys, rule_version_keys_with_summary)
            ):
                raise invalid()
            require_uuid(value["rule_version_id"])
            if value["status"] != "PUBLISHED":
                raise invalid()
            require_text(value["rule_set_code"])
            require_int(value["version_no"], minimum=1)
            require_text(value["version_name"])
            require_date(value["effective_from"])
            require_date(value["effective_to"])
            if (
                value["applicable_case_type"] != case_context["case_type"]
                or value["applicable_district_code"]
                != case_context["district_code"]
            ):
                raise invalid()
            require_int(value["selection_priority"])
            require_uuid(value["source_document_id"])
            if "import_summary" in value and not isinstance(value["import_summary"], dict):
                raise invalid()
            return dict(value)

        rule_version = validate_rule_version_snapshot("rule_version")
        rule_version_id = require_uuid(rule_version["rule_version_id"])
        if "source_rule_version" in rule_selection:
            source_rule_version = validate_rule_version_snapshot("source_rule_version")
            if require_uuid(source_rule_version["rule_version_id"]) != source_rule_version_id:
                raise invalid()
            if not rule_versions_are_handoff_compatible(source_rule_version, rule_version):
                raise invalid()
        elif rule_version_id != source_rule_version_id:
            # Legacy v1 snapshots carried one rule version for both validation
            # and Review execution. Keep accepting those immutable snapshots,
            # but fail closed if the source run points anywhere else.
            raise invalid()

        source_document_id = require_uuid(rule_version["source_document_id"])

        rule_source_keys = {
            "document_id",
            "checksum_sha256",
            "version_no",
            "effective_from",
            "effective_to",
        }
        rule_source = require_dict(rule_selection, "rule_source", rule_source_keys)
        if require_uuid(rule_source["document_id"]) != source_document_id:
            raise invalid()
        if not isinstance(rule_source["checksum_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", rule_source["checksum_sha256"]
        ):
            raise invalid()
        require_int(rule_source["version_no"], minimum=1)
        require_date(rule_source["effective_from"])
        require_date(rule_source["effective_to"])

        validation_rules = rule_selection["validation_rules"]
        # A Valuation formal-validation snapshot is authoritative at handoff.
        # A fixed rule pack can therefore legitimately omit the legacy
        # F01-only Review comparison rules and produce a zero-extra-check run.
        if not isinstance(validation_rules, list):
            raise invalid()
        rule_keys = {
            "validation_rule_id",
            "rule_version_id",
            "rule_code",
            "rule_name",
            "target_form_code",
            "target_table",
            "target_field_code",
            "severity",
            "rule_expression",
            "message_template",
            "is_active",
        }
        copied_rules = []
        for rule in validation_rules:
            if not isinstance(rule, dict) or set(rule) != rule_keys:
                raise invalid()
            copied_rule = dict(rule)
            if require_uuid(rule["validation_rule_id"]) is None:
                raise invalid()
            if require_uuid(rule["rule_version_id"]) != rule_version_id:
                raise invalid()
            for key in ("rule_code", "rule_name", "target_table", "target_field_code", "severity", "rule_expression", "message_template"):
                require_text(rule[key])
            if rule["target_form_code"] is not None:
                require_text(rule["target_form_code"])
            if not isinstance(rule["is_active"], bool) or not rule["is_active"]:
                raise invalid()
            copied_rules.append(copied_rule)

        validation = snapshot["validation"]
        if (
            not isinstance(validation, dict)
            or require_uuid(validation.get("validation_run_id")) != source_run_id
            or require_uuid(validation.get("form_instance_id")) != report_form["form_instance_id"]
            or require_uuid(validation.get("rule_version_id")) != source_rule_version_id
        ):
            raise invalid()

        fields = trusted_fields_by_code(official_fields)
        contracts = validate_rule_contracts(copied_rules)
        prepared_rules = prepare_trusted_rules(contracts, fields)
        case_projection = {
            key: case_context[key]
            for key in (
                "case_id",
                "case_no",
                "case_title",
                "valuation_base_date",
                "district_code",
            )
        }
        return TrustedRunContext(
            document=snapshot_document,
            fields=fields,
            official_fields=official_fields,
            rule_version=dict(rule_version),
            validation_rules=tuple(copied_rules),
            rule_source=dict(rule_source),
            prepared_rules=prepared_rules,
            documents=documents,
            case=case_projection,
        )

    async def _load_submitted_snapshot(self, review):
        submission = await self.repository.get_submission_snapshot_record(
            review.latest_submission_id,
            review_id=review.review_id,
            case_id=review.case_id,
        )
        if submission is None:
            raise self._invalid_submission_snapshot()
        snapshot = submission.get("input_snapshot")
        document, official_fields = self._snapshot_trusted_inputs(
            snapshot,
            input_fingerprint=submission.get("input_fingerprint"),
        )
        return snapshot, document, official_fields

    async def _trusted_completeness_missing_items(
        self, review, submitted_inputs=None
    ):
        if review.latest_submission_id is not None:
            if submitted_inputs is None:
                submitted_inputs = await self._load_submitted_snapshot(review)
            snapshot, _document, official_fields = submitted_inputs
            try:
                self._snapshot_trusted_run_context(
                    review, snapshot, official_fields
                )
            except AppError as error:
                if error.code == "SUBMISSION_SNAPSHOT_INVALID":
                    raise
                return (trusted_preflight_to_missing(error),)
            return ()

        document = await self.repository.get_latest_original_document(review.case_id)
        official_fields = tuple(
            self._trusted_field(row)
            for row in await self.repository.list_applied_confirmed_extracted_fields(
                review.case_id
            )
        )
        if document is None:
            return (trusted_context_missing_requirement(),)
        fields = trusted_fields_by_code(official_fields)
        case_context = await self.repository.get_case_rule_context(review.case_id)
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
        required_codes = {
            field_code
            for contract in contracts
            for field_code in contract.required_field_codes
        }
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
        review = await self.get(review_id)
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_SUPPLEMENT_REQUEST_STATUSES,
            action="要求補件",
        )
        if due_at <= datetime.now(due_at.tzinfo):
            raise AppError("INVALID_DUE_AT", "補件期限必須晚於目前時間", 422)
        return await self.repository.request_supplement(review_id, due_at)

    async def _resolve_trusted_run_context(self, review) -> TrustedRunContext:
        documents = {}
        if review.latest_submission_id is not None:
            snapshot, document, official_fields = await self._load_submitted_snapshot(
                review
            )
            return self._snapshot_trusted_run_context(
                review, snapshot, official_fields
            )

        document = await self.repository.get_latest_original_document(review.case_id)
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
        documents = {str(document["document_id"]): document}
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
        required_codes = {
            field_code
            for contract in contracts
            for field_code in contract.required_field_codes
        }
        problems = required_field_problems(required_codes, fields)
        if await self._demo_advisory(review):
            completeness = evaluate_completeness(
                await self.repository.load_case_snapshot(review.case_id)
            )
            contracts = tuple(
                contract for contract in contracts
                if not required_field_problems(contract.required_field_codes, fields)
                and contract.rule["rule_code"] not in completeness.blocked_rule_codes
            )
            problems = ()
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
            documents=documents,
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
    def _source_evidence_many(
        context: TrustedRunContext, fields: tuple[TrustedField, ...]
    ) -> "list[dict]":
        evidence: list[dict] = []
        for field in fields:
            evidence.extend(
                ReviewService._source_evidence(
                    ReviewService._field_document(context, field),
                    field,
                )
            )
        return evidence

    @staticmethod
    def _field_document(context: TrustedRunContext, field: TrustedField) -> dict:
        if field.document_id is not None:
            document = context.documents.get(str(field.document_id))
            if document is not None:
                return document
        return context.document

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
            "document_id": field.document_id,
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
            if prepared_rule.weight_sum_result is not None:
                result = prepared_rule.weight_sum_result
                reported_value = {
                    "comparison_weight": str(result.comparison_weight),
                    "income_weight": str(result.income_weight),
                    "weight_sum": str(result.total),
                }
            elif prepared_rule.reported_rate is not None:
                reported_value = str(prepared_rule.reported_rate)
            else:
                reported_value = prepared_rule.reported_grade
            source_fields = prepared_rule.source_fields or (field,)
            checks.append(
                {
                    "finding_code": ReviewService._finding_code(rule),
                    "validation_rule_id": str(rule["validation_rule_id"]),
                    "rule_code": rule["rule_code"],
                    **ReviewService._field_snapshot(field),
                    "reported_value": ReviewService._json_value(reported_value),
                    "source_fields": [
                        ReviewService._field_snapshot(item)
                        for item in source_fields
                    ],
                    "rule_result": ReviewService._json_value(
                        {
                            "weight_sum": prepared_rule.weight_sum_result.total,
                            "expected_total": prepared_rule.weight_sum_result.expected_total,
                            "tolerance": prepared_rule.weight_sum_result.tolerance,
                            "within_range": prepared_rule.weight_sum_result.within_range,
                            "matches_total": prepared_rule.weight_sum_result.matches_total,
                            "valid": prepared_rule.weight_sum_result.valid,
                        }
                        if prepared_rule.weight_sum_result is not None
                        else None
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
                        "field_status": ("APPLIED_OR_AUTO_APPLIED" if any(
                            field.field_status == "AUTO_APPLIED" for field in context.official_fields
                        ) else "APPLIED"),
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

    async def _freeze_external_review_input(
        self,
        review,
        actor_id: UUID,
        run_input_snapshot: dict,
    ):
        """Persist the external evidence package used by the next Review run."""
        if review.latest_submission_id is not None:
            return None
        case = await self.repository.get_case(review.case_id)
        if case is None or getattr(case, "case_type", None) != "EXTERNAL_REVIEW":
            return None

        documents = await self.repository.list_external_snapshot_documents(
            review.case_id
        )
        fields = await self.repository.list_external_snapshot_fields(review.case_id)
        snapshot = normalize_snapshot_value(
            {
                "schema_version": _EXTERNAL_REVIEW_INPUT_SCHEMA_VERSION,
                "review_id": review.review_id,
                "case_id": review.case_id,
                "documents": documents,
                "resolved_fields": fields,
                "run_input": run_input_snapshot,
            }
        )
        fingerprint = snapshot_fingerprint(snapshot)
        return await self.repository.create_external_input_snapshot(
            review_id=review.review_id,
            case_id=review.case_id,
            actor_id=actor_id,
            snapshot_schema_version=_EXTERNAL_REVIEW_INPUT_SCHEMA_VERSION,
            input_snapshot=snapshot,
            input_fingerprint=fingerprint,
        )

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
        case = context.case
        if case is None:
            # Legacy standalone Reviews have no Submission pointer and retain
            # the existing canonical live-data fallback.
            case = await self.repository.get_case_report_data(review.case_id)
        input_snapshot = self._input_snapshot(review, case, context)
        demo_advisory = await self._demo_advisory(review)
        if demo_advisory:
            executed = {str(item.rule["validation_rule_id"]) for item in context.prepared_rules}
            input_snapshot["demo_notice"] = "Demo：缺件不阻擋流程；資料不足的規則未執行，不代表通過。"
            input_snapshot["skipped_rule_codes"] = [
                rule["rule_code"] for rule in context.validation_rules
                if str(rule["validation_rule_id"]) not in executed
            ]
        external_snapshot = await self._freeze_external_review_input(
            review,
            actor_id,
            input_snapshot,
        )

        review.review_status = ensure_transition(review.review_status, "ANALYZING")
        run = await self.repository.create_run(
            review,
            actor_id,
            UUID(str(context.rule_version["rule_version_id"])),
            input_snapshot,
            submission_id=review.latest_submission_id,
            external_input_snapshot_id=(
                None
                if external_snapshot is None
                else external_snapshot.external_input_snapshot_id
            ),
        )
        findings = []
        for prepared_rule in context.prepared_rules:
            rule = prepared_rule.rule
            field = prepared_rule.field
            field_document = self._field_document(context, field)
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
                    document_id=field_document["document_id"],
                    document_version=field_document["version_no"],
                    page_number=field.page_number,
                    field_path=field.field_path,
                    source_evidence=self._source_evidence(field_document, field),
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
            elif rule["rule_code"] == "F03_WEIGHT_SUM":
                result = prepared_rule.weight_sum_result
                if result is None:
                    raise RuntimeError("F03 權重規則未完成 trusted preflight")
                if result.valid:
                    run.passed_count += 1
                    continue
                source_fields = prepared_rule.source_fields
                actual_value = {
                    "comparison_weight": str(result.comparison_weight),
                    "income_weight": str(result.income_weight),
                    "weight_sum": str(result.total),
                    "within_range": result.within_range,
                }
                expected_value = {
                    "weight_sum": str(result.expected_total),
                    "tolerance": str(result.tolerance),
                    "weight_range": ["0", "1"],
                }
                machine_finding = await self.repository.create_validation_finding(
                    validation_run_id=run.validation_run_id,
                    validation_rule_id=rule["validation_rule_id"],
                    field_code=rule["target_field_code"],
                    severity=rule["severity"],
                    actual_value=actual_value,
                    expected_value=expected_value,
                    finding_message="比較法與收益法權重必須介於 0 到 1 且合計為 1",
                )
                finding = await self.repository.create_finding(
                    review_id=review.review_id,
                    source_validation_finding_id=machine_finding.finding_id,
                    validation_run_id=run.validation_run_id,
                    finding_code=finding_code,
                    finding_type="F03_WEIGHT_SUM_MISMATCH",
                    severity=rule["severity"],
                    title="F03 權重範圍或加總不一致",
                    description=(
                        "比較法與收益法權重需各介於 0 到 1，且合計為 1；"
                        "系統僅檢查權重，不套用任何地價尾數進位規則。"
                    ),
                    status="OPEN",
                    document_id=field_document["document_id"],
                    document_version=field_document["version_no"],
                    page_number=field.page_number,
                    field_path=",".join(item.field_path for item in source_fields),
                    source_evidence=self._source_evidence_many(context, source_fields),
                    reported_text="；".join(
                        item.raw_text for item in source_fields if item.raw_text
                    ),
                    reported_value=(
                        f"comparison_weight={result.comparison_weight}; "
                        f"income_weight={result.income_weight}; total={result.total}"
                    ),
                    legal_basis=self._legal_basis(context, rule),
                    comparison_result={
                        **actual_value,
                        "expected_weight_sum": str(result.expected_total),
                        "tolerance": str(result.tolerance),
                        "matches_total": result.matches_total,
                        "valid": False,
                    },
                    recommended_action={"action": "VERIFY_F03_METHOD_WEIGHTS"},
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
                    document_id=field_document["document_id"],
                    document_version=field_document["version_no"],
                    page_number=field.page_number,
                    field_path=field.field_path,
                    source_evidence=self._source_evidence(field_document, field),
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
            summary=(
                (f"Demo：缺件不阻擋流程；{len(input_snapshot.get('skipped_rule_codes', []))} 項規則因資料不足未執行，不代表通過。"
                 if demo_advisory else "")
                + f"本次檢核產生 {len(findings)} 筆未解決疑點。"
            ),
            category_scores={"deterministic_findings": len(findings)},
            high_count=risk.high_count,
            medium_count=risk.medium_count,
            low_count=risk.low_count,
            missing_item_count=review.missing_item_count,
            risk_reasons=sorted({item.finding_type for item in findings}) + (
                [input_snapshot["demo_notice"], "未執行規則：" + ", ".join(input_snapshot["skipped_rule_codes"])]
                if demo_advisory else []
            ),
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
        if await self._demo_advisory(review):
            missing = [item for item in missing if item.item_code not in ADVISORY_ITEM_CODES]
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
        input_provenance = await self._report_input_provenance(run, review)
        corrections = CorrectionRepository(self.repository.session)
        run_document = run.input_snapshot.get("document")
        run_document_id = (
            str(run_document.get("document_id"))
            if isinstance(run_document, dict) and run_document.get("document_id")
            else None
        )
        report_requests = []
        history = []
        if input_provenance.frozen_at is not None:
            source_label = {
                "PLATFORM": "平台送審",
                "EXTERNAL": "外部審查輸入",
                "LEGACY": "舊版檢核輸入",
            }[input_provenance.source]
            version_label = (
                f" v{input_provenance.version_no}"
                if input_provenance.version_no is not None
                else ""
            )
            history.append(
                ReportHistoryEvent(
                    event_type="REVIEW_INPUT_FROZEN",
                    occurred_at=input_provenance.frozen_at,
                    actor_id=None,
                    reason=f"{source_label}{version_label}",
                )
            )
        if run.completed_at is not None:
            history.append(
                ReportHistoryEvent(
                    event_type="VALIDATION_RUN_COMPLETED",
                    occurred_at=run.completed_at,
                    actor_id=run.triggered_by_user_id,
                    reason=f"檢核批次 #{run.run_no}",
                )
            )
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
        if (run.input_snapshot or {}).get("demo_notice"):
            case_context = {**case_context, "case_title": "【Demo 展示，缺件不代表通過】" + case_context["case_title"]}
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
            input_provenance=input_provenance,
        )
        return build_review_report(data)

    async def _report_input_provenance(self, run, review) -> ReportInputProvenance:
        """Project the immutable input pointer for one historical Review run."""

        if run.submission_id is not None:
            row = await self.repository.get_submission_provenance_by_id(
                run.submission_id,
                review_id=review.review_id,
                case_id=review.case_id,
            )
            if row is None:
                raise AppError(
                    "HISTORICAL_RUN_CONTEXT_UNAVAILABLE",
                    "檢核批次找不到對應的平台送審版本",
                    409,
                )
            documents = self._report_input_documents(
                row.get("input_snapshot"),
                missing_message="平台送審版本缺少文件版本資訊",
                incomplete_message="平台送審版本的文件資訊不完整",
            )
            source_report_document_id = row.get("source_report_document_id")
            if source_report_document_id is not None and not any(
                document.document_id == source_report_document_id
                for document in documents
            ):
                raise AppError(
                    "HISTORICAL_RUN_CONTEXT_UNAVAILABLE",
                    "平台送審版本未包含本次送審的完整估價報告",
                    409,
                )
            return ReportInputProvenance(
                source="PLATFORM",
                version_no=row["submission_no"],
                frozen_at=row["submitted_at"],
                fingerprint=row["input_fingerprint"],
                schema_version=SNAPSHOT_SCHEMA_VERSION,
                submission_id=row["submission_id"],
                documents=documents,
            )

        if run.external_input_snapshot_id is not None:
            row = await self.repository.get_external_input_snapshot_provenance_by_id(
                run.external_input_snapshot_id,
                review_id=review.review_id,
                case_id=review.case_id,
            )
            if row is None:
                raise AppError(
                    "HISTORICAL_RUN_CONTEXT_UNAVAILABLE",
                    "檢核批次找不到對應的外部審查輸入版本",
                    409,
                )
            documents = self._report_input_documents(
                row.get("input_snapshot"),
                missing_message="外部審查輸入版本缺少文件版本資訊",
                incomplete_message="外部審查輸入版本的文件資訊不完整",
            )
            return ReportInputProvenance(
                source="EXTERNAL",
                version_no=row["snapshot_no"],
                frozen_at=row["created_at"],
                fingerprint=row["input_fingerprint"],
                schema_version=row["snapshot_schema_version"],
                external_input_snapshot_id=row["external_input_snapshot_id"],
                documents=documents,
            )

        # Backward compatibility for Review runs created before immutable
        # Submission/External Snapshot pointers existed. Their run snapshot is
        # still exposed as legacy provenance instead of being mistaken for a
        # modern platform or external snapshot.
        document = run.input_snapshot.get("document")
        documents = []
        if isinstance(document, dict) and all(
            document.get(key) is not None
            for key in ("document_id", "version_no", "checksum_sha256")
        ):
            documents.append(
                ReportInputDocument(
                    document_id=document["document_id"],
                    document_group_id=document.get("document_group_id"),
                    document_type="original",
                    version_no=document["version_no"],
                    checksum_sha256=document["checksum_sha256"],
                )
            )
        return ReportInputProvenance(
            source="LEGACY",
            version_no=run.run_no,
            frozen_at=run.started_at,
            documents=documents,
        )

    @staticmethod
    def _report_input_documents(
        snapshot,
        *,
        missing_message: str,
        incomplete_message: str,
    ) -> "list[ReportInputDocument]":
        """Project only immutable, user-safe document provenance from a snapshot."""

        raw_documents = snapshot.get("documents") if isinstance(snapshot, dict) else None
        if not isinstance(raw_documents, list) or not raw_documents:
            raise AppError(
                "HISTORICAL_RUN_CONTEXT_UNAVAILABLE",
                missing_message,
                409,
            )
        documents: list[ReportInputDocument] = []
        try:
            for document in raw_documents:
                if not isinstance(document, dict):
                    raise ValueError
                documents.append(
                    ReportInputDocument(
                        document_id=document["document_id"],
                        document_group_id=document.get("document_group_id"),
                        document_type=document["document_type"],
                        version_no=document["version_no"],
                        checksum_sha256=document["checksum_sha256"],
                        original_filename=document.get("original_filename"),
                    )
                )
        except (KeyError, TypeError, ValueError):
            raise AppError(
                "HISTORICAL_RUN_CONTEXT_UNAVAILABLE",
                incomplete_message,
                409,
            )
        return documents
