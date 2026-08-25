from decimal import Decimal

import pytest

from app.core.exceptions import AppError
from app.review.recalculation import (
    grade_for_value,
    recalculate_adjustment_rate,
    recalculate_weighted_price,
)


def test_adjustment_rate_is_quantized_without_float():
    result = recalculate_adjustment_rate(
        Decimal("-12"), Decimal("-5"), Decimal("0")
    )

    assert result.system_rate == Decimal("-5.00")
    assert result.difference == Decimal("-7.00")
    assert result.within_tolerance is False


def test_weighted_price_preserves_unrounded_and_final_values():
    result = recalculate_weighted_price(
        (
            (Decimal("101.11"), Decimal("0.6")),
            (Decimal("99.99"), Decimal("0.4")),
        )
    )

    assert result.unrounded == Decimal("100.662")
    assert result.final == Decimal("100.66")


def test_weighted_price_rejects_invalid_weight_sum():
    with pytest.raises(AppError) as error:
        recalculate_weighted_price(((Decimal("100"), Decimal("0.9")),))

    assert error.value.code == "INVALID_WEIGHT_SUM"


def test_grade_for_value_uses_inclusive_decimal_bands():
    bands = (("A", Decimal("0"), Decimal("10")), ("B", Decimal("10.01"), None))

    assert grade_for_value(Decimal("10"), bands) == "A"
    assert grade_for_value(Decimal("10.01"), bands) == "B"
