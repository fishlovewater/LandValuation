from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.review import auto_fill
from tests.test_review_intake_fix import candidate, forms  # Shared isolated form repository.
from app.review.intake_forms import fill_review_form


def source(**updates):
    return candidate(extracted_value="123.25", confidence="0.99", source_page=1,
                     source_text="土地面積 123.25", extraction_id=uuid4(),
                     **updates)


@pytest.mark.parametrize("changes", [
    {"confidence": "0.9"}, {"confidence": "NaN"}, {"source_page": None},
    {"source_text": "別的數字 999"}, {"extracted_value": "bad"},
    {"field_name": "comparison_weight"},
])
def test_uncertain_fields_remain_for_human_review(changes):
    field = source()
    for key, value in changes.items():
        setattr(field, key, value)
    assert auto_fill.uncertainty_reasons(field, [field])


def test_conflicting_values_require_review():
    one, two = source(), source()
    two.extracted_value = "124"
    assert "同名欄位的辨識值不一致" in auto_fill.uncertainty_reasons(one, [one, two])


@pytest.mark.asyncio
async def test_auto_fill_has_no_fabricated_human_confirmation(forms):
    field = source()
    field.confirmed_by_user_id = field.confirmed_at = field.confirmed_value = None
    field.field_status = "NEEDS_CONFIRMATION"
    extraction = SimpleNamespace(extraction_metadata={})
    await auto_fill.apply_unambiguous_fields(SimpleNamespace(flush=AsyncMock()), extraction, [field], SimpleNamespace(user_id=uuid4()))
    assert field.field_status == "AUTO_APPLIED"
    assert field.confirmed_by_user_id is None and field.confirmed_at is None
    assert field.applied_form_instance_id == forms[0][0].form_instance_id
    assert forms[0][0].form_content["review_fields"]["land_area"]["origin"] == "AUTO"


@pytest.mark.asyncio
@pytest.mark.parametrize("code,name,value", [
    ("F01", "land_area", "123"), ("F02", "comparison_targets", [{"land_no": "1"}]),
    ("F02-RF", "factor_rows", [{"factor": "road"}]), ("F03", "land_no", "123-1"),
    ("F04", "parcel_rows", [{"land_no": "123-1"}]), ("S01", "survey_date", "2026-09-13"),
])
async def test_all_form_families_store_confirmed_source_fields(forms, code, name, value):
    field = candidate(form_code=code, field_name=name, confirmed_value=value)
    await fill_review_form(None, field, SimpleNamespace(user_id=uuid4()))
    assert field.field_status == "APPLIED"
    assert forms[0][0].form_content["review_fields"][name]["value"] == value


@pytest.mark.asyncio
async def test_new_extraction_creates_new_form_without_copying_old_values(forms):
    old = source()
    await fill_review_form(None, old, SimpleNamespace(user_id=uuid4()))
    new = source()
    new.case_id, new.document_id = old.case_id, old.document_id
    new.confirmed_value = "150"
    await fill_review_form(None, new, SimpleNamespace(user_id=uuid4()))
    assert len(forms[0]) == 2
    assert forms[0][0].form_content["data"]["land_area_sqm"] == "123.25"
    assert forms[0][1].form_content["data"]["land_area_sqm"] == "150"
