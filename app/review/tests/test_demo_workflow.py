from datetime import UTC, datetime, timedelta
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient
from openpyxl import load_workbook

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

            # Triage every finding, then raise and send a correction request.
            for item in findings1.json():
                decision = (
                    "CONFIRMED_ISSUE"
                    if item["finding_id"] == high["finding_id"]
                    else "DISMISSED_FALSE_POSITIVE"
                )
                triaged = client.post(
                    f"/api/v1/review/findings/{item['finding_id']}/triage",
                    json={
                        "review_id": review_id,
                        "decision": decision,
                        "reason": "Demo triage",
                    },
                    headers=headers,
                )
                assert triaged.status_code == 201

            due_at = (datetime.now(UTC) + timedelta(days=5)).isoformat()
            draft = client.post(
                f"/api/v1/review/cases/{review_id}/correction-requests",
                json={
                    "message": "Use the revised official report",
                    "due_at": due_at,
                },
                headers=headers,
            )
            assert draft.status_code == 201
            request_id = draft.json()["correction_request_id"]
            assert client.post(
                f"/api/v1/review/correction-requests/{request_id}/send",
                json={},
                headers=headers,
            ).status_code == 200
            assert client.get(
                f"/api/v1/review/cases/{review_id}", headers=headers
            ).json()["review_status"] == "RETURNED_FOR_REVISION"

            revision = revise_demo()
            assert revision["created"] is True
            assert revise_demo()["created"] is False

            revised_document = next(
                item
                for item in client.get(
                    f"/api/v1/review/workbench/cases/{review_id}", headers=headers
                ).json()["documents"]
                if item["document_type"] == "original" and item["version_no"] == 2
            )
            assert client.post(
                f"/api/v1/review/correction-requests/{request_id}/resubmissions",
                json={
                    "document_id": revised_document["document_id"],
                    "document_version": 2,
                },
                headers=headers,
            ).status_code == 201
            rechecked = client.post(
                f"/api/v1/review/correction-requests/{request_id}/recheck",
                headers=headers,
            )
            assert rechecked.status_code == 200
            assert rechecked.json()["status"] == "RECHECKED"
            assert {
                item["recheck_outcome"] for item in rechecked.json()["items"]
            } <= {"RESOLVED", "STILL_PRESENT"}

            run2 = next(
                item
                for item in client.get(
                    f"/api/v1/review/cases/{review_id}/runs", headers=headers
                ).json()
                if item["run_no"] == 2
            )
            run2_id = run2["validation_run_id"]
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

            # Complete the review, then export the immutable Excel and Word
            # artifacts and reopen both byte streams.
            remaining = client.get(
                f"/api/v1/review/runs/{run2_id}/findings", headers=headers
            ).json()
            for item in remaining:
                if item["status"] != "OPEN":
                    continue
                assert client.post(
                    f"/api/v1/review/findings/{item['finding_id']}/triage",
                    json={
                        "review_id": review_id,
                        "decision": "DISMISSED_FALSE_POSITIVE",
                        "reason": "修正版已排除",
                    },
                    headers=headers,
                ).status_code == 201
            completed = client.post(
                f"/api/v1/review/cases/{review_id}/complete-review",
                json={"reason": "修正版已確認無誤"},
                headers=headers,
            )
            assert completed.status_code == 201
            for format_name, opener in (
                ("xlsx", load_workbook),
                ("docx", Document),
            ):
                exported = client.post(
                    f"/api/v1/review/runs/{run2_id}/reports",
                    json={"format": format_name},
                    headers=headers,
                )
                assert exported.status_code == 201
                body = exported.json()
                assert "bucket_name" not in body
                assert "object_key" not in body
                artifact = client.get(
                    f"/api/v1/review/reports/{body['document_id']}/download",
                    headers=headers,
                )
                assert artifact.status_code == 200
                # Both artifacts reopen successfully.
                assert opener(BytesIO(artifact.content)) is not None
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
