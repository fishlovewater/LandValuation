from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.review.demo import DEMO_CASE_NO, reset_demo, revise_demo, seed_demo


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
            finding_decision = client.post(
                f"/api/v1/review/findings/{high['finding_id']}/decisions",
                json={
                    "review_id": seeded["review_id"],
                    "decision": "PARTIALLY_ACCEPTED",
                    "reason": "請依修正版重新檢核",
                    "after_value": {"adjustment_rate": "-7"},
                },
                headers=headers,
            )
            assert finding_decision.status_code == 201
            case_decision = client.post(
                f"/api/v1/review/cases/{seeded['review_id']}/decision",
                json={
                    "decision": "RETURNED_FOR_REVISION",
                    "reason": "請提交修正版正式報告",
                },
                headers=headers,
            )
            assert case_decision.status_code == 201
            assert revise_demo()["created"] is True

            rerun = client.post(
                f"/api/v1/review/workbench/cases/{seeded['review_id']}/start",
                headers=headers,
            )
            assert rerun.status_code == 200
            assert rerun.json()["outcome"] == "COMPLETED"
            assert rerun.json()["run"]["run_no"] == 2

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
                "decision": "ACCEPTED",
                "reason": "第一次人工決策",
            }

            first = client.post(
                f"/api/v1/review/findings/{finding['finding_id']}/decisions",
                json=payload,
                headers=headers,
            )
            second = client.post(
                f"/api/v1/review/findings/{finding['finding_id']}/decisions",
                json={**payload, "decision": "REJECTED", "reason": "不應覆寫"},
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
            assert cursor.fetchone()[0] == "ACCEPTED"
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
