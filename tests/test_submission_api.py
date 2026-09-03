from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.service import permission_codes
from app.main import app
from app.valuation.submissions.service import SubmissionService


def user_with_role(role_code, permissions=()):
    role = SimpleNamespace(
        role_code=role_code,
        is_active=True,
        permissions=[
            SimpleNamespace(permission_code=permission_code)
            for permission_code in permissions
        ],
    )
    return SimpleNamespace(user_id=uuid4(), roles=[role])


def payload():
    return {
        "request_id": str(uuid4()),
        "expected_case_version": 1,
        "source_validation_run_id": str(uuid4()),
        "source_report_document_id": str(uuid4()),
    }


def test_submit_permission_is_association_based_not_role_name_based() -> None:
    appraiser = user_with_role("APPRAISER", ("valuation.submit_review",))
    appraiser_without_grant = user_with_role("APPRAISER")
    reviewer = user_with_role("REVIEWER", ("review.execute", "review.decide"))

    assert "valuation.submit_review" in permission_codes(appraiser)
    assert "valuation.submit_review" not in permission_codes(appraiser_without_grant)
    assert "valuation.submit_review" not in permission_codes(reviewer)


def test_submit_route_creates_submission_for_appraiser(monkeypatch) -> None:
    case_id = uuid4()
    expected = {
        "submission_id": uuid4(),
        "submission_no": 1,
        "review_id": uuid4(),
        "case_status": "IN_REVIEW",
        "submitted_at": datetime(2026, 9, 3, tzinfo=UTC),
    }
    captured = {}

    async def submit(_self, submitted_case_id, command, actor):
        captured.update(case_id=submitted_case_id, command=command, actor=actor)
        return expected

    monkeypatch.setattr(SubmissionService, "submit", submit)
    appraiser = user_with_role("APPRAISER", ("valuation.submit_review",))
    app.dependency_overrides[get_current_user] = lambda: appraiser
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/valuation/cases/{case_id}/submit-for-review",
                json=payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["submission_id"] == str(expected["submission_id"])
    assert captured["case_id"] == case_id
    assert captured["actor"] is appraiser


def test_submit_route_forbids_review_only_user() -> None:
    reviewer = user_with_role("REVIEWER", ("review.execute", "review.decide"))
    app.dependency_overrides[get_current_user] = lambda: reviewer
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/valuation/cases/{uuid4()}/submit-for-review",
                json=payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_submit_route_rejects_client_owned_snapshot() -> None:
    appraiser = user_with_role("APPRAISER", ("valuation.submit_review",))
    app.dependency_overrides[get_current_user] = lambda: appraiser
    forged = {**payload(), "snapshot": {"applied_fields": []}}
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/valuation/cases/{uuid4()}/submit-for-review",
                json=forged,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
