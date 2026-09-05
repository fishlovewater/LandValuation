from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.core.exceptions import PermissionDeniedError
from app.main import app
from app.valuation.submissions.schemas import ValuationReviewHandoffRead
from app.valuation.submissions.handoff_service import ValuationReviewHandoffService


class _ScalarRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, *, scalar_values=(), rows=()):
        self.scalar_values = list(scalar_values)
        self.rows = list(rows)
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0)

    async def scalars(self, statement):
        self.statements.append(statement)
        return _ScalarRows(self.rows.pop(0))


def _actor(user_id=None, permissions=("case.read",)):
    role = SimpleNamespace(
        role_code="APPRAISER",
        is_active=True,
        permissions=[
            SimpleNamespace(permission_code=permission)
            for permission in permissions
        ],
    )
    return SimpleNamespace(user_id=user_id or uuid4(), roles=[role])


def _records(*, correction_status="SENT", include_review=True, include_submission=True):
    owner = _actor()
    case = SimpleNamespace(
        case_id=uuid4(),
        created_by_user_id=owner.user_id,
        case_status="REVISION_REQUIRED",
    )
    if not include_review:
        return owner, case, _Session(scalar_values=(case, None))

    review = SimpleNamespace(
        review_id=uuid4(),
        case_id=case.case_id,
        review_status="REVIEW_REQUIRED",
        latest_submission_id=uuid4() if include_submission else None,
    )
    submission = (
        SimpleNamespace(
            submission_id=review.latest_submission_id,
            review_id=review.review_id,
            case_id=case.case_id,
            submission_no=1,
            submitted_at=datetime(2026, 9, 5, 1, 2, 3, tzinfo=UTC),
            input_snapshot={"object_key": "must-never-leak"},
        )
        if include_submission
        else None
    )
    request = SimpleNamespace(
        correction_request_id=uuid4(),
        request_no=1,
        status=correction_status,
        due_at=datetime(2026, 9, 10, tzinfo=UTC),
        message="請修正價格日期並補上謄本",
    )
    item = SimpleNamespace(
        finding_code="PRICE_DATE",
        severity="HIGH",
        document_id=uuid4(),
        page_number=3,
        issue_summary="價格日期與來源文件不一致",
        requested_correction="更正價格日期",
        legal_basis_snapshot=[{"secret": "do-not-expose"}],
        source_evidence_snapshot=[{"object_key": "do-not-expose"}],
    )
    missing = SimpleNamespace(
        item_code="LAND_REGISTER",
        item_name="土地登記謄本",
        document_type="land-register",
        severity="HIGH",
        reason="必要文件尚未提供",
        due_at=datetime(2026, 9, 10, tzinfo=UTC),
    )
    rows = ((missing,),)
    if correction_status in {"SENT", "RESUBMITTED"}:
        rows = ((item,), (missing,))
    return owner, case, _Session(
        scalar_values=(case, review, submission, request),
        rows=rows,
    )


@pytest.mark.asyncio
async def test_handoff_status_returns_only_appraiser_safe_correction_data():
    owner, case, session = _records()

    result = await ValuationReviewHandoffService(session).get(case.case_id, owner)

    assert result.case_status == "REVISION_REQUIRED"
    assert result.display_status == "退回補正"
    assert result.latest_submission.submission_no == 1
    assert result.correction.message == "請修正價格日期並補上謄本"
    assert result.correction.items[0].requested_correction == "更正價格日期"
    assert result.missing_items[0].item_name == "土地登記謄本"
    body = result.model_dump(mode="json")
    serialized = str(body)
    assert "input_snapshot" not in serialized
    assert "object_key" not in serialized
    assert "bucket_name" not in serialized
    assert "legal_basis_snapshot" not in serialized
    assert "source_evidence_snapshot" not in serialized


@pytest.mark.asyncio
async def test_handoff_status_without_review_is_a_safe_empty_projection():
    owner, case, session = _records(include_review=False)

    result = await ValuationReviewHandoffService(session).get(case.case_id, owner)

    assert result.case_id == case.case_id
    assert result.case_status == "REVISION_REQUIRED"
    assert result.display_status == "退回補正"
    assert result.review_id is None
    assert result.review_status is None
    assert result.latest_submission is None
    assert result.correction is None
    assert result.missing_items == []


@pytest.mark.asyncio
async def test_handoff_status_rejects_another_appraisers_case():
    owner, case, session = _records()
    other_appraiser = _actor()

    with pytest.raises(PermissionDeniedError) as raised:
        await ValuationReviewHandoffService(session).get(case.case_id, other_appraiser)

    assert raised.value.status_code == 403
    assert str(raised.value) == "只能查看自己建立的估價案件"
    assert owner.user_id != other_appraiser.user_id


@pytest.mark.asyncio
async def test_handoff_status_hides_draft_correction():
    owner, case, session = _records(correction_status="DRAFT")

    result = await ValuationReviewHandoffService(session).get(case.case_id, owner)

    assert result.correction is None
    assert result.missing_items[0].item_code == "LAND_REGISTER"


@pytest.mark.asyncio
async def test_latest_submission_query_is_scoped_to_review_and_case():
    owner, case, session = _records()

    await ValuationReviewHandoffService(session).get(case.case_id, owner)

    submission_query = str(session.statements[2])
    assert "review_submissions.review_id" in submission_query
    assert "review_submissions.case_id" in submission_query


@pytest.mark.asyncio
async def test_handoff_status_accepts_resubmitted_correction():
    owner, case, session = _records(correction_status="RESUBMITTED")

    result = await ValuationReviewHandoffService(session).get(case.case_id, owner)

    assert result.correction.status == "RESUBMITTED"


def _http_user(permissions=()):
    return _actor(permissions=permissions)


def test_handoff_route_allows_case_reader(monkeypatch):
    case_id = uuid4()
    expected = ValuationReviewHandoffRead(
        case_id=case_id,
        case_status="PROCESSING",
        display_status="製作中",
        review_id=None,
        review_status=None,
        latest_submission=None,
        correction=None,
        missing_items=[],
    )
    captured = {}

    async def get(_self, requested_case_id, actor):
        captured.update(case_id=requested_case_id, actor=actor)
        return expected

    monkeypatch.setattr(ValuationReviewHandoffService, "get", get)
    reader = _http_user(("case.read",))
    app.dependency_overrides[get_current_user] = lambda: reader
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/valuation/cases/{case_id}/review-handoff"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["display_status"] == "製作中"
    assert captured["case_id"] == case_id
    assert captured["actor"] is reader


def test_handoff_route_requires_case_read_permission():
    app.dependency_overrides[get_current_user] = lambda: _http_user()
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/valuation/cases/{uuid4()}/review-handoff"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
