import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
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
from app.review.schemas import FindingTriageRequest


@pytest.mark.parametrize(
    "decision",
    ["CONFIRMED_ISSUE", "DISMISSED_FALSE_POSITIVE", "EXPERT_REVIEW"],
)
def test_finding_triage_accepts_only_review_meaning(decision):
    assert (
        validate_finding_triage(FindingTriageCommand(decision, "已核對證據"))
        == decision
    )


def test_finding_triage_requires_reason():
    with pytest.raises(AppError, match="必須填寫理由"):
        validate_finding_triage(FindingTriageCommand("CONFIRMED_ISSUE", "   "))


@pytest.mark.parametrize("legacy", ["ACCEPTED", "REJECTED", "PARTIALLY_ACCEPTED"])
def test_new_triage_schema_rejects_legacy_value_choices(legacy):
    with pytest.raises(ValidationError):
        FindingTriageRequest(
            review_id="00000000-0000-0000-0000-000000000001",
            decision=legacy,
            reason="x",
        )


def test_new_triage_schema_rejects_after_value():
    with pytest.raises(ValidationError):
        FindingTriageRequest(
            review_id="00000000-0000-0000-0000-000000000001",
            decision="CONFIRMED_ISSUE",
            reason="x",
            after_value={"value": "不得接受"},
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


@pytest.mark.parametrize(
    "after_value",
    [
        None,
        {},
        [],
        "",
        "   ",
        {"value": ""},
        {"value": "   "},
        {"field_path": "comparables[0].adjustment_rate", "value": ""},
        {"field_path": None, "value": ""},
        {"nested": {}},
    ],
)
def test_partial_acceptance_rejects_semantically_empty_after_value(after_value):
    with pytest.raises(AppError) as error:
        validate_finding_decision(
            FindingDecisionCommand("PARTIALLY_ACCEPTED", "部分接受", after_value)
        )

    assert error.value.code == "REVIEW_DECISION_INVALID"


@pytest.mark.parametrize(
    "after_value",
    [
        {"reported_rate": "-7"},
        {"field_path": None, "value": "-7"},
    ],
)
def test_partial_acceptance_accepts_meaningful_after_value(after_value):
    assert (
        validate_finding_decision(
            FindingDecisionCommand("PARTIALLY_ACCEPTED", "部分接受", after_value)
        )
        == "PARTIALLY_ACCEPTED"
    )


@pytest.mark.parametrize(
    ("decision", "source", "expected"),
    [
        ("REJECTED", "REPORTED", "-12"),
        ("ACCEPTED", "SYSTEM", "-5"),
        ("PARTIALLY_ACCEPTED", "REVIEWER", "-7"),
    ],
)
def test_build_finding_after_value_uses_explicit_source(decision, source, expected):
    command = FindingDecisionCommand(
        decision=decision,
        reason="人工覆核",
        after_value={"value": "-7"} if decision == "PARTIALLY_ACCEPTED" else None,
    )
    context = FindingValueContext(
        field_path="comparables[0].adjustment_rate",
        reported_value="-12",
        system_value="-5",
    )

    assert build_finding_after_value(command, context) == {
        "selection_source": source,
        "field_path": context.field_path,
        "value": expected,
    }


def test_supplement_has_no_final_value():
    command = FindingDecisionCommand("REQUIRES_SUPPLEMENT", "請補正")
    context = FindingValueContext("field", "original", "system")

    assert build_finding_after_value(command, context) is None


def test_system_choice_rejects_missing_system_value():
    with pytest.raises(AppError) as error:
        build_finding_after_value(
            FindingDecisionCommand("ACCEPTED", "採用系統建議"),
            FindingValueContext("field", "original", None),
        )

    assert error.value.code == "REVIEW_DECISION_INVALID"


@pytest.mark.parametrize(
    "summary",
    [
        ReviewGateSummary(False, 0, 0, 0),
        ReviewGateSummary(True, 1, 0, 0),
        ReviewGateSummary(True, 0, 1, 0),
        ReviewGateSummary(True, 0, 0, 1),
    ],
)
def test_any_incomplete_gate_blocks_approval(summary):
    with pytest.raises(AppError) as error:
        validate_case_decision(CaseDecisionCommand("APPROVED", "擬核准"), summary)

    assert error.value.code == "REVIEW_DECISION_INVALID"
    assert error.value.details["blockers"]


def test_complete_gate_allows_approval():
    assert (
        validate_case_decision(
            CaseDecisionCommand("APPROVED", "擬核准"),
            ReviewGateSummary(True, 0, 0, 0),
        )
        == "APPROVED"
    )
