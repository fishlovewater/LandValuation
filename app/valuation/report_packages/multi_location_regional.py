"""Deterministic regional-factor calculations for the multi-location workbook.

This is the executable subset of ``field_rules.md`` for the residential Table
5-1 worksheet.  It deliberately consumes only confirmed, location-scoped
values.  Natural-language evidence that cannot be placed in a published
range remains blank; an LLM must never invent a formal adjustment percentage.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_ONE_HUNDRED = Decimal("100")
_RATE_QUANTUM = Decimal("0.000001")

# This identifier is persisted in the calculation snapshot.  Updating a
# threshold or percentage therefore creates a new auditable rule version,
# instead of silently changing a previously generated workbook.
RULE_VERSION = "NTPC_RESIDENTIAL_TABLE_5_1_V1"
RULE_SOURCE = "計分表.pdf／field_rules.md F02-RF 住宅用地對照表"

# Adjacent level step in percentage points from field_rules.md.  A five-level
# factor is centred on L3; the signed level score is then used for the
# benchmark-minus-comparable correction.
_STEPS = {
    "urban_plan_status": Decimal("20"),
    "land_use_zone": Decimal("5"),
    "building_coverage_rate": Decimal("2.5"),
    "floor_area_ratio": Decimal("6.25"),
    "prohibited_building": Decimal("50"),
    "restricted_building": Decimal("25"),
    "main_road_width": Decimal("3.75"),
    "average_road_width": Decimal("3"),
    "mass_transit_proximity": Decimal("2.5"),
    "station_proximity": Decimal("1"),
    "interchange_proximity": Decimal("1"),
    "road_plan": Decimal("2.5"),
    "drainage": Decimal("2.5"),
    "terrain": Decimal("2.5"),
    "market_proximity": Decimal("2"),
    "park_proximity": Decimal("2"),
    "tourist_facility_proximity": Decimal("1.5"),
    "parking_convenience": Decimal("1.5"),
    "power_gas_facility": Decimal("2.5"),
    "funeral_facility": Decimal("2.5"),
    "waste_facility": Decimal("3.75"),
    "environmental_pollution": Decimal("5"),
    "other": Decimal("3.33"),
}


def _number(value: object) -> Decimal | None:
    if value is None:
        return None
    match = _NUMBER.search(str(value).replace(",", ""))
    if match is None:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _level_for_number(value: object, boundaries: tuple[Decimal, ...]) -> str | None:
    number = _number(value)
    if number is None:
        return None
    for index, boundary in enumerate(boundaries, start=1):
        if number >= boundary:
            return f"L{index}"
    return "L5"


def _contains(value: object, *terms: str) -> bool:
    text = str(value or "").replace(" ", "")
    return any(term in text for term in terms)


def level_for_value(factor_code: str, value: object) -> str | None:
    """Return a rule level only where the confirmed value is unambiguous."""
    if value in (None, ""):
        return None
    if factor_code == "urban_plan_status":
        return "L1" if _contains(value, "都市計畫內", "計畫內") else "L5" if _contains(value, "都市計畫外", "計畫外") else None
    if factor_code == "land_use_zone":
        if _contains(value, "商業區", "捷運用地"):
            return "L1"
        if _contains(value, "住宅區", "市場用地"):
            return "L2"
        if _contains(value, "甲建", "乙建", "特定專用區", "公共設施"):
            return "L3"
        if _contains(value, "工業區", "丙建", "丁建"):
            return "L4"
        if _contains(value, "可建築"):
            return "L5"
        return None
    if factor_code == "building_coverage_rate":
        return _level_for_number(value, (Decimal("80"), Decimal("70"), Decimal("60"), Decimal("50")))
    if factor_code == "floor_area_ratio":
        return _level_for_number(value, (Decimal("460"), Decimal("360"), Decimal("260"), Decimal("180")))
    if factor_code == "main_road_width":
        return _level_for_number(value, (Decimal("28"), Decimal("20"), Decimal("12"), Decimal("8")))
    if factor_code == "average_road_width":
        return _level_for_number(value, (Decimal("20"), Decimal("15"), Decimal("10"), Decimal("8")))
    if factor_code == "prohibited_building":
        return "L1" if _contains(value, "無", "否", "沒有") else "L5" if _contains(value, "有", "是") else None
    if factor_code == "restricted_building":
        if _contains(value, "無", "否", "沒有"):
            return "L1"
        if _contains(value, "整體開發"):
            return "L5"
        if _contains(value, "限制", "高度", "面積"):
            return "L3"
        return None
    if factor_code == "road_plan":
        if _contains(value, "全部規劃", "全部開闢"):
            return "L1"
        if _contains(value, "大部分"):
            return "L2"
        if _contains(value, "部分"):
            return "L3"
        if _contains(value, "砂石"):
            return "L4"
        if _contains(value, "全無"):
            return "L5"
        return None
    if factor_code == "drainage":
        names = (("極完善", "L1"), ("非常完善", "L2"), ("普通完善", "L3"), ("不良", "L4"), ("極不良", "L5"))
    elif factor_code == "terrain":
        names = (("極平坦", "L1"), ("平坦", "L2"), ("緩傾斜", "L3"), ("低地", "L4"), ("孤立", "L5"))
    else:
        return None
    return next((level for text, level in names if _contains(value, text)), None)


def _score(level: str, step: Decimal) -> Decimal:
    if level == "L1":
        return step * Decimal("2")
    if level == "L2":
        return step
    if level == "L3":
        return Decimal("0")
    if level == "L4":
        return -step
    if level == "L5":
        return -(step * Decimal("2"))
    return Decimal("0")


def calculate_multi_location_regional_adjustments(
    locations: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Calculate Table 5-1 rates for up to three comparable locations.

    The return value is JSON-safe and can be saved in the formal calculation
    snapshot. It intentionally has no entry for missing or ambiguous inputs.
    """
    benchmark = next((item for item in locations if item.get("is_benchmark_location")), None)
    if benchmark is None:
        return {}
    benchmark_values = dict(benchmark.get("values") or {})
    benchmark_levels = {
        code: level
        for code in _STEPS
        if (level := level_for_value(code, benchmark_values.get(code))) is not None
    }
    results: dict[str, dict[str, Any]] = {}
    for location in [item for item in locations if item is not benchmark][:3]:
        rates: dict[str, str] = {}
        levels: dict[str, str] = {}
        total = Decimal("0")
        values = dict(location.get("values") or {})
        for code, step in _STEPS.items():
            benchmark_level = benchmark_levels.get(code)
            comparable_level = level_for_value(code, values.get(code))
            if benchmark_level is None or comparable_level is None:
                continue
            rate = ((_score(benchmark_level, step) - _score(comparable_level, step)) / _ONE_HUNDRED).quantize(_RATE_QUANTUM)
            levels[code] = comparable_level
            rates[code] = format(rate, "f")
            total += rate
        results[str(location["location_id"])] = {
            "factor_levels": levels,
            "factor_adjustment_rates": rates,
            "regional_adjustment_rate": format(total.quantize(_RATE_QUANTUM), "f"),
        }
    return results
