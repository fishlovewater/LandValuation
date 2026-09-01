from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.valuation.schemas import (
    CaseUpdate,
    FormCode,
    FormDraftUpdate,
    ParcelCreate,
    ParcelUpdate,
)
from app.valuation.service import ValuationService


def test_f03_requirements_match_backend_guide() -> None:
    requirement = ValuationService.form_requirement(FormCode.F03)

    assert requirement.required_fields == ["valuation_base_date", "benchmark_land_id"]
    assert requirement.required_documents == ["land-register", "cadastral-map"]
    assert requirement.optional_documents == ["photos", "attachments"]
    assert requirement.calculated_fields == [
        "adjusted_unit_price",
        "benchmark_land_price",
    ]


def test_undefined_document_requirements_are_not_guessed() -> None:
    requirements = {
        item.form_type: item for item in ValuationService.form_requirements()
    }

    for form_code in ("F01", "F02", "F04"):
        assert requirements[form_code].required_documents == []
        assert requirements[form_code].optional_documents == []


def test_complete_report_form_codes_and_requirements_are_available() -> None:
    assert FormCode.S01.value == "S01"
    assert FormCode.F02_RF.value == "F02-RF"

    s01 = ValuationService.form_requirement(FormCode.S01)
    f02_rf = ValuationService.form_requirement(FormCode.F02_RF)
    assert s01.form_name == "地價區段勘查表"
    assert "zone_boundary_description" in s01.required_fields
    assert f02_rf.form_name == "影響地價區域因素分析明細表（商業用地）"
    assert "confirmed_factor_levels" in f02_rf.required_fields


def test_form_content_cannot_be_cleared_to_null() -> None:
    with pytest.raises(ValidationError, match="表單內容不可設為 null"):
        FormDraftUpdate(form_content=None)


def test_case_update_rejects_null_for_required_field() -> None:
    with pytest.raises(ValidationError, match="案件必填欄位不可設為 null"):
        CaseUpdate(case_title=None)


def test_parcel_create_preserves_decimal_and_validates_ownership() -> None:
    payload = ParcelCreate(
        district_code="D01",
        section_name="S01",
        land_no="100",
        area_sqm="123.4567",
        ownership_numerator="1",
        ownership_denominator="2",
    )

    assert payload.area_sqm == Decimal("123.4567")
    assert payload.ownership_numerator == Decimal("1")


def test_parcel_create_rejects_partial_ownership() -> None:
    with pytest.raises(ValidationError, match="權利分子與分母必須同時提供"):
        ParcelCreate(
            district_code="D01",
            section_name="S01",
            land_no="100",
            area_sqm="123.4567",
            ownership_numerator="1",
        )


def test_parcel_update_rejects_mixed_clear_and_value() -> None:
    with pytest.raises(ValidationError, match="必須同時提供或同時清除"):
        ParcelUpdate(
            ownership_numerator=None,
            ownership_denominator="2",
        )
