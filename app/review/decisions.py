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
    has_completed_run: bool
    open_missing_count: int
    unresolved_finding_count: int
    invalid_value_count: int

    def blockers(self) -> list[str]:
        items = []
        if not self.has_completed_run:
            items.append("最新一次智慧審查尚未完成")
        if self.open_missing_count:
            items.append(f"仍有 {self.open_missing_count} 項缺件")
        if self.unresolved_finding_count:
            items.append(f"仍有 {self.unresolved_finding_count} 項疑點未完成")
        if self.invalid_value_count:
            items.append(f"仍有 {self.invalid_value_count} 項缺少正式採用內容")
        return items


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
    blockers = summary.blockers() if command.decision == "APPROVED" else []
    if blockers:
        raise AppError(
            "REVIEW_DECISION_INVALID",
            "案件仍有未完成審查項目，不得核定",
            409,
            {"blockers": blockers},
        )
    return command.decision
