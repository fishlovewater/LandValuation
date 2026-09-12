from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.core.exceptions import AppError
from app.valuation.rounding import round_up_land_unit_price


MONEY = Decimal("0.01")


@dataclass(frozen=True)
class F01Result:
    normal_land_total_price: Decimal
    normal_land_unit_price: Decimal


def calculate_f01(
    transaction_total_price: Decimal,
    building_price_deduction: Decimal,
    special_transaction_adjustment: Decimal,
    land_area_sqm: Decimal,
) -> F01Result:
    if land_area_sqm <= 0:
        raise AppError("F01_LAND_AREA_RANGE", "F01 土地面積必須大於 0", 422)
    if building_price_deduction < 0 or building_price_deduction > transaction_total_price:
        raise AppError("F01_BUILDING_DEDUCTION_RANGE", "建物價格扣除不可超過交易總價", 422)
    if special_transaction_adjustment <= Decimal("-1"):
        raise AppError("F01_ADJUSTMENT_RANGE", "特殊交易修正不可小於或等於 -100%", 422)
    normal_total = (transaction_total_price - building_price_deduction) * (
        Decimal("1") + special_transaction_adjustment
    )
    return F01Result(
        normal_land_total_price=normal_total.quantize(MONEY, rounding=ROUND_HALF_UP),
        normal_land_unit_price=(normal_total / land_area_sqm).quantize(
            MONEY, rounding=ROUND_HALF_UP
        ),
    )


@dataclass(frozen=True)
class F04Result:
    trial_unit_price: Decimal
    parcel_unit_price: Decimal
    parcel_total_value: Decimal


def calculate_f04(
    benchmark_land_price: Decimal,
    parcel_adjustment_rate: Decimal,
    parcel_area_sqm: Decimal,
    ownership_numerator: Decimal | None,
    ownership_denominator: Decimal | None,
) -> F04Result:
    if benchmark_land_price < 0 or parcel_area_sqm <= 0:
        raise AppError("F04_INPUT_RANGE", "比準地價格不可小於 0 且宗地面積必須大於 0", 422)
    if parcel_adjustment_rate <= Decimal("-1"):
        raise AppError("F04_ADJUSTMENT_RANGE", "宗地修正率不可小於或等於 -100%", 422)
    ratio = Decimal("1")
    if ownership_numerator is not None or ownership_denominator is not None:
        if not ownership_numerator or not ownership_denominator:
            raise AppError("F04_OWNERSHIP_INVALID", "宗地權利分子與分母必須完整", 422)
        ratio = ownership_numerator / ownership_denominator
    raw_unit_price = benchmark_land_price * (Decimal("1") + parcel_adjustment_rate)
    trial_unit_price = raw_unit_price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    unit_price = round_up_land_unit_price(trial_unit_price)
    total = unit_price * parcel_area_sqm * ratio
    return F04Result(
        trial_unit_price=trial_unit_price,
        parcel_unit_price=unit_price,
        parcel_total_value=total.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
    )
