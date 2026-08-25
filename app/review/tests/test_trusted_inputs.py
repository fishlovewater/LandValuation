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
        verification_status=status,
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
