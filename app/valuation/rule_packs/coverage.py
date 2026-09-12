from __future__ import annotations

from datetime import date
from typing import Protocol


# Ministry of the Interior administrative district codes. The eight-digit form is
# retained because it is the code form used by the approved New Taipei reference.
NEW_TAIPEI_DISTRICTS: dict[str, str] = {
    "65000010": "板橋區",
    "65000020": "三重區",
    "65000030": "中和區",
    "65000040": "永和區",
    "65000050": "新莊區",
    "65000060": "新店區",
    "65000070": "樹林區",
    "65000080": "鶯歌區",
    "65000090": "三峽區",
    "65000100": "淡水區",
    "65000110": "汐止區",
    "65000120": "瑞芳區",
    "65000130": "土城區",
    "65000140": "蘆洲區",
    "65000150": "五股區",
    "65000160": "泰山區",
    "65000170": "林口區",
    "65000180": "深坑區",
    "65000190": "石碇區",
    "65000200": "坪林區",
    "65000210": "三芝區",
    "65000220": "石門區",
    "65000230": "八里區",
    "65000240": "平溪區",
    "65000250": "雙溪區",
    "65000260": "貢寮區",
    "65000270": "金山區",
    "65000280": "萬里區",
    "65000290": "烏來區",
}

NEW_TAIPEI_DISTRICT_CODES = frozenset(NEW_TAIPEI_DISTRICTS)
NEW_TAIPEI_CITYWIDE_SCOPE: dict[str, object] = {
    "mode": "ALL",
    "district_codes": [],
}


class RuleCoverageLike(Protocol):
    jurisdiction_code: str | None
    status: str
    effective_from: date | None
    effective_to: date | None
    district_scope: dict | None
    land_use_types: list | None


def expanded_district_codes(scope: dict | None) -> frozenset[str]:
    value = scope if isinstance(scope, dict) else {}
    if value.get("mode") == "ALL":
        return NEW_TAIPEI_DISTRICT_CODES
    if value.get("mode") == "INCLUDE":
        return frozenset(value.get("district_codes") or [])
    return frozenset()


def rule_covers(
    rule: RuleCoverageLike,
    *,
    district_code: str,
    land_use_type: str,
    valuation_date: date,
) -> bool:
    return (
        rule.jurisdiction_code == "NEW_TAIPEI_CITY"
        and rule.status == "PUBLISHED"
        and rule.effective_from is not None
        and rule.effective_from <= valuation_date
        and (rule.effective_to is None or rule.effective_to >= valuation_date)
        and district_code in expanded_district_codes(rule.district_scope)
        and land_use_type in set(rule.land_use_types or [])
    )


def rules_overlap(left: RuleCoverageLike, right: RuleCoverageLike) -> bool:
    if left.effective_from is None or right.effective_from is None:
        return False
    date_overlap = (
        (right.effective_to is None or left.effective_from <= right.effective_to)
        and (left.effective_to is None or right.effective_from <= left.effective_to)
    )
    district_overlap = bool(
        expanded_district_codes(left.district_scope)
        & expanded_district_codes(right.district_scope)
    )
    land_use_overlap = bool(
        set(left.land_use_types or []) & set(right.land_use_types or [])
    )
    return date_overlap and district_overlap and land_use_overlap
