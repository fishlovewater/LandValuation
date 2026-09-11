from datetime import date, datetime, timezone
from uuid import uuid4

from app.valuation.schemas import CaseCreate, CaseResponse, CaseStatus, CaseUpdate


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
