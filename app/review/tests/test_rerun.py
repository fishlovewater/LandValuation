from uuid import uuid4

from app.review.tests.test_runs_api import (
    authorized_client,
    run_payload,
    runnable_review,
)


def test_finding_and_case_decisions_are_append_only(
    authorized_client, runnable_review, postgres_connection
):
    run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    finding = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    ).json()[0]
    request_id = str(uuid4())

    blocked = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        headers={"X-Request-ID": request_id},
        json={"decision": "APPROVED", "reason": "先嘗試核准"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "REVIEW_DECISION_INVALID"

    decided = authorized_client.post(
        f"/api/v1/review/findings/{finding['finding_id']}/decisions",
        headers={"X-Request-ID": request_id},
        json={
            "review_id": str(runnable_review.review_id),
            "decision": "PARTIALLY_ACCEPTED",
            "reason": "現勘資料支持部分調整",
            "after_value": {"reported_rate": "-7.00"},
        },
    )
    assert decided.status_code == 201
    assert decided.json()["decision"] == "PARTIALLY_ACCEPTED"
    assert decided.json()["request_id"] == request_id

    still_blocked = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "APPROVED", "reason": "部分接受後嘗試核准"},
    )
    assert still_blocked.status_code == 409

    resolved = authorized_client.post(
        f"/api/v1/review/findings/{finding['finding_id']}/decisions",
        json={
            "review_id": str(runnable_review.review_id),
            "decision": "ACCEPTED",
            "reason": "補充證據已確認，疑點完成處理",
        },
    )
    assert resolved.status_code == 201
    current = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()
    assert current["high_count"] == 0
    assert current["current_risk_level"] == "LOW"

    approved = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "APPROVED", "reason": "高風險疑點已完成處理"},
    )
    assert approved.status_code == 201
    assert approved.json()["decision"] == "APPROVED"

    decisions = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}/decisions"
    )
    assert decisions.status_code == 200
    assert len(decisions.json()) == 3

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM review.decisions WHERE review_id = %s",
            (runnable_review.review_id,),
        )
        assert cursor.fetchone()[0] == 3
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_findings WHERE validation_run_id = %s",
            (run["validation_run_id"],),
        )
        assert cursor.fetchone()[0] == 1


def test_rerun_preserves_old_finding_and_links_replacement(
    authorized_client, runnable_review, postgres_connection
):
    first_run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    old_finding = authorized_client.get(
        f"/api/v1/review/runs/{first_run['validation_run_id']}/findings"
    ).json()[0]
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE review.reviews SET review_status = 'READY_FOR_REVIEW' WHERE review_id = %s",
            (runnable_review.review_id,),
        )
    postgres_connection.commit()
    rerun = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/rerun", json={}
    )

    assert rerun.status_code == 202
    assert rerun.json()["run_no"] == 2
    new_findings = authorized_client.get(
        f"/api/v1/review/runs/{rerun.json()['validation_run_id']}/findings"
    ).json()
    assert new_findings[0]["supersedes_finding_id"] == old_finding["finding_id"]
    old_still_exists = authorized_client.get(
        f"/api/v1/review/findings/{old_finding['finding_id']}"
    )
    assert old_still_exists.status_code == 200
    runs = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs"
    )
    assert [item["run_no"] for item in runs.json()] == [1, 2]


def test_generic_update_cannot_bypass_decision_gate(
    authorized_client, runnable_review
):
    authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    )

    response = authorized_client.patch(
        f"/api/v1/review/cases/{runnable_review.review_id}",
        json={"review_status": "APPROVED"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEW_DECISION_INVALID"
    review = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()
    assert review["review_status"] == "REVIEW_REQUIRED"
    decisions = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}/decisions"
    ).json()
    assert decisions == []


def test_superseded_run_high_finding_does_not_block_current_clean_run(
    authorized_client, runnable_review, postgres_connection
):
    first_run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    assert authorized_client.get(
        f"/api/v1/review/runs/{first_run['validation_run_id']}/findings"
    ).json()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE review.reviews SET review_status = 'READY_FOR_REVIEW' "
            "WHERE review_id = %s",
            (runnable_review.review_id,),
        )
    postgres_connection.commit()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET normalized_value = '"-5"'::jsonb, raw_text = '調整率 -5%%'
            WHERE extraction_run_id = %s AND field_code = 'adjustment_rate'
            """,
            (runnable_review.extraction_run_id,),
        )
    postgres_connection.commit()

    rerun = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/rerun",
        json={},
    )

    assert rerun.status_code == 202
    assert authorized_client.get(
        f"/api/v1/review/runs/{rerun.json()['validation_run_id']}/findings"
    ).json() == []
    approved = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "APPROVED", "reason": "目前批次已無高風險疑點"},
    )
    assert approved.status_code == 201


def test_rerun_rejects_caller_owned_authoritative_values(
    authorized_client, runnable_review
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/rerun",
        json={"rule_version_id": str(uuid4())},
    )

    assert response.status_code == 422


def test_rate_finding_remains_high_gate_when_rule_severity_is_too_low(
    authorized_client, runnable_review, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE valuation.validation_rules SET severity = 'LOW' "
            "WHERE validation_rule_id = %s",
            (runnable_review.validation_rule_id,),
        )
    postgres_connection.commit()
    run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    finding = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    ).json()[0]
    decided = authorized_client.post(
        f"/api/v1/review/findings/{finding['finding_id']}/decisions",
        json={
            "review_id": str(runnable_review.review_id),
            "decision": "PARTIALLY_ACCEPTED",
            "reason": "仍需確認部分差異",
            "after_value": {"reported_rate": "-7"},
        },
    )
    assert decided.status_code == 201
    review = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()
    assert review["current_risk_level"] == "HIGH"
    assert review["high_count"] == 1

    approved = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "APPROVED", "reason": "嘗試忽略風險"},
    )

    assert approved.status_code == 409


def test_completed_case_rejects_late_finding_decision(
    authorized_client, runnable_review
):
    run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    finding = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    ).json()[0]
    assert authorized_client.post(
        f"/api/v1/review/findings/{finding['finding_id']}/decisions",
        json={
            "review_id": str(runnable_review.review_id),
            "decision": "ACCEPTED",
            "reason": "疑點已完成處理",
        },
    ).status_code == 201
    assert authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "APPROVED", "reason": "准予核定"},
    ).status_code == 201
    completed = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "REVIEW_COMPLETED", "reason": "審查程序完成"},
    )
    assert completed.status_code == 201
    assert authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}"
    ).json()["review_status"] == "REVIEW_COMPLETED"

    late_decision = authorized_client.post(
        f"/api/v1/review/findings/{finding['finding_id']}/decisions",
        json={
            "review_id": str(runnable_review.review_id),
            "decision": "PARTIALLY_ACCEPTED",
            "reason": "核定後不應再變更",
            "after_value": {"reported_rate": "-7"},
        },
    )

    assert late_decision.status_code == 409
    assert late_decision.json()["error"]["code"] == "REVIEW_STATE_CONFLICT"
