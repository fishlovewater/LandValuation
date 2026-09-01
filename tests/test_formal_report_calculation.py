from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.valuation.report_packages.formal_calculation import (
    LevelValue,
    TargetPriceInput,
    calculate_benchmark_comparison_price,
    calculate_level_adjustment,
    calculate_target_price,
)


def _level(code: str, rate: str, maximum: str = "0.20") -> LevelValue:
    return LevelValue(
        factor_definition_id=uuid4(),
        factor_level_id=uuid4(),
        factor_code="urban_plan_status",
        level_code=code,
        level_name=code,
        suggested_rate=Decimal(rate),
        maximum_impact_rate=Decimal(maximum),
    )


def test_regional_adjustment_uses_benchmark_minus_comparable_score() -> None:
    result = calculate_level_adjustment(_level("BETTER", "0.20"), _level("WORSE", "0"))
    assert result.adjustment_rate == Decimal("0.200000")


def test_table_four_sequential_formula_and_weighted_price() -> None:
    target_1 = calculate_target_price(
        TargetPriceInput(
            comparison_target_id=uuid4(),
            normal_unit_price=Decimal("15200"),
            time_adjustment_rate=Decimal("0"),
            regional_adjustment_rate=Decimal("0.0417"),
            individual_adjustment_rate=Decimal("0.03"),
            regional_absolute_total=Decimal("0.0417"),
            individual_absolute_total=Decimal("0.07"),
            weight=Decimal("0.50"),
        )
    )
    target_2 = calculate_target_price(
        TargetPriceInput(
            comparison_target_id=uuid4(),
            normal_unit_price=Decimal("13500"),
            time_adjustment_rate=Decimal("0"),
            regional_adjustment_rate=Decimal("0.0742"),
            individual_adjustment_rate=Decimal("0.06"),
            regional_absolute_total=Decimal("0.0742"),
            individual_absolute_total=Decimal("0.10"),
            weight=Decimal("0.30"),
        )
    )
    target_3 = calculate_target_price(
        TargetPriceInput(
            comparison_target_id=uuid4(),
            normal_unit_price=Decimal("12150"),
            time_adjustment_rate=Decimal("0"),
            regional_adjustment_rate=Decimal("0.0917"),
            individual_adjustment_rate=Decimal("0.15"),
            regional_absolute_total=Decimal("0.0917"),
            individual_absolute_total=Decimal("0.15"),
            weight=Decimal("0.20"),
        )
    )

    assert target_1.trial_price == Decimal("16308.86")
    assert target_2.trial_price == Decimal("15371.80")
    assert target_3.trial_price == Decimal("15253.78")
    assert calculate_benchmark_comparison_price(
        [target_1, target_2, target_3]
    ) == Decimal("15817")


def test_weight_sum_is_a_hard_error() -> None:
    target = calculate_target_price(
        TargetPriceInput(
            comparison_target_id=uuid4(),
            normal_unit_price=Decimal("100"),
            time_adjustment_rate=Decimal("0"),
            regional_adjustment_rate=Decimal("0"),
            individual_adjustment_rate=Decimal("0"),
            regional_absolute_total=Decimal("0"),
            individual_absolute_total=Decimal("0"),
            weight=Decimal("0.5"),
        )
    )
    with pytest.raises(AppError) as raised:
        calculate_benchmark_comparison_price([target])
    assert raised.value.code == "COMPARISON_WEIGHT_SUM"
