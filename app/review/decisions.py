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
class CaseDecisionCommand:
    decision: Literal[
        "RETURNED_FOR_REVISION",
        "SUPPLEMENT_REQUIRED",
        "EXPERT_REVIEW",
        "APPROVED",
    ]
    reason: str
    has_override_permission: bool = False
    override_reason: str | None = None


@dataclass(frozen=True)
class ReviewGateSummary:
    unresolved_high_count: int


def validate_finding_decision(command: FindingDecisionCommand) -> FindingStatus:
    if not command.reason.strip():
        raise AppError(
            "REVIEW_DECISION_INVALID", "人工決策必須填寫理由", 409
        )
    if command.decision == "PARTIALLY_ACCEPTED" and command.after_value is None:
        raise AppError(
            "REVIEW_DECISION_INVALID", "部分接受必須提供調整後內容", 409
        )
    return command.decision


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
