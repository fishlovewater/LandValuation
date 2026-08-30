"""HTTP contract and authorization tests for the correction workflow.

Reuses the trusted end-to-end seeding helpers from test_workflow_e2e so that
findings come from the real run pipeline rather than hand-inserted rows.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app
from app.review.tests.test_workflow_e2e import (  # noqa: F401
    add_complete_inputs,
    workflow_data,
)


@pytest.fixture
def review_client(workflow_data):  # noqa: F811
    permissions = [
        SimpleNamespace(permission_code=code)
        for code in ("review.execute", "review.decide", "review.override_high_risk")
    ]
    user = SimpleNamespace(
        user_id=workflow_data.user_id,
        roles=[
            SimpleNamespace(
                role_code="SUPERVISOR", is_active=True, permissions=permissions
            )
        ],
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def review_with_findings(review_client, workflow_data, postgres_connection):
    """Create a case, run the pipeline, and return (review_id, findings)."""
    created = review_client.post(
        "/api/v1/review/cases", json={"case_id": str(workflow_data.case_id)}
    )
    assert created.status_code == 201
    review_id = created.json()["review_id"]
    review_client.post(f"/api/v1/review/cases/{review_id}/completeness-check")
    add_complete_inputs(postgres_connection, workflow_data)
    review_client.post(f"/api/v1/review/cases/{review_id}/completeness-check")
    run = review_client.post(
        f"/api/v1/review/cases/{review_id}/runs", json={}
    ).json()
    findings = review_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    ).json()
    return SimpleNamespace(review_id=review_id, findings=findings)


@pytest.fixture
def open_finding(review_with_findings):
    finding = next(
        item for item in review_with_findings.findings if item["severity"] == "HIGH"
    )
    return SimpleNamespace(
        finding_id=finding["finding_id"],
        review_id=review_with_findings.review_id,
    )


def test_triage_confirmed_issue_writes_no_formal_value(review_client, open_finding):
    response = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "CONFIRMED_ISSUE",
            "reason": "與適用規則不一致",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "CONFIRMED_ISSUE"
    assert body["after_value"] == {"status": "CONFIRMED_ISSUE"}
    assert "value" not in body["after_value"]


def test_triage_route_rejects_after_value(review_client, open_finding):
    response = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "CONFIRMED_ISSUE",
            "reason": "x",
            "after_value": {"value": "45000"},
        },
    )
    assert response.status_code == 422


def test_dismissed_false_positive_excluded_from_risk_counts(
    review_client, open_finding
):
    review = review_client.get(
        f"/api/v1/review/cases/{open_finding.review_id}"
    ).json()
    assert review["high_count"] >= 1
    response = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "DISMISSED_FALSE_POSITIVE",
            "reason": "屬誤判",
        },
    )
    assert response.status_code == 201
    review_after = review_client.get(
        f"/api/v1/review/cases/{open_finding.review_id}"
    ).json()
    assert review_after["high_count"] == review["high_count"] - 1


def test_confirmed_issue_still_counts_as_unresolved(review_client, open_finding):
    review = review_client.get(
        f"/api/v1/review/cases/{open_finding.review_id}"
    ).json()
    before = review["high_count"]
    review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "CONFIRMED_ISSUE",
            "reason": "確認成立",
        },
    )
    review_after = review_client.get(
        f"/api/v1/review/cases/{open_finding.review_id}"
    ).json()
    assert review_after["high_count"] == before


def test_duplicate_triage_returns_conflict(review_client, open_finding):
    first = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "CONFIRMED_ISSUE",
            "reason": "確認成立",
        },
    )
    assert first.status_code == 201
    second = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "DISMISSED_FALSE_POSITIVE",
            "reason": "改判",
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "FINDING_DECISION_CONFLICT"


def test_triage_rejects_cross_review_finding(review_client, open_finding):
    response = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(uuid4()),
            "decision": "CONFIRMED_ISSUE",
            "reason": "x",
        },
    )
    assert response.status_code in (404, 409)


def test_legacy_decisions_write_route_is_disabled(review_client, open_finding):
    response = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/decisions",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "ACCEPTED",
            "reason": "legacy",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LEGACY_FINDING_DECISION_DISABLED"
