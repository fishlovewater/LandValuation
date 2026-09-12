import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.exceptions import AppError

FORMULA_VERSION = "F03_WEIGHTED_PRICE_V1"
ROUNDING_MODE = "ROUND_HALF_UP"
RESULT_SCALE = 2
RESULT_QUANTUM = Decimal("0.01")
WEIGHT_TOLERANCE = Decimal("0.000001")


@dataclass(frozen=True)
class F03CalculationOutput:
    result: Decimal
    raw_result: Decimal
    steps: list[dict[str, str]]
    input_snapshot: dict[str, str | None]
    input_fingerprint: str


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def calculate_f03_price(
    *,
    comparison_price: Decimal | None,
    comparison_weight: Decimal,
    income_price: Decimal | None,
    income_weight: Decimal,
) -> F03CalculationOutput:
    values = (comparison_weight, income_weight)
    if any(value < 0 or value > 1 for value in values):
        raise AppError("F03_WEIGHT_RANGE", "比較法與收益法權重必須介於 0 到 1", 422)
    if abs((comparison_weight + income_weight) - Decimal("1")) > WEIGHT_TOLERANCE:
        raise AppError("F03_WEIGHT_SUM", "比較法與收益法權重合計必須等於 1", 422)
    if comparison_weight > 0 and comparison_price is None:
        raise AppError("F03_COMPARISON_PRICE_REQUIRED", "比較法權重大於 0 時必須提供比較價格", 422)
    if income_weight > 0 and income_price is None:
        raise AppError("F03_INCOME_PRICE_REQUIRED", "收益法權重大於 0 時必須提供收益價格", 422)
    if any(
        price is not None and price < 0
        for price in (comparison_price, income_price)
    ):
        raise AppError("F03_PRICE_RANGE", "F03 價格不可小於 0", 422)

    comparison_component = (comparison_price or Decimal("0")) * comparison_weight
    income_component = (income_price or Decimal("0")) * income_weight
    raw_result = comparison_component + income_component
    result = raw_result.quantize(RESULT_QUANTUM, rounding=ROUND_HALF_UP)
    inputs = {
        "comparison_price": _decimal_text(comparison_price),
        "comparison_weight": _decimal_text(comparison_weight),
        "income_price": _decimal_text(income_price),
        "income_weight": _decimal_text(income_weight),
    }
    fingerprint_payload = {
        "formula_version": FORMULA_VERSION,
        "rounding_mode": ROUNDING_MODE,
        "result_scale": RESULT_SCALE,
        "inputs": inputs,
    }
    return F03CalculationOutput(
        result=result,
        raw_result=raw_result,
        steps=[
            {
                "step": "comparison_component",
                "expression": "comparison_price * comparison_weight",
                "result": _decimal_text(comparison_component) or "0",
            },
            {
                "step": "income_component",
                "expression": "income_price * income_weight",
                "result": _decimal_text(income_component) or "0",
            },
            {
                "step": "weighted_sum",
                "expression": "comparison_component + income_component",
                "result": _decimal_text(raw_result) or "0",
            },
            {
                "step": "rounding",
                "expression": "ROUND_HALF_UP to 2 decimal places",
                "result": _decimal_text(result) or "0",
            },
        ],
        input_snapshot=inputs,
        input_fingerprint=_fingerprint(fingerprint_payload),
    )


def build_calculation_snapshot(
    *,
    output: F03CalculationOutput,
    benchmark_valuation_id: str,
    benchmark_land_id: str,
    valuation_base_date: str,
) -> dict[str, Any]:
    return {
        "formula_version": FORMULA_VERSION,
        "formula": (
            "comparison_price * comparison_weight + "
            "income_price * income_weight"
        ),
        "rounding_mode": ROUNDING_MODE,
        "result_scale": RESULT_SCALE,
        "benchmark_valuation_id": benchmark_valuation_id,
        "benchmark_land_id": benchmark_land_id,
        "valuation_base_date": valuation_base_date,
        "inputs": output.input_snapshot,
        "input_fingerprint": output.input_fingerprint,
        "steps": output.steps,
        "raw_result": _decimal_text(output.raw_result),
        "result": _decimal_text(output.result),
    }
