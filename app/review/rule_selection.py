from dataclasses import dataclass
from collections.abc import Mapping
from typing import AbstractSet
from datetime import date

from app.core.exceptions import AppError


@dataclass(frozen=True)
class RuleCandidate:
    rule_version_id: str
    status: str
    effective_from: date
    effective_to: date | None = None
    case_type: str | None = None
    district_code: str | None = None
    form_code: str | None = None
    priority: int = 0


@dataclass(frozen=True)
class RuleSelection:
    status: str
    rule: RuleCandidate | None


def rule_versions_are_handoff_compatible(
    source_rule: Mapping[str, object] | None,
    selected_rule: Mapping[str, object] | None,
) -> bool:
    """Accept one shared version or an explicitly reciprocal rule-set pair.

    A Valuation validation pack and a Review execution pack may intentionally
    be distinct.  Distinct versions are compatible only when immutable import
    metadata on both rule versions points to the other's rule-set code.
    """
    if source_rule is None or selected_rule is None:
        return False

    source_id = str(source_rule.get("rule_version_id") or "")
    selected_id = str(selected_rule.get("rule_version_id") or "")
    if not source_id or not selected_id:
        return False
    if source_id == selected_id:
        return True

    source_code = str(source_rule.get("rule_set_code") or "").strip()
    selected_code = str(selected_rule.get("rule_set_code") or "").strip()
    if not source_code or not selected_code or source_code == selected_code:
        return False

    source_summary = source_rule.get("import_summary")
    selected_summary = selected_rule.get("import_summary")
    if not isinstance(source_summary, dict) or not isinstance(selected_summary, dict):
        return False

    return (
        source_summary.get("paired_rule_set_code") == selected_code
        and selected_summary.get("paired_rule_set_code") == source_code
    )


def select_effective_rule(
    candidates,
    valuation_base_date: date,
    case_type: str,
    district_code: str,
    form_codes: AbstractSet[str],
) -> RuleSelection:
    def matches(candidate: RuleCandidate) -> bool:
        return (
            candidate.status == "PUBLISHED"
            and candidate.effective_from <= valuation_base_date
            and (
                candidate.effective_to is None
                or candidate.effective_to >= valuation_base_date
            )
            and candidate.case_type in (None, case_type)
            and candidate.district_code in (None, district_code)
            and (candidate.form_code is None or candidate.form_code in form_codes)
        )

    eligible = [candidate for candidate in candidates if matches(candidate)]
    if not eligible:
        return RuleSelection("REQUIRES_EXPERT_JUDGMENT", None)

    highest_priority = max(candidate.priority for candidate in eligible)
    selected = [
        candidate for candidate in eligible if candidate.priority == highest_priority
    ]
    if len(selected) > 1:
        raise AppError(
            "RULE_SELECTION_CONFLICT",
            "同一案件條件存在多筆最高優先規則",
            409,
            {"rule_version_ids": [item.rule_version_id for item in selected]},
        )
    return RuleSelection("SELECTED", selected[0])
