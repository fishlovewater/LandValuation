import asyncio
from uuid import uuid4

from app.review.repository import ReviewRepository
from app.review.trusted_inputs import (
    TrustedField,
    required_field_problems,
    trusted_fields_by_code,
)
import pytest


def field(code, status="VERIFIED", official=True):
    return TrustedField(
        extracted_field_id="field-1",
        field_code=code,
        field_path=code,
        raw_text="來源原文",
        normalized_value="-12",
        value_type="DECIMAL",
        page_number=3,
        bounding_box=None,
        confidence=None,
        verification_status=status,
        verified_by_user_id=None,
        verified_at=None,
        is_official=official,
    )


def test_high_impact_field_requires_verified_official_value():
    fields = trusted_fields_by_code([field("adjustment_rate", "AUTO_EXTRACTED")])
    problems = required_field_problems({"adjustment_rate"}, fields)
    assert problems[0].code == "TRUSTED_INPUT_UNVERIFIED"


def test_low_impact_field_accepts_auto_extracted_official_value():
    fields = trusted_fields_by_code([field("property_description", "AUTO_EXTRACTED")])
    assert required_field_problems({"property_description"}, fields) == ()


def test_rejected_or_nonofficial_field_is_missing():
    fields = trusted_fields_by_code([field("adjustment_rate", "REJECTED", False)])
    assert required_field_problems({"adjustment_rate"}, fields)[0].code == "TRUSTED_INPUT_MISSING"


def test_unknown_low_impact_status_is_unverified():
    fields = trusted_fields_by_code([field("property_description", "PENDING")])
    problems = required_field_problems({"property_description"}, fields)
    assert problems[0].code == "TRUSTED_INPUT_UNVERIFIED"


def test_rejected_official_field_is_missing():
    fields = trusted_fields_by_code([field("adjustment_rate", "REJECTED")])
    assert required_field_problems({"adjustment_rate"}, fields)[0].code == "TRUSTED_INPUT_MISSING"


def test_verified_nonofficial_field_is_missing():
    fields = trusted_fields_by_code([field("adjustment_rate", "VERIFIED", False)])
    assert required_field_problems({"adjustment_rate"}, fields)[0].code == "TRUSTED_INPUT_MISSING"


@pytest.mark.parametrize("ordered_fields", [
    [field("adjustment_rate", "VERIFIED"), field("adjustment_rate", "REJECTED")],
    [field("adjustment_rate", "REJECTED"), field("adjustment_rate", "VERIFIED")],
])
def test_duplicate_official_fields_are_missing_in_either_input_order(ordered_fields):
    fields = trusted_fields_by_code(ordered_fields)
    assert required_field_problems({"adjustment_rate"}, fields)[0].code == "TRUSTED_INPUT_MISSING"


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
