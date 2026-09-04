"""Deterministic F02-RF and F02 calculations for the six-page report.

Rates are stored as decimal fractions (``0.0417`` means ``4.17%``).  The
formula follows the supplied official operating manual's Table 4 example:

``normal price × date factor × regional factor × individual factor``.

AI output is intentionally absent from this module.  It accepts only values
that the service has already matched to a published rule version and values
that were explicitly confirmed by a user.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from app.core.exceptions import AppError


RATE_QUANTUM = Decimal("0.000001")
PRICE_QUANTUM = Decimal("0.01")
INTEGER_PRICE_QUANTUM = Decimal("1")
ONE = Decimal("1")


@dataclass(frozen=True)
class LevelValue:
    factor_definition_id: UUID
    factor_level_id: UUID
    factor_code: str
    level_code: str
    level_name: str
    suggested_rate: Decimal
    maximum_impact_rate: Decimal


@dataclass(frozen=True)
class FactorAdjustment:
    factor_code: str
    benchmark: LevelValue
    comparable: LevelValue
    adjustment_rate: Decimal


@dataclass(frozen=True)
class TargetPriceInput:
    comparison_target_id: UUID
    normal_unit_price: Decimal
    time_adjustment_rate: Decimal
    regional_adjustment_rate: Decimal
    individual_adjustment_rate: Decimal
    regional_absolute_total: Decimal
    individual_absolute_total: Decimal
    weight: Decimal


@dataclass(frozen=True)
class TargetPriceResult:
    comparison_target_id: UUID
    date_adjusted_price: Decimal
    regional_adjusted_price: Decimal
    trial_price: Decimal
    total_adjustment_absolute: Decimal
    weight: Decimal


def _rate(value: Decimal) -> Decimal:
    return Decimal(value).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_level_adjustment(
    benchmark: LevelValue,
    comparable: LevelValue,
) -> FactorAdjustment:
    if benchmark.factor_code != comparable.factor_code:
        raise AppError(
            "FACTOR_LEVEL_MISMATCH",
            "比準地與比較標的因素級距不屬於同一因素",
            422,
        )
    if benchmark.maximum_impact_rate != comparable.maximum_impact_rate:
        raise AppError(
            "RULE_FACTOR_BOUND_INCONSISTENT",
            f"因素 {benchmark.factor_code} 的最大影響範圍不一致",
            409,
        )
    # A higher rule score means a condition that contributes more to price.
    # The comparable is adjusted to the benchmark, therefore benchmark minus
    # comparable is the signed correction.
    adjustment = _rate(benchmark.suggested_rate - comparable.suggested_rate)
    if abs(adjustment) > benchmark.maximum_impact_rate:
        raise AppError(
            "FACTOR_ADJUSTMENT_OUT_OF_RANGE",
            f"因素 {benchmark.factor_code} 修正率超出正式規則最大影響範圍",
            422,
            {
                "factor_code": benchmark.factor_code,
                "adjustment_rate": format(adjustment, "f"),
                "maximum_impact_rate": format(
                    benchmark.maximum_impact_rate, "f"
                ),
            },
        )
    return FactorAdjustment(
        factor_code=benchmark.factor_code,
        benchmark=benchmark,
        comparable=comparable,
        adjustment_rate=adjustment,
    )


def sum_adjustments(values: list[FactorAdjustment]) -> Decimal:
    return _rate(sum((item.adjustment_rate for item in values), Decimal("0")))


def sum_absolute_adjustments(values: list[FactorAdjustment]) -> Decimal:
    return _rate(sum((abs(item.adjustment_rate) for item in values), Decimal("0")))


def calculate_target_price(value: TargetPriceInput) -> TargetPriceResult:
    if value.normal_unit_price < 0:
        raise AppError("COMPARISON_PRICE_RANGE", "比較標的正常單價不可小於 0", 422)
    if any(
        rate <= Decimal("-1")
        for rate in (
            value.time_adjustment_rate,
            value.regional_adjustment_rate,
            value.individual_adjustment_rate,
        )
    ):
        raise AppError(
            "COMPARISON_ADJUSTMENT_RANGE",
            "任一價格調整率不可小於或等於 -100%",
            422,
        )
    if value.weight < 0 or value.weight > 1:
        raise AppError("COMPARISON_WEIGHT_RANGE", "比較標的權重必須介於 0 與 1", 422)

    date_adjusted = value.normal_unit_price * (ONE + value.time_adjustment_rate)
    regional_adjusted = date_adjusted * (ONE + value.regional_adjustment_rate)
    raw_trial = regional_adjusted * (ONE + value.individual_adjustment_rate)
    absolute_total = _rate(
        abs(value.time_adjustment_rate)
        + value.regional_absolute_total
        + value.individual_absolute_total
    )
    return TargetPriceResult(
        comparison_target_id=value.comparison_target_id,
        date_adjusted_price=date_adjusted.quantize(
            PRICE_QUANTUM, rounding=ROUND_HALF_UP
        ),
        regional_adjusted_price=regional_adjusted.quantize(
            PRICE_QUANTUM, rounding=ROUND_HALF_UP
        ),
        trial_price=raw_trial.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP),
        total_adjustment_absolute=absolute_total,
        weight=_rate(value.weight),
    )


def calculate_benchmark_comparison_price(
    values: list[TargetPriceResult],
) -> Decimal:
    if not 1 <= len(values) <= 3:
        raise AppError("COMPARISON_TARGET_COUNT", "比較標的必須為 1 至 3 筆", 422)
    weight_total = sum((item.weight for item in values), Decimal("0"))
    if _rate(weight_total) != ONE.quantize(RATE_QUANTUM):
        raise AppError("COMPARISON_WEIGHT_SUM", "比較標的權重合計必須等於 1", 422)
    weighted = sum(
        (item.trial_price * item.weight for item in values),
        Decimal("0"),
    )
    return weighted.quantize(INTEGER_PRICE_QUANTUM, rounding=ROUND_HALF_UP)
