from datetime import date
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.valuation.official_forms import (
    FORMULA_POLICY,
    OFFICIAL_FORM_TEMPLATES,
    OFFICIAL_SCHEMA_VERSION,
    blank_form_content,
    template_contract,
)
from app.valuation.schemas import FormCode, FormCreate
from app.valuation.service import ValuationService

from tests.test_valuation_service import FakeRepository, case_record, user_with_role


def test_all_official_form_codes_have_blank_contracts() -> None:
    assert set(OFFICIAL_FORM_TEMPLATES) == {
        "S01",
        "F01",
        "F02",
        "F02-RF",
        "F03",
        "F04",
    }
    for code in OFFICIAL_FORM_TEMPLATES:
        contract = template_contract(code)
        blank = blank_form_content(code)
        assert contract["schema_version"] == OFFICIAL_SCHEMA_VERSION
        assert blank["schema_version"] == OFFICIAL_SCHEMA_VERSION
        assert blank["form_code"] == code
        declared = {
            field["code"]
            for section in contract["sections"]
            for field in section["fields"]
        }
        assert set(blank["data"]) == declared
        for calculated in contract["calculated_fields"]:
            assert blank["data"][calculated] in (None, {})


def test_formula_policy_prevents_example_values_becoming_rules() -> None:
    assert FORMULA_POLICY["formula_code"] == "NTPC_COMPARISON_V1"
    assert "範例數值不得成為正式規則" in FORMULA_POLICY["safety"]
    assert "F02.trial_price" in FORMULA_POLICY["formulas"]
    assert "F03.benchmark_land_price" in FORMULA_POLICY["formulas"]
    assert "F04.parcel_total_value" in FORMULA_POLICY["formulas"]


@pytest.mark.asyncio
async def test_generic_form_creation_starts_from_official_blank_structure() -> None:
    user = user_with_role()
    case = case_record(user.user_id)
    repository = FakeRepository(case)
    service = ValuationService(None, repository=repository)

    record = await service.create_form(
        case.case_id,
        FormCreate(form_code=FormCode.F01, prepared_date=date(2026, 8, 29)),
        user,
    )

    assert record.form_content["schema_version"] == OFFICIAL_SCHEMA_VERSION
    assert record.form_content["form_code"] == "F01"
    assert record.form_content["data"]["transaction_no"] is None
    assert record.form_content["data"]["normal_land_unit_price"] is None


@pytest.mark.asyncio
async def test_generic_form_creation_rejects_prefilled_payload() -> None:
    user = user_with_role()
    case = case_record(user.user_id)
    service = ValuationService(None, repository=FakeRepository(case))

    with pytest.raises(AppError) as raised:
        await service.create_form(
            case.case_id,
            FormCreate(form_code=FormCode.F04, form_content={"parcel_unit_price": 1}),
            user,
        )

    assert raised.value.code == "FORM_CREATE_MUST_START_BLANK"
