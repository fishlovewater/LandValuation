from dataclasses import dataclass
from typing import Any, Literal

from app.core.exceptions import AppError


FindingStatus = Literal[
    "ACCEPTED",
    "PARTIALLY_ACCEPTED",
    "REJECTED",
    "REQUIRES_SUPPLEMENT",
    "EXPERT_REVIEW",
]


@dataclass(frozen=True)
class FindingDecisionCommand:
    decision: FindingStatus
    reason: str
    after_value: Any = None


@dataclass(frozen=True)
class FindingValueContext:
    field_path: str | None
    reported_value: Any
    system_value: Any


@dataclass(frozen=True)
class CaseDecisionCommand:
    decision: Literal[
        "RETURNED_FOR_REVISION",
        "SUPPLEMENT_REQUIRED",
        "EXPERT_REVIEW",
        "APPROVED",
        "REVIEW_COMPLETED",
    ]
    reason: str
    has_override_permission: bool = False
    override_reason: str | None = None


@dataclass(frozen=True)
class ReviewGateSummary:
    unresolved_high_count: int


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        if "value" in value:
            return _has_meaningful_value(value["value"])
        return any(_has_meaningful_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_value(item) for item in value)
    return True


def validate_finding_decision(command: FindingDecisionCommand) -> FindingStatus:
    if not command.reason.strip():
        raise AppError(
            "REVIEW_DECISION_INVALID", "人工決策必須填寫理由", 409
        )
    if (
        command.decision == "PARTIALLY_ACCEPTED"
        and not _has_meaningful_value(command.after_value)
    ):
        raise AppError(
            "REVIEW_DECISION_INVALID", "部分接受必須提供調整後內容", 409
        )
    return command.decision


def build_finding_after_value(
    command: FindingDecisionCommand,
    context: FindingValueContext,
) -> dict[str, Any] | None:
    validate_finding_decision(command)
    if command.decision == "REQUIRES_SUPPLEMENT":
        return None
    if command.decision == "REJECTED":
        source, value = "REPORTED", context.reported_value
    elif command.decision == "ACCEPTED":
        source, value = "SYSTEM", context.system_value
    elif command.decision == "PARTIALLY_ACCEPTED":
        source = "REVIEWER"
        value = command.after_value.get("value") if command.after_value else None
    else:
        return command.after_value
    if not _has_meaningful_value(value):
        raise AppError(
            "REVIEW_DECISION_INVALID",
            "所選內容沒有可用的正式採用值",
            409,
        )
    return {
        "selection_source": source,
        "field_path": context.field_path,
        "value": str(value).strip(),
    }


def validate_case_decision(
    command: CaseDecisionCommand, summary: ReviewGateSummary
) -> str:
    if not command.reason.strip():
        raise AppError(
            "REVIEW_DECISION_INVALID", "案件決策必須填寫理由", 409
        )
    if command.decision == "APPROVED" and summary.unresolved_high_count > 0:
        if not command.has_override_permission or not (
            command.override_reason and command.override_reason.strip()
        ):
            raise AppError(
                "REVIEW_DECISION_INVALID",
                "仍有未解決高風險疑點，不得直接核准",
                409,
                {"unresolved_high_count": summary.unresolved_high_count},
            )
    return command.decision
