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
    assert len(decisions.json()) == 2

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM review.decisions WHERE review_id = %s",
            (runnable_review.review_id,),
        )
        assert cursor.fetchone()[0] == 2
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
    payload = run_payload(runnable_review)
    payload["adjustment_checks"][0]["reported_rate"] = "-10"

    rerun = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/rerun", json=payload
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
