from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader

from app.core.exceptions import AppError
from app.valuation.operations.calculation import (
    FORMULA_VERSION,
    calculate_f03_price,
)
from app.valuation.operations.report_builder import build_f03_report_pdf


def test_f03_calculation_is_deterministic_and_applies_article_21_rounding() -> None:
    values = {
        "comparison_price": Decimal("100.005"),
        "comparison_weight": Decimal("1"),
        "income_price": None,
        "income_weight": Decimal("0"),
    }

    first = calculate_f03_price(**values)
    second = calculate_f03_price(**values)

    assert first.result == Decimal("110")
    assert first.input_fingerprint == second.input_fingerprint
    assert first.steps == second.steps
    assert FORMULA_VERSION == "F03_WEIGHTED_PRICE_V2"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("99.13", "100"),
        ("100", "100"),
        ("811", "820"),
        ("1000", "1000"),
        ("11111", "11200"),
        ("100000", "100000"),
        ("1111111", "1112000"),
    ],
)
def test_f03_article_21_rounding_matches_official_workbook_examples(
    value: str, expected: str
) -> None:
    result = calculate_f03_price(
        comparison_price=Decimal(value),
        comparison_weight=Decimal("1"),
        income_price=None,
        income_weight=Decimal("0"),
    )
    assert result.result == Decimal(expected)


def test_f03_calculation_requires_price_for_positive_weight() -> None:
    with pytest.raises(AppError) as captured:
        calculate_f03_price(
            comparison_price=None,
            comparison_weight=Decimal("0.5"),
            income_price=Decimal("100"),
            income_weight=Decimal("0.5"),
        )

    assert captured.value.code == "F03_COMPARISON_PRICE_REQUIRED"


def test_f03_report_is_valid_pdf_and_contains_backend_values() -> None:
    calculation_id = uuid4()
    validation_run_id = uuid4()
    payload = {
        "case_no": "001",
        "case_title": "測試案件",
        "valuation_base_date": "2026-08-25",
        "city_code": "TPE",
        "district_code": "123",
        "form_version": 1,
        "benchmark_land_no": "12",
        "price_zone_no": "TEST-ZONE-001",
        "parcel_display": "測試段／—／12",
        "area_sqm": "402.0000",
        "comparison_price": "12345.00",
        "comparison_weight": "1.000000",
        "income_price": None,
        "income_weight": "0.000000",
        "benchmark_land_price": "12345.00",
        "formula_version": FORMULA_VERSION,
        "calculation_id": calculation_id,
        "ruleset_version": "F03_MVP_VALIDATION:v1",
        "validation_summary": "8／0／0",
        "validation_run_id": validation_run_id,
        "request_id": uuid4(),
    }

    pdf = build_f03_report_pdf(payload)
    reader = PdfReader(BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert pdf.startswith(b"%PDF-")
    assert len(reader.pages) >= 1
    assert "12345.00" in extracted
    assert str(calculation_id) in extracted
    assert str(validation_run_id) in extracted
