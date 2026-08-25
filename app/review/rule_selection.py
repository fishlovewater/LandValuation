from dataclasses import dataclass
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
