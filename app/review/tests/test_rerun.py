import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.session import AsyncSessionFactory
from app.review.repository import ReviewRepository
from app.review.service import ReviewService
from app.review.tests.test_runs_api import (
    authorized_client,
    run_payload,
    runnable_review,
)


def test_finding_decision_is_immutable_and_case_decisions_are_append_only(
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
            "after_value": {"value": "-7.00"},
        },
    )
    assert decided.status_code == 201
    assert decided.json()["decision"] == "PARTIALLY_ACCEPTED"
    assert decided.json()["request_id"] == request_id
    assert decided.json()["after_value"] == {
        "selection_source": "REVIEWER",
        "field_path": finding["field_path"],
        "value": "-7.00",
    }

    still_blocked = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "APPROVED", "reason": "部分接受後嘗試核准"},
    )
    assert still_blocked.status_code == 409

    duplicate = authorized_client.post(
        f"/api/v1/review/findings/{finding['finding_id']}/decisions",
        json={
            "review_id": str(runnable_review.review_id),
            "decision": "ACCEPTED",
            "reason": "不應覆寫既有疑點決策",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "FINDING_DECISION_CONFLICT"

    approved = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/decision",
        json={"decision": "APPROVED", "reason": "高風險疑點已完成處理"},
    )
    assert approved.status_code == 409

    decisions = authorized_client.get(
        f"/api/v1/review/cases/{runnable_review.review_id}/decisions"
    )
    assert decisions.status_code == 200
    assert len(decisions.json()) == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM review.decisions WHERE review_id = %s",
            (runnable_review.review_id,),
        )
        assert cursor.fetchone()[0] == 1
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

    assert rerun.status_code == 200
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


def test_rerun_supersedes_legacy_finding_code_by_validation_rule(
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
            "UPDATE review.findings SET finding_code = 'ADJUSTMENT_RATE:legacy-field' WHERE finding_id = %s",
            (old_finding["finding_id"],),
        )
        cursor.execute(
            "UPDATE review.reviews SET review_status = 'READY_FOR_REVIEW' WHERE review_id = %s",
            (runnable_review.review_id,),
        )
    postgres_connection.commit()

    rerun = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/rerun", json={}
    )

    assert rerun.status_code == 200
    new_finding = authorized_client.get(
        f"/api/v1/review/runs/{rerun.json()['validation_run_id']}/findings"
    ).json()[0]
    assert new_finding["supersedes_finding_id"] == old_finding["finding_id"]


def test_rerun_fails_closed_when_previous_run_has_duplicate_rule_links(
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
            """INSERT INTO review.findings (
                review_id, source_validation_finding_id, finding_code, finding_type,
                severity, title, description, status, validation_run_id
            ) SELECT review_id, source_validation_finding_id, 'DUPLICATE-RULE-LINK',
                     finding_type, severity, title, description, status, validation_run_id
              FROM review.findings WHERE finding_id = %s""",
            (old_finding["finding_id"],),
        )
        cursor.execute(
            "UPDATE review.reviews SET review_status = 'READY_FOR_REVIEW' WHERE review_id = %s",
            (runnable_review.review_id,),
        )
    postgres_connection.commit()

    rerun = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/rerun", json={}
    )

    assert rerun.status_code == 200
    new_finding = authorized_client.get(
        f"/api/v1/review/runs/{rerun.json()['validation_run_id']}/findings"
    ).json()[0]
    assert new_finding["supersedes_finding_id"] is None


