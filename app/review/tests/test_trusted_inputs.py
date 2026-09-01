import asyncio
from decimal import Decimal
from uuid import uuid4

from app.core.exceptions import AppError
from app.review.repository import ReviewRepository
from app.review.service import ReviewService
from app.review.trusted_inputs import (
    TrustedField,
    prepare_trusted_rules,
    required_field_problems,
    trusted_fields_by_code,
    validate_rule_contracts,
)
import pytest


def field(name="adjustment_rate", *, form_code="F03", value="-12"):
    return TrustedField(
        extracted_field_id="field-1",
        form_code=form_code,
        field_name=name,
        confirmed_value=value,
        source_page=3,
        source_text="來源原文",
        confidence="0.9",
        field_status="APPLIED",
        confirmed_by_user_id="reviewer-1",
        confirmed_at="2026-09-02T00:00:00Z",
    )


def test_applied_confirmed_field_is_available_by_canonical_field_name():
    fields = trusted_fields_by_code([field()])

    assert fields["adjustment_rate"].confirmed_value == "-12"
    assert fields["adjustment_rate"].value_type == "DECIMAL"


def test_missing_canonical_field_is_reported_missing():
    assert required_field_problems({"adjustment_rate"}, {})[0].code == "TRUSTED_INPUT_MISSING"


@pytest.mark.parametrize(
    "ordered_fields",
    [
        [field(), field()],
        [field(), field(form_code="F04")],
    ],
)
def test_duplicate_applied_fields_are_not_trusted_in_either_form(ordered_fields):
    fields = trusted_fields_by_code(ordered_fields)

    assert required_field_problems({"adjustment_rate"}, fields)[0].code == "TRUSTED_INPUT_MISSING"


def test_float_confirmed_value_is_not_a_trusted_decimal():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "ADJUSTMENT_RATE",
                "target_field_code": "adjustment_rate",
                "rule_expression": '{"system_rate": "0.3", "tolerance": "0.1"}',
            }
        ]
    )

    with pytest.raises(AppError) as raised:
        prepare_trusted_rules(contracts, {"adjustment_rate": field(value=0.1 + 0.2)})

    assert raised.value.code == "TRUSTED_INPUT_UNVERIFIED"


def test_rule_json_numbers_are_parsed_as_exact_decimals():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "ADJUSTMENT_RATE",
                "target_field_code": "adjustment_rate",
                "rule_expression": '{"system_rate": 0.1, "tolerance": 0.2}',
            }
        ]
    )

    contract = contracts[0]
    assert contract.system_rate == Decimal("0.1")
    assert contract.tolerance == Decimal("0.2")
    assert contract.configuration == {
        "system_rate": Decimal("0.1"),
        "tolerance": Decimal("0.2"),
    }


class _MappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


class _RecordingSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.parameters = None

    async def execute(self, statement, parameters):
        self.statement = str(statement)
        self.parameters = parameters
        return _MappingsResult(self.rows)


def test_repository_reads_only_applied_confirmed_canonical_fields():
    case_id = uuid4()
    session = _RecordingSession(
        [
            {
                "extracted_field_id": uuid4(),
                "form_code": "F03",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12",
                "source_page": 3,
                "source_text": "來源原文",
                "confidence": "0.9",
                "field_status": "APPLIED",
                "confirmed_by_user_id": uuid4(),
                "confirmed_at": "2026-09-02T00:00:00Z",
            }
        ]
    )

    rows = asyncio.run(
        ReviewRepository(session).list_applied_confirmed_extracted_fields(case_id)
    )

    assert rows[0]["field_name"] == "adjustment_rate"
    assert session.parameters == {"case_id": case_id}
    assert "ef.field_status = 'APPLIED'" in session.statement
    assert "ef.confirmed_value IS NOT NULL" in session.statement
    assert "extraction_run_id" not in session.statement
    assert "field_code" not in session.statement
    assert "normalized_value" not in session.statement


def test_service_maps_canonical_applied_field_to_trusted_field():
    trusted = ReviewService._trusted_field(
        {
            "extracted_field_id": uuid4(),
            "form_code": "F03",
            "field_name": "adjustment_rate",
            "confirmed_value": "-12",
            "source_page": 3,
            "source_text": "來源原文",
            "confidence": "0.9",
            "field_status": "APPLIED",
            "confirmed_by_user_id": uuid4(),
            "confirmed_at": "2026-09-02T00:00:00Z",
        }
    )

    assert trusted.field_name == "adjustment_rate"
    assert trusted.confirmed_value == "-12"
    assert trusted.source_page == 3
