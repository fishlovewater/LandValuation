from app.review.trusted_inputs import (
    TrustedField,
    required_field_problems,
    trusted_fields_by_code,
)


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
