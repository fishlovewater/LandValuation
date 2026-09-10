from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.valuation.comparison_setup import ComparisonSetupCreate


def _target(**overrides):
    values = {
        "transaction_no": "TX-001",
        "transaction_date": date(2026, 1, 1),
        "transaction_total_price": Decimal("10000000"),
        "normal_land_unit_price": Decimal("50000"),
        "weight": Decimal("1"),
        "source_notes": "交易明細第 1 列，已人工確認",
    }
    values.update(overrides)
    return values


def test_comparison_setup_accepts_one_to_three_traceable_targets():
    payload = ComparisonSetupCreate(
        report_id=uuid4(), benchmark_land_id=uuid4(), targets=[_target()]
    )

    assert len(payload.targets) == 1
    assert payload.targets[0].normal_land_unit_price == Decimal("50000")


@pytest.mark.parametrize(
    "targets",
    [
        [_target(weight=Decimal("0.6"))],
        [_target(), _target()],
    ],
)
def test_comparison_setup_rejects_invalid_weights_or_duplicate_transactions(targets):
    with pytest.raises(ValidationError):
        ComparisonSetupCreate(
            report_id=uuid4(), benchmark_land_id=uuid4(), targets=targets
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("transaction_no", "T" * 31),
        ("subject_address", "A" * 301),
    ],
)
def test_comparison_setup_rejects_values_wider_than_database_columns(
    field_name, value
):
    """Request validation must fail before PostgreSQL varchar constraints do."""
    with pytest.raises(ValidationError):
        ComparisonSetupCreate(
            report_id=uuid4(),
            benchmark_land_id=uuid4(),
            targets=[_target(**{field_name: value})],
        )
