from datetime import date

import pytest

from app.core.exceptions import AppError
from app.review.rule_selection import RuleCandidate, select_effective_rule


BASE_DATE = date(2026, 8, 25)


def rule(rule_id="rule-1", **overrides):
    values = {
        "rule_version_id": rule_id,
        "status": "PUBLISHED",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "case_type": "LAND",
        "district_code": "F01",
        "form_code": "F01",
        "priority": 10,
    }
    values.update(overrides)
    return RuleCandidate(**values)


def select(candidates):
    return select_effective_rule(candidates, BASE_DATE, "LAND", "F01", {"F01"})


def test_selects_only_published_effective_matching_rule():
    result = select(
        [
            rule("draft", status="DRAFT", priority=100),
            rule("expired", effective_to=date(2026, 8, 24), priority=90),
            rule("other-district", district_code="F02", priority=80),
            rule("selected", priority=20),
        ]
    )

    assert result.status == "SELECTED"
    assert result.rule.rule_version_id == "selected"


def test_ambiguous_highest_priority_rules_raise_conflict():
    with pytest.raises(AppError) as error:
        select([rule("one"), rule("two")])

    assert error.value.code == "RULE_SELECTION_CONFLICT"
    assert error.value.status_code == 409


def test_no_match_requires_expert_judgment():
    result = select([rule(status="DRAFT")])

    assert result.status == "REQUIRES_EXPERT_JUDGMENT"
    assert result.rule is None


def test_selects_candidate_matching_any_form_code_in_set():
    result = select_effective_rule(
        [rule("f02", form_code="F02"), rule("f03", form_code="F03")],
        BASE_DATE,
        "LAND",
        "F01",
        {"F01", "F03"},
    )

    assert result.status == "SELECTED"
    assert result.rule.rule_version_id == "f03"
