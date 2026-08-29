from fastapi.testclient import TestClient

from app.main import app
from app.review.demo import (
    DEMO_CASE_NO,
    DEMO_USERNAME,
    reset_demo,
    revise_demo,
    seed_demo,
)


def test_demo_seed_is_idempotent_and_real_api_workflow_completes(postgres_connection):
    first = seed_demo()
    second = seed_demo()
    assert first["case_id"] != second["case_id"]

    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM valuation.cases WHERE case_no = %s", (DEMO_CASE_NO,))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT count(*) FROM auth.users WHERE username = %s", (DEMO_USERNAME,))
        assert cursor.fetchone()[0] == 1

    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": second["username"], "password": second["password"]},
            )
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            review_id = second["review_id"]

            completeness = client.post(
                f"/api/v1/review/cases/{review_id}/completeness-check",
                headers=headers,
            )
            assert completeness.status_code == 200
            assert completeness.json()["ready"] is True

            run1 = client.post(
                f"/api/v1/review/cases/{review_id}/runs",
                json={},
                headers=headers,
            )
            assert run1.status_code == 200
            assert run1.json()["run_no"] == 1
            run1_id = run1.json()["validation_run_id"]

            findings1 = client.get(
                f"/api/v1/review/runs/{run1_id}/findings",
                headers=headers,
            )
            assert findings1.status_code == 200
            assert {item["severity"] for item in findings1.json()} == {"HIGH", "MEDIUM"}
            high = next(item for item in findings1.json() if item["severity"] == "HIGH")

            finding_decision = client.post(
                f"/api/v1/review/findings/{high['finding_id']}/decisions",
                json={
                    "review_id": review_id,
                    "decision": "PARTIALLY_ACCEPTED",
                    "reason": "Demo requires revision",
                    "after_value": {"value": "-7"},
                },
                headers=headers,
            )
            assert finding_decision.status_code == 201

            case_decision = client.post(
                f"/api/v1/review/cases/{review_id}/decision",
                json={
                    "decision": "RETURNED_FOR_REVISION",
                    "reason": "Use the revised official report",
                },
                headers=headers,
            )
            assert case_decision.status_code == 201
            assert client.patch(
                f"/api/v1/review/cases/{review_id}",
                json={"review_status": "PREPROCESSING"},
                headers=headers,
            ).status_code == 200

            revision = revise_demo()
            assert revision["created"] is True
            assert revise_demo()["created"] is False
            assert client.post(
                f"/api/v1/review/cases/{review_id}/completeness-check",
                headers=headers,
            ).json()["ready"] is True

            run2 = client.post(
                f"/api/v1/review/cases/{review_id}/rerun",
                json={},
                headers=headers,
            )
            assert run2.status_code == 200
            assert run2.json()["run_no"] == 2
            run2_id = run2.json()["validation_run_id"]
            assert client.get(
                f"/api/v1/review/runs/{run1_id}", headers=headers
            ).status_code == 200

            findings2 = client.get(
                f"/api/v1/review/runs/{run2_id}/findings",
                headers=headers,
            ).json()
            assert len(findings2) == 1
            assert findings2[0]["supersedes_finding_id"] == high["finding_id"]
            assert client.get(
                f"/api/v1/review/runs/{run2_id}/report", headers=headers
            ).status_code == 200
            generated = client.post(
                f"/api/v1/review/runs/{run2_id}/report/pdf", headers=headers
            )
            assert generated.status_code == 201
            downloaded = client.get(
                f"/api/v1/review/runs/{run2_id}/report/pdf/download",
                headers=headers,
            )
            assert downloaded.status_code == 200
            assert downloaded.content.startswith(b"%PDF-")
    finally:
        removed = reset_demo()
        assert removed["removed"] is True

    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM valuation.cases WHERE case_no = %s", (DEMO_CASE_NO,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM auth.users WHERE username = %s", (DEMO_USERNAME,))
        assert cursor.fetchone()[0] == 0


def test_demo_reset_is_a_successful_noop():
    reset_demo()
    result = reset_demo()

    assert result == {"command": "reset", "removed": False, "object_count": 0}
