from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.review.demo import DEMO_CASE_NO, reset_demo, revise_demo, seed_demo


def test_preflight_ready_does_not_create_run(postgres_connection):
    seeded = seed_demo()
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": seeded["username"], "password": seeded["password"]},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            response = client.post(
                "/api/v1/review/workbench/cases/"
                f"{seeded['review_id']}/start/preflight",
                headers=headers,
            )
            repeated = client.post(
                "/api/v1/review/workbench/cases/"
                f"{seeded['review_id']}/start/preflight",
                headers=headers,
            )

        assert response.status_code == 200
        assert response.json()["outcome"] == "READY"
        assert response.json()["completeness"]["ready"] is True
        assert response.json()["completeness"]["review_status"] == "READY_FOR_REVIEW"
        assert repeated.status_code == 200
        assert repeated.json()["outcome"] == "READY"
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
                (seeded["review_id"],),
            )
            assert cursor.fetchone()[0] == 0

        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": seeded["username"], "password": seeded["password"]},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            started = client.post(
                f"/api/v1/review/workbench/cases/{seeded['review_id']}/start",
                headers=headers,
            )
        assert started.status_code == 200
        assert started.json()["outcome"] == "COMPLETED"
        assert started.json()["run"]["run_no"] == 1
    finally:
        reset_demo()


