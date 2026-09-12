from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.valuation.schemas import CaseCreate, CaseResponse, CaseStatus, CaseUpdate, FormCode
from app.valuation.service import ValuationService


def test_case_create_and_response_keep_optional_valuation_due_date() -> None:
    payload = CaseCreate(
        case_no="VAL-2026-001",
        case_title="期限測試案件",
        case_type="LAND",
        valuation_base_date=date(2026, 9, 8),
        valuation_due_date=date(2026, 9, 30),
        city_code="65000",
        district_code="65000010",
    )
    assert payload.valuation_due_date == date(2026, 9, 30)

    response = CaseResponse(
        case_id=uuid4(),
        case_no=payload.case_no,
        case_title=payload.case_title,
        case_type=payload.case_type,
        requesting_agency=None,
        valuation_base_date=payload.valuation_base_date,
        valuation_due_date=payload.valuation_due_date,
        city_code=payload.city_code,
        district_code=payload.district_code,
        land_use_type=None,
        case_status=CaseStatus.PROCESSING,
        created_by_user_id=None,
        updated_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert response.valuation_due_date == date(2026, 9, 30)


def test_case_deadline_remains_optional_and_can_be_cleared() -> None:
    create_payload = CaseCreate(
        case_no="VAL-2026-002",
        case_title="無期限案件",
        case_type="LAND",
        valuation_base_date=date(2026, 9, 8),
        city_code="65000",
        district_code="65000010",
    )
    assert create_payload.valuation_due_date is None

    update_payload = CaseUpdate(valuation_due_date=None)
    assert update_payload.model_fields_set == {"valuation_due_date"}
    assert update_payload.valuation_due_date is None


@pytest.mark.parametrize(
    "case_type",
    [
        "LAND",
        "land",
        "LAND_VALUATION",
        "LAND_ACQUISITION",
        "土地徵收補償市價查估",
        "土地徵收補償市價查估案件",
    ],
)
def test_case_type_aliases_are_normalized_to_land(case_type: str) -> None:
    payload = CaseCreate(
        case_no="VAL-2026-TYPE",
        case_title="案件類型正規化測試",
        case_type=case_type,
        valuation_base_date=date(2026, 9, 12),
        city_code="65000000",
        district_code="65000010",
    )

    assert payload.case_type == "LAND"
    assert CaseUpdate(case_type=case_type).case_type == "LAND"


def test_case_type_rejects_values_outside_the_supported_valuation_workflow() -> None:
    with pytest.raises(ValidationError, match="案件類型僅支援土地徵收補償市價查估"):
        CaseCreate(
            case_no="VAL-2026-INVALID-TYPE",
            case_title="不支援案件類型",
            case_type="GENERAL_APPRAISAL",
            valuation_base_date=date(2026, 9, 12),
            city_code="65000000",
            district_code="65000010",
        )

    with pytest.raises(ValidationError, match="案件類型僅支援土地徵收補償市價查估"):
        CaseUpdate(case_type="EXTERNAL_REVIEW")


@pytest.mark.asyncio
async def test_case_bootstrap_uses_same_request_to_create_initial_f03() -> None:
    payload = CaseCreate(
        case_no="VAL-2026-BOOTSTRAP",
        case_title="原子建立案件",
        case_type="LAND",
        valuation_base_date=date(2026, 9, 12),
        city_code="65000",
        district_code="65000010",
    )
    user = SimpleNamespace(user_id=uuid4())
    case_id = uuid4()
    form_id = uuid4()
    created_case = SimpleNamespace(case_id=case_id)
    current_case = SimpleNamespace(case_id=case_id, case_status="PROCESSING")
    initial_form = SimpleNamespace(form_instance_id=form_id, form_code="F03")
    calls: list[tuple[str, object]] = []

    async def create_case(value, actor):
        assert value is payload
        assert actor is user
        calls.append(("case", value))
        return created_case

    async def create_form(value_case_id, value, actor):
        assert value_case_id == case_id
        assert actor is user
        calls.append(("form", value))
        return initial_form

    async def get_case(value_case_id, actor):
        assert value_case_id == case_id
        assert actor is user
        return current_case

    service = object.__new__(ValuationService)
    service.create_case = create_case
    service.create_form = create_form
    service.get_case = get_case

    case, form = await service.bootstrap_case(payload, user)

    assert case is current_case
    assert form is initial_form
    assert [name for name, _ in calls] == ["case", "form"]
    form_payload = calls[1][1]
    assert form_payload.form_code == FormCode.F03
    assert form_payload.prepared_date == payload.valuation_base_date
