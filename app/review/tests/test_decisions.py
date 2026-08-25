import pytest

from app.core.exceptions import AppError
from app.review.decisions import (
    CaseDecisionCommand,
    FindingDecisionCommand,
    ReviewGateSummary,
    validate_case_decision,
    validate_finding_decision,
)


@pytest.mark.parametrize(
    "decision",
    [
        "ACCEPTED",
        "PARTIALLY_ACCEPTED",
        "REJECTED",
        "REQUIRES_SUPPLEMENT",
        "EXPERT_REVIEW",
    ],
)
def test_finding_decisions_return_resulting_status(decision):
    after_value = {"rate": "-7"} if decision == "PARTIALLY_ACCEPTED" else None
    command = FindingDecisionCommand(decision, "人工查核理由", after_value)

    assert validate_finding_decision(command) == decision


def test_every_finding_decision_requires_nonblank_reason():
    with pytest.raises(AppError) as error:
        validate_finding_decision(FindingDecisionCommand("ACCEPTED", "  "))

    assert error.value.code == "REVIEW_DECISION_INVALID"
    assert error.value.status_code == 409


def test_partial_acceptance_requires_after_value():
    with pytest.raises(AppError) as error:
        validate_finding_decision(
            FindingDecisionCommand("PARTIALLY_ACCEPTED", "部分接受")
        )

    assert error.value.code == "REVIEW_DECISION_INVALID"


def test_unresolved_high_risk_blocks_approval_without_override():
    with pytest.raises(AppError) as error:
        validate_case_decision(
            CaseDecisionCommand("APPROVED", "擬核准"),
            ReviewGateSummary(unresolved_high_count=1),
        )

    assert error.value.code == "REVIEW_DECISION_INVALID"


def test_high_risk_override_requires_permission_and_reason():
    with pytest.raises(AppError):
        validate_case_decision(
            CaseDecisionCommand(
                "APPROVED",
                "擬核准",
                has_override_permission=True,
                override_reason=" ",
            ),
            ReviewGateSummary(unresolved_high_count=1),
        )

    result = validate_case_decision(
        CaseDecisionCommand(
            "APPROVED",
            "擬核准",
            has_override_permission=True,
            override_reason="主管依現勘資料覆核",
        ),
        ReviewGateSummary(unresolved_high_count=1),
    )
    assert result == "APPROVED"