def test_seed_creates_received_review_and_start_completes(postgres_connection):
    seeded = seed_demo()
    try:
        assert seeded["review_id"]
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT review_status
                FROM review.reviews
                WHERE review_id = %s AND case_id = %s
                """,
                (seeded["review_id"], seeded["case_id"]),
            )
            assert cursor.fetchone()[0] == "RECEIVED"
            cursor.execute(
                """
                SELECT de.extraction_status, ef.form_code, ef.field_name,
                       ef.confirmed_value, ef.field_status
                FROM valuation.document_extractions AS de
                JOIN valuation.extracted_fields AS ef
                  ON ef.extraction_id = de.extraction_id
                WHERE de.case_id = %s
                ORDER BY ef.field_name
                """,
                (seeded["case_id"],),
            )
            assert cursor.fetchall() == [
                ("COMPLETED", "F01", "adjustment_rate", "-12", "APPLIED"),
                ("COMPLETED", "F01", "expert_grade", "B", "APPLIED"),
            ]

        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": seeded["username"], "password": seeded["password"]},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            listed = client.get(
                f"/api/v1/review/workbench/cases?q={DEMO_CASE_NO}",
                headers=headers,
            )
            assert listed.status_code == 200
            assert listed.json()["items"][0]["review_id"] == seeded["review_id"]

            started = client.post(
                f"/api/v1/review/workbench/cases/{seeded['review_id']}/start",
                headers=headers,
            )
            assert started.status_code == 200
            assert started.json()["outcome"] == "COMPLETED"
            assert started.json()["run"]["run_status"] == "COMPLETED"
            assert {item["severity"] for item in started.json()["findings"]} == {
                "HIGH",
                "MEDIUM",
            }
            assert started.json()["risk_summary"]["overall_risk_level"] == "HIGH"

            high = next(
                item for item in started.json()["findings"] if item["severity"] == "HIGH"
            )
            # Triage every finding, then raise and send a correction request.
            for item in started.json()["findings"]:
                decision = (
                    "CONFIRMED_ISSUE"
                    if item["finding_id"] == high["finding_id"]
                    else "DISMISSED_FALSE_POSITIVE"
                )
                triaged = client.post(
                    f"/api/v1/review/findings/{item['finding_id']}/triage",
                    json={
                        "review_id": seeded["review_id"],
                        "decision": decision,
                        "reason": "請依修正版重新檢核",
                    },
                    headers=headers,
                )
                assert triaged.status_code == 201
            due_at = (datetime.now(UTC) + timedelta(days=5)).isoformat()
            draft = client.post(
                f"/api/v1/review/cases/{seeded['review_id']}/correction-requests",
                json={"message": "請提交修正版正式報告", "due_at": due_at},
                headers=headers,
            )
            assert draft.status_code == 201
            request_id = draft.json()["correction_request_id"]
            sent = client.post(
                f"/api/v1/review/correction-requests/{request_id}/send",
                json={},
                headers=headers,
            )
            assert sent.status_code == 200
            assert revise_demo()["created"] is True

            revised = client.get(
                f"/api/v1/review/workbench/cases/{seeded['review_id']}",
                headers=headers,
            )
            revised_document = next(
                item
                for item in revised.json()["documents"]
                if item["document_type"] == "original" and item["version_no"] == 2
            )
            resubmitted = client.post(
                f"/api/v1/review/correction-requests/{request_id}/resubmissions",
                json={
                    "document_id": revised_document["document_id"],
                    "document_version": 2,
                },
                headers=headers,
            )
            assert resubmitted.status_code == 201
            rechecked = client.post(
                f"/api/v1/review/correction-requests/{request_id}/recheck",
                headers=headers,
            )
            assert rechecked.status_code == 200
            assert rechecked.json()["status"] == "RECHECKED"
            assert {
                item["recheck_outcome"] for item in rechecked.json()["items"]
            } <= {"RESOLVED", "STILL_PRESENT"}

            detail = client.get(
                f"/api/v1/review/workbench/cases/{seeded['review_id']}",
                headers=headers,
            )
            assert detail.status_code == 200
            assert [run["run_no"] for run in detail.json()["runs"]] == [1, 2]
            assert detail.json()["version_diffs"][0]["field_code"] == "adjustment_rate"
            assert detail.json()["findings"][0]["supersedes_finding_id"] == high[
                "finding_id"
            ]
    finally:
        reset_demo()


def test_finding_cannot_receive_a_second_decision(postgres_connection):
    seeded = seed_demo()
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": seeded["username"], "password": seeded["password"]},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            started = client.post(
                f"/api/v1/review/workbench/cases/{seeded['review_id']}/start",
                headers=headers,
            )
            finding = next(
                item for item in started.json()["findings"] if item["severity"] == "HIGH"
            )
            payload = {
                "review_id": seeded["review_id"],
                "decision": "CONFIRMED_ISSUE",
                "reason": "第一次人工判定",
            }

            first = client.post(
                f"/api/v1/review/findings/{finding['finding_id']}/triage",
                json=payload,
                headers=headers,
            )
            second = client.post(
                f"/api/v1/review/findings/{finding['finding_id']}/triage",
                json={
                    **payload,
                    "decision": "DISMISSED_FALSE_POSITIVE",
                    "reason": "不應覆寫",
                },
                headers=headers,
            )

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "FINDING_DECISION_CONFLICT"
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM review.findings WHERE finding_id = %s",
                (finding["finding_id"],),
            )
            assert cursor.fetchone()[0] == "CONFIRMED_ISSUE"
            cursor.execute(
                "SELECT count(*) FROM review.decisions WHERE finding_id = %s",
                (finding["finding_id"],),
            )
            assert cursor.fetchone()[0] == 1
    finally:
        reset_demo()


def test_demo_revise_http_is_development_only_and_idempotent(monkeypatch):
    seeded = seed_demo()
    try:
        monkeypatch.setattr(
            "app.review.router.get_settings",
            lambda: SimpleNamespace(app_env="development"),
        )
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": seeded["username"], "password": seeded["password"]},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            first = client.post("/api/v1/review/demo/revise", headers=headers)
            second = client.post("/api/v1/review/demo/revise", headers=headers)
        assert first.status_code == 200
        assert first.json()["created"] is True
        assert second.status_code == 200
        assert second.json()["created"] is False

        monkeypatch.setattr(
            "app.review.router.get_settings",
            lambda: SimpleNamespace(app_env="production"),
        )
        with TestClient(app) as client:
            hidden = client.post("/api/v1/review/demo/revise", headers=headers)
            hidden_without_token = client.post("/api/v1/review/demo/revise")
        assert hidden.status_code == 404
        assert hidden_without_token.status_code == 404
    finally:
        monkeypatch.undo()
        reset_demo()
