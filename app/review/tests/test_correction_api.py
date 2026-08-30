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


@pytest.fixture
def triaged_case(review_client, review_with_findings):
    """Confirm the HIGH finding and dismiss the rest so the send gate passes."""
    review_id = review_with_findings.review_id
    confirmed_finding_id = None
    for finding in review_with_findings.findings:
        if finding["severity"] == "HIGH" and confirmed_finding_id is None:
            decision = "CONFIRMED_ISSUE"
            confirmed_finding_id = finding["finding_id"]
        else:
            decision = "DISMISSED_FALSE_POSITIVE"
        response = review_client.post(
            f"/api/v1/review/findings/{finding['finding_id']}/triage",
            json={
                "review_id": str(review_id),
                "decision": decision,
                "reason": "判定理由",
            },
        )
        assert response.status_code == 201
    return SimpleNamespace(
        review_id=review_id,
        confirmed_finding_id=confirmed_finding_id,
        future_due_at=_future_due_at(),
    )


def _future_due_at():
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC) + timedelta(days=5)


def test_create_draft_snapshots_only_confirmed_findings(review_client, triaged_case):
    response = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={
            "message": "請依附件疑點修正",
            "due_at": triaged_case.future_due_at.isoformat(),
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert {item["finding_id"] for item in body["items"]} == {
        str(triaged_case.confirmed_finding_id)
    }
    assert body["status"] == "DRAFT"
    assert body["request_no"] == 1
    # No storage internals leaked.
    assert "bucket_name" not in body
    assert "object_key" not in body


def test_send_locks_request_and_returns_case_for_revision(review_client, triaged_case):
    draft = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={
            "message": "請修正",
            "due_at": triaged_case.future_due_at.isoformat(),
        },
    ).json()
    request_id = draft["correction_request_id"]
    sent = review_client.post(
        f"/api/v1/review/correction-requests/{request_id}/send", json={}
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "SENT"
    review = review_client.get(
        f"/api/v1/review/cases/{triaged_case.review_id}"
    ).json()
    assert review["review_status"] == "RETURNED_FOR_REVISION"


def test_second_active_request_is_blocked(review_client, triaged_case):
    first = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={"message": "第一次", "due_at": triaged_case.future_due_at.isoformat()},
    )
    assert first.status_code == 201
    second = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={"message": "第二次", "due_at": triaged_case.future_due_at.isoformat()},
    )
    assert second.status_code == 409


def test_send_gate_blocks_when_findings_untriaged(review_client, review_with_findings):
    response = review_client.post(
        f"/api/v1/review/cases/{review_with_findings.review_id}/correction-requests",
        json={
            "message": "尚未判定",
            "due_at": _future_due_at().isoformat(),
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CORRECTION_REQUEST_BLOCKED"


def test_get_correction_request_returns_immutable_snapshot(
    review_client, triaged_case
):
    draft = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={"message": "請修正", "due_at": triaged_case.future_due_at.isoformat()},
    ).json()
    request_id = draft["correction_request_id"]
    review_client.post(f"/api/v1/review/correction-requests/{request_id}/send", json={})
    fetched = review_client.get(
        f"/api/v1/review/correction-requests/{request_id}"
    ).json()
    assert fetched["status"] == "SENT"
    assert {item["finding_id"] for item in fetched["items"]} == {
        str(triaged_case.confirmed_finding_id)
    }


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
