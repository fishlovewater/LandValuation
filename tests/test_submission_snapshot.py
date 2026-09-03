from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.valuation.submissions.snapshot import (
    build_submission_snapshot,
    snapshot_bytes,
    snapshot_fingerprint,
)


def test_snapshot_decimal_is_stable_string() -> None:
    snapshot = build_submission_snapshot(
        case_version=3,
        applied_fields=[
            {
                "form_code": "F03",
                "field_name": "unit_price",
                "confirmed_value": Decimal("123.4500"),
            }
        ],
        calculations={"total": Decimal("246.9000")},
        documents=[],
        validation={},
    )

    assert snapshot["applied_fields"][0]["confirmed_value"] == "123.4500"
    assert snapshot["calculations"]["total"] == "246.9000"
    assert snapshot_fingerprint(snapshot) == snapshot_fingerprint(snapshot)


def test_snapshot_fingerprint_ignores_dictionary_input_order() -> None:
    first = {
        "case_version": 3,
        "nested": {"z": Decimal("1.00"), "a": "value"},
    }
    second = {
        "nested": {"a": "value", "z": Decimal("1.00")},
        "case_version": 3,
    }

    assert snapshot_bytes(first) == snapshot_bytes(second)
    assert snapshot_fingerprint(first) == snapshot_fingerprint(second)


def test_snapshot_rejects_float_at_any_depth() -> None:
    with pytest.raises(
        TypeError,
        match="^float is not allowed in submission snapshots$",
    ):
        snapshot_fingerprint({"calculations": {"total": 246.9}})


def test_snapshot_normalizes_uuid_and_datetime_to_strings() -> None:
    identifier = uuid4()
    occurred_at = datetime(2026, 9, 3, 10, 11, 12, tzinfo=UTC)

    encoded = snapshot_bytes({"id": identifier, "occurred_at": occurred_at})

    assert encoded == (
        f'{{"id":"{identifier}","occurred_at":"{occurred_at.isoformat()}"}}'.encode()
    )