@pytest.mark.asyncio
async def test_finding_rule_links_do_not_cross_review_boundaries(
    runnable_review, postgres_connection
):
    other_case_id = uuid4()
    other_review_id = uuid4()
    other_run_id = uuid4()
    other_machine_finding_id = uuid4()
    other_finding_id = uuid4()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status
            ) VALUES (%s, %s, 'Other Review Case', 'LAND', CURRENT_DATE,
                      'F', 'F01', 'DRAFT')""",
            (other_case_id, f"OTHER-{str(other_case_id)[:8]}"),
        )
        cursor.execute(
            """INSERT INTO review.reviews (
                review_id, case_id, review_status, started_by_user_id
            ) VALUES (%s, %s, 'READY_FOR_REVIEW', %s)""",
            (other_review_id, other_case_id, runnable_review.user_id),
        )
        cursor.execute(
            """INSERT INTO valuation.validation_runs (
                validation_run_id, case_id, review_id, run_no, run_status,
                input_snapshot, rule_version_id, ruleset_snapshot, started_at, completed_at
            ) VALUES (%s, %s, %s, 1, 'COMPLETED', '{}', %s, '{}', now(), now())""",
            (
                other_run_id,
                other_case_id,
                other_review_id,
                runnable_review.rule_version_id,
            ),
        )
        cursor.execute(
            """INSERT INTO valuation.validation_findings (
                finding_id, validation_run_id, validation_rule_id, severity, finding_message
            ) VALUES (%s, %s, %s, 'HIGH', 'Other review finding')""",
            (
                other_machine_finding_id,
                other_run_id,
                runnable_review.validation_rule_id,
            ),
        )
        cursor.execute(
            """INSERT INTO review.findings (
                finding_id, review_id, source_validation_finding_id, finding_code,
                finding_type, severity, title, description, status, validation_run_id
            ) VALUES (%s, %s, %s, 'OTHER-RULE', 'RATE_OUT_OF_RANGE', 'HIGH',
                      'Other', 'Other review finding', 'OPEN', %s)""",
            (other_finding_id, other_review_id, other_machine_finding_id, other_run_id),
        )
    postgres_connection.commit()
    try:
        async with AsyncSessionFactory() as session:
            repository = ReviewRepository(session)
            assert await repository.list_finding_rule_links(
                runnable_review.review_id, other_run_id
            ) == []
            assert await repository.list_finding_rule_links(
                other_review_id, other_run_id
            ) == [(other_finding_id, runnable_review.validation_rule_id)]
    finally:
        with postgres_connection.cursor() as cursor:
            cursor.execute("DELETE FROM review.findings WHERE finding_id = %s", (other_finding_id,))
            cursor.execute("DELETE FROM valuation.validation_findings WHERE finding_id = %s", (other_machine_finding_id,))
            cursor.execute("DELETE FROM valuation.validation_runs WHERE validation_run_id = %s", (other_run_id,))
            cursor.execute("DELETE FROM review.reviews WHERE review_id = %s", (other_review_id,))
            cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (other_case_id,))
        postgres_connection.commit()


@pytest.mark.asyncio
async def test_rerun_locks_before_reloading_latest_history(monkeypatch):
    run1_id, run2_id, run3_id = uuid4(), uuid4(), uuid4()

    class LockedRepository:
        def __init__(self):
            self.review = SimpleNamespace(review_id=uuid4(), latest_validation_run_id=run1_id)
            self.lock = asyncio.Lock()
            self.first_locked = asyncio.Event()
            self.second_waiting = asyncio.Event()
            self.release_first = asyncio.Event()
            self.history_reads = []

        async def get(self, review_id, for_update=False):
            assert review_id == self.review.review_id
            assert for_update is True
            if self.lock.locked():
                self.second_waiting.set()
            await self.lock.acquire()
            if not self.first_locked.is_set():
                self.first_locked.set()
            return self.review

        async def list_finding_rule_links(self, review_id, validation_run_id):
            assert review_id == self.review.review_id
            self.history_reads.append(validation_run_id)
            return []

    repository = LockedRepository()
    service = ReviewService(repository)
    create_calls = 0

    async def create_run(review_id, actor_id, supersedes_by_rule_id=None, locked_review=None):
        nonlocal create_calls
        assert review_id == repository.review.review_id
        assert locked_review is repository.review
        create_calls += 1
        if create_calls == 1:
            await repository.release_first.wait()
            repository.review.latest_validation_run_id = run2_id
        else:
            assert repository.review.latest_validation_run_id == run2_id
            repository.review.latest_validation_run_id = run3_id
        repository.lock.release()
        return SimpleNamespace(), SimpleNamespace()

    monkeypatch.setattr(service, "create_run", create_run)
    first = asyncio.create_task(service.rerun(repository.review.review_id, uuid4()))
    await repository.first_locked.wait()
    second = asyncio.create_task(service.rerun(repository.review.review_id, uuid4()))
    await repository.second_waiting.wait()
    repository.release_first.set()
    await asyncio.gather(first, second)

    assert repository.history_reads == [run1_id, run2_id]


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

    assert rerun.status_code == 200
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
            "after_value": {"value": "-7"},
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
