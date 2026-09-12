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


def test_workbench_detail_keeps_correction_request_after_reload(
    review_client, triaged_case
):
    draft = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={
            "message": "請依確認疑點修正",
            "due_at": triaged_case.future_due_at.isoformat(),
        },
    ).json()

    detail = review_client.get(
        f"/api/v1/review/workbench/cases/{triaged_case.review_id}"
    )

    assert detail.status_code == 200
    requests = detail.json()["correction_requests"]
    assert [item["correction_request_id"] for item in requests] == [
        draft["correction_request_id"]
    ]
    assert requests[0]["status"] == "DRAFT"
    assert [item["finding_id"] for item in requests[0]["items"]] == [
        str(triaged_case.confirmed_finding_id)
    ]


def test_run_report_contains_scoped_correction_snapshot_and_history(
    review_client, triaged_case
):
    draft = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={
            "message": "請依確認疑點修正",
            "due_at": triaged_case.future_due_at.isoformat(),
        },
    ).json()
    sent = review_client.post(
        f"/api/v1/review/correction-requests/{draft['correction_request_id']}/send",
        json={},
    )
    assert sent.status_code == 200

    report = review_client.get(
        f"/api/v1/review/runs/{draft['based_on_validation_run_id']}/report"
    )

    assert report.status_code == 200
    body = report.json()
    assert [item["correction_request_id"] for item in body["correction_requests"]] == [
        draft["correction_request_id"]
    ]
    assert body["correction_requests"][0]["items"][0]["finding_id"] == str(
        triaged_case.confirmed_finding_id
    )
    assert "CORRECTION_SENT" in {
        item["event_type"] for item in body["history"]
    }


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


@pytest.fixture
def sent_request(review_client, triaged_case):
    draft = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={"message": "請修正", "due_at": triaged_case.future_due_at.isoformat()},
    ).json()
    request_id = draft["correction_request_id"]
    sent = review_client.post(
        f"/api/v1/review/correction-requests/{request_id}/send", json={}
    ).json()
    return SimpleNamespace(
        id=request_id,
        review_id=triaged_case.review_id,
        base_document_id=sent["base_document_id"],
        base_document_version=sent["base_document_version"],
    )


def test_resubmission_rejects_other_case_document(review_client, sent_request):
    response = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/resubmissions",
        json={"document_id": str(uuid4()), "document_version": 2},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CORRECTION_RESUBMISSION_INVALID"


def test_resubmission_rejects_equal_or_older_version(review_client, sent_request):
    response = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/resubmissions",
        json={
            "document_id": sent_request.base_document_id,
            "document_version": sent_request.base_document_version,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CORRECTION_RESUBMISSION_INVALID"


def test_full_resubmit_recheck_complete_flow(
    review_client, sent_request, workflow_data, postgres_connection
):
    # Register a genuine same-lineage newer version, recheck, then complete.
    add_complete_inputs(postgres_connection, workflow_data, version=2)
    resubmitted = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/resubmissions",
        json={
            "document_id": str(workflow_data.v2_document_id),
            "document_version": 2,
        },
    )
    assert resubmitted.status_code == 201
    assert resubmitted.json()["status"] == "RESUBMITTED"
    assert resubmitted.json()["response_document_version"] == 2

    rechecked = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/recheck"
    )
    assert rechecked.status_code == 200
    body = rechecked.json()
    assert body["status"] == "RECHECKED"
    assert {item["recheck_outcome"] for item in body["items"]} <= {
        "RESOLVED",
        "STILL_PRESENT",
    }


def test_duplicate_resubmission_is_rejected(
    review_client, sent_request, workflow_data, postgres_connection
):
    add_complete_inputs(postgres_connection, workflow_data, version=2)
    first = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/resubmissions",
        json={"document_id": str(workflow_data.v2_document_id), "document_version": 2},
    )
    assert first.status_code == 201
    second = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/resubmissions",
        json={"document_id": str(workflow_data.v2_document_id), "document_version": 2},
    )
    assert second.status_code == 409


def test_incomplete_recheck_persists_missing_items_without_creating_run(
    review_client, sent_request, workflow_data, postgres_connection
):
    add_complete_inputs(postgres_connection, workflow_data, version=2)
    registered = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/resubmissions",
        json={
            "document_id": str(workflow_data.v2_document_id),
            "document_version": 2,
        },
    )
    assert registered.status_code == 201

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.document_extractions
            SET extraction_status = 'PROCESSING', completed_at = NULL
            WHERE document_id = %s
            """,
            (workflow_data.v2_document_id,),
        )
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
            (sent_request.review_id,),
        )
        before_runs = cursor.fetchone()[0]
    postgres_connection.commit()

    blocked = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/recheck"
    )

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CORRECTION_RECHECK_INCOMPLETE"
    request = review_client.get(
        f"/api/v1/review/correction-requests/{sent_request.id}"
    ).json()
    assert request["status"] == "RESUBMITTED"
    missing = review_client.get(
        f"/api/v1/review/cases/{sent_request.review_id}/missing-items"
    ).json()
    assert missing
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
            (sent_request.review_id,),
        )
        assert cursor.fetchone()[0] == before_runs


def test_completion_rejects_returned_for_revision_until_recheck(
    review_client, sent_request
):
    response = review_client.post(
        f"/api/v1/review/cases/{sent_request.review_id}/complete-review",
        json={"reason": "嘗試完成"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEW_STATE_CONFLICT"
    assert response.json()["error"]["details"]["current"] == "RETURNED_FOR_REVISION"


def test_legacy_case_decision_route_is_disabled(review_client, triaged_case):
    for decision in ("RETURNED_FOR_REVISION", "APPROVED", "REVIEW_COMPLETED"):
        response = review_client.post(
            f"/api/v1/review/cases/{triaged_case.review_id}/decision",
            json={"decision": decision, "reason": "legacy"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "LEGACY_CASE_DECISION_DISABLED"


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
