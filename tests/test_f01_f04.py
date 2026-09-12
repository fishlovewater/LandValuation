from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.valuation.f01_f04_calculation import calculate_f01, calculate_f04
from app.valuation.f01_f04_schemas import F01DraftData, F04FactorDraft, F04ParcelDraft


def test_f01_normal_land_price_is_decimal_and_deterministic() -> None:
    result = calculate_f01(
        Decimal("10000000"), Decimal("1000000"), Decimal("0.02"), Decimal("100")
    )
    assert result.normal_land_total_price == Decimal("9180000.00")
    assert result.normal_land_unit_price == Decimal("91800.00")


def test_f01_rejects_building_deduction_over_total() -> None:
    with pytest.raises(AppError) as raised:
        calculate_f01(Decimal("100"), Decimal("101"), Decimal("0"), Decimal("1"))
    assert raised.value.code == "F01_BUILDING_DEDUCTION_RANGE"


def test_f01_nonzero_adjustment_requires_confirmation() -> None:
    with pytest.raises(ValidationError, match="使用者確認"):
        F01DraftData(special_transaction_adjustment=Decimal("0.01"))


def test_f04_parcel_price_applies_ownership_ratio() -> None:
    result = calculate_f04(
        Decimal("200000"), Decimal("0.05"), Decimal("100"), Decimal("1"), Decimal("2")
    )
    assert result.parcel_unit_price == Decimal("210000.00")
    assert result.parcel_total_value == Decimal("10500000")


def test_f04_uses_trial_rounding_then_article_21_tail_rounding() -> None:
    result = calculate_f04(
        Decimal("11111"), Decimal("0"), Decimal("1"), None, None
    )
    assert result.trial_unit_price == Decimal("11111")
    assert result.parcel_unit_price == Decimal("11200")
    assert result.parcel_total_value == Decimal("11200")


def test_f04_nonzero_adjustment_requires_confirmation() -> None:
    with pytest.raises(ValidationError, match="正式規則來源"):
        F04ParcelDraft(parcel_id="00000000-0000-0000-0000-000000000001", parcel_adjustment_rate="0.01")


def test_f04_factor_rows_use_formal_individual_factor_codes() -> None:
    row = F04FactorDraft(
        factor_code="individual_area",
        condition_value="500㎡",
        difference_rate="0.01",
        source_notes="正式個別因素規則",
        confirmed_by_user=True,
    )
    parcel = F04ParcelDraft(
        parcel_id="00000000-0000-0000-0000-000000000001",
        factor_rows=[row],
    )
    assert parcel.factor_rows[0].factor_code == "individual_area"
