from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.core.exceptions import AppError


RATE_QUANTUM = Decimal("0.01")
WEIGHT_TOTAL = Decimal("1.000000")
WEIGHT_TOLERANCE = Decimal("0.000001")


@dataclass(frozen=True)
class AdjustmentResult:
    reported_rate: Decimal
    system_rate: Decimal
    difference: Decimal
    within_tolerance: bool


@dataclass(frozen=True)
class WeightedPriceResult:
    unrounded: Decimal
    final: Decimal


def recalculate_adjustment_rate(
    reported_rate: Decimal, system_rate: Decimal, tolerance: Decimal
) -> AdjustmentResult:
    reported = reported_rate.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
    system = system_rate.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
    difference = (reported - system).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
    return AdjustmentResult(
        reported,
        system,
        difference,
        abs(difference) <= tolerance,
    )


def recalculate_weighted_price(items) -> WeightedPriceResult:
    items = tuple(items)
    if any(weight < 0 for _, weight in items):
        raise AppError(
            "INVALID_WEIGHT",
            "比較標的權重不得為負值",
            422,
        )
    total_weight = sum((weight for _, weight in items), Decimal("0"))
    if abs(total_weight - WEIGHT_TOTAL) > WEIGHT_TOLERANCE:
        raise AppError(
            "INVALID_WEIGHT_SUM",
            "比較標的權重合計必須為 1",
            422,
            {"weight_sum": str(total_weight)},
        )
    unrounded = sum((price * weight for price, weight in items), Decimal("0"))
    return WeightedPriceResult(
        unrounded=unrounded,
        final=unrounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    )


def grade_for_value(value: Decimal, bands) -> str | None:
    for grade, minimum, maximum in bands:
        if value >= minimum and (maximum is None or value <= maximum):
            return grade
    return None
