import hashlib

from app.main import app
from app.storage.dependencies import get_storage_service
from app.review.tests.test_runs_api import (
    authorized_client,
    run_payload,
    runnable_review,
)


class DownloadObject:
    def __init__(self, content):
        self.content = content

    def read(self):
        return self.content

    def close(self):
        pass

    def release_conn(self):
        pass


class FakeStorage:
    bucket = "land-valuation"

    def __init__(self):
        self.objects = {}

    async def upload(self, object_key, data, length, content_type):
        content = data.read()
        assert length == len(content)
        self.objects[object_key] = content
        return {
            "bucket_name": self.bucket,
            "object_key": object_key,
            "checksum_sha256": hashlib.sha256(content).hexdigest(),
            "file_size_bytes": len(content),
            "etag": "fake-etag",
        }

    async def download(self, object_key):
        return DownloadObject(self.objects[object_key])

    async def delete(self, object_key):
        self.objects.pop(object_key, None)


def test_structured_and_pdf_report_apis(authorized_client, runnable_review):
    run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()

    structured = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/report"
    )
    assert structured.status_code == 200
    assert structured.json()["case"]["case_no"].startswith("RUN-")
    finding = structured.json()["findings"][0]
    assert finding["finding_code"] == (
        f"{runnable_review.rule_version_id}:{runnable_review.validation_rule_id}"
    )
    assert finding["source_evidence"][0]["verification_status"] == "VERIFIED"

    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    generated = authorized_client.post(
        f"/api/v1/review/runs/{run['validation_run_id']}/report/pdf"
    )
    assert generated.status_code == 201
    metadata = generated.json()
    assert metadata["bucket_name"] == "land-valuation"
    assert metadata["object_key"].startswith(
        f"cases/{runnable_review.case_id}/generated/"
    )
    assert "localhost" not in metadata["object_key"]

    downloaded = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/report/pdf/download"
    )
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"%PDF")


def test_report_decisions_are_scoped_to_the_requested_run(
    authorized_client, runnable_review, postgres_connection
):
    run1 = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    findings1 = authorized_client.get(
        f"/api/v1/review/runs/{run1['validation_run_id']}/findings"
    ).json()
    finding1 = findings1[0]
    from datetime import UTC, datetime, timedelta

    for item in findings1:
        decision = "CONFIRMED_ISSUE" if item["finding_id"] == finding1["finding_id"] else "DISMISSED_FALSE_POSITIVE"
        reason = "run-1 finding decision" if item["finding_id"] == finding1["finding_id"] else "run-1 dismiss"
        assert authorized_client.post(
            f"/api/v1/review/findings/{item['finding_id']}/triage",
            json={
                "review_id": str(runnable_review.review_id),
                "decision": decision,
                "reason": reason,
            },
        ).status_code == 201
    draft = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/correction-requests",
        json={
            "message": "case decision",
            "due_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
        },
    )
    assert draft.status_code == 201
    assert authorized_client.post(
        f"/api/v1/review/correction-requests/{draft.json()['correction_request_id']}/send",
        json={},
    ).status_code == 200
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE review.reviews
            SET review_status = 'READY_FOR_REVIEW', missing_item_count = 9
            WHERE review_id = %s
            """,
            (runnable_review.review_id,),
        )
    postgres_connection.commit()

    run2 = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/rerun", json={}
    ).json()
    finding2 = authorized_client.get(
        f"/api/v1/review/runs/{run2['validation_run_id']}/findings"
    ).json()[0]
    assert authorized_client.post(
        f"/api/v1/review/findings/{finding2['finding_id']}/triage",
        json={
            "review_id": str(runnable_review.review_id),
            "decision": "CONFIRMED_ISSUE",
            "reason": "run-2 finding decision",
        },
    ).status_code == 201

    report1 = authorized_client.get(
        f"/api/v1/review/runs/{run1['validation_run_id']}/report"
    ).json()
    report2 = authorized_client.get(
        f"/api/v1/review/runs/{run2['validation_run_id']}/report"
    ).json()

    assert [item["reason"] for item in report1["findings"][0]["decisions"]] == [
        "run-1 finding decision"
    ]
    assert [item["reason"] for item in report2["findings"][0]["decisions"]] == [
        "run-2 finding decision"
    ]
    # Correction-send case decisions are scoped by correction request, not run,
    # so they no longer appear in a run-scoped report's case_decisions.
    assert report1["case_decisions"] == []
    assert report2["case_decisions"] == []
    assert report1["review_status"] == "REVIEW_REQUIRED"
    assert report1["missing_item_count"] == 0
