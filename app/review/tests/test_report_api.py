import hashlib
import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

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
    assert finding["source_evidence"][0]["verification_status"] == "APPLIED"

    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        generated = authorized_client.post(
            f"/api/v1/review/runs/{run['validation_run_id']}/report/pdf"
        )
        assert generated.status_code == 201
        metadata = generated.json()
        # Storage internals must never reach an API response.
        assert "bucket_name" not in metadata
        assert "object_key" not in metadata
        assert metadata["mime_type"] == "application/pdf"
        assert metadata["original_filename"].endswith(".pdf")

        downloaded = authorized_client.get(
            f"/api/v1/review/runs/{run['validation_run_id']}/report/pdf/download"
        )
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


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


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@pytest.fixture
def completed_review(authorized_client, runnable_review):
    """Dismiss every finding and complete the Review so a final report is allowed."""
    run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    findings = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    ).json()
    for finding in findings:
        authorized_client.post(
            f"/api/v1/review/findings/{finding['finding_id']}/triage",
            json={
                "review_id": str(runnable_review.review_id),
                "decision": "DISMISSED_FALSE_POSITIVE",
                "reason": "屬誤判",
            },
        )
    completed = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/complete-review",
        json={"reason": "確認無誤並完成審查"},
    )
    assert completed.status_code == 201
    return SimpleNamespace(
        id=run["validation_run_id"],
        review_id=runnable_review.review_id,
        case_id=runnable_review.case_id,
    )


@pytest.mark.parametrize(
    ("format_name", "mime_type", "suffix"),
    [
        ("xlsx", XLSX_MIME, ".xlsx"),
        ("docx", DOCX_MIME, ".docx"),
    ],
)
def test_generate_and_download_report(
    authorized_client, completed_review, format_name, mime_type, suffix
):
    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        generated = authorized_client.post(
            f"/api/v1/review/runs/{completed_review.id}/reports",
            json={"format": format_name},
        )
        assert generated.status_code == 201
        body = generated.json()
        assert body["original_filename"].endswith(suffix)
        assert "bucket_name" not in body
        assert "object_key" not in body
        downloaded = authorized_client.get(
            f"/api/v1/review/reports/{body['document_id']}/download"
        )
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith(mime_type)
        # Both formats are real Office packages (ZIP containers).
        assert downloaded.content.startswith(b"PK")
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def test_final_report_requires_completed_review(
    authorized_client, runnable_review
):
    run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        response = authorized_client.post(
            f"/api/v1/review/runs/{run['validation_run_id']}/reports",
            json={"format": "xlsx"},
        )
    finally:
        app.dependency_overrides.pop(get_storage_service, None)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEW_REPORT_NOT_AVAILABLE"


def test_report_generation_rejects_unknown_format(
    authorized_client, completed_review
):
    response = authorized_client.post(
        f"/api/v1/review/runs/{completed_review.id}/reports",
        json={"format": "pptx"},
    )
    assert response.status_code == 422


def test_download_rejects_unknown_document(authorized_client, completed_review):
    response = authorized_client.get(
        f"/api/v1/review/reports/{uuid4()}/download"
    )
    assert response.status_code == 404


def test_storage_object_is_removed_when_metadata_write_fails(
    authorized_client, completed_review, monkeypatch
):
    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage

    from app.review.repository import ReviewRepository

    async def failing_save(self, **values):
        raise RuntimeError("metadata write failed")

    monkeypatch.setattr(ReviewRepository, "save_report_document", failing_save)
    try:
        with pytest.raises(RuntimeError):
            authorized_client.post(
                f"/api/v1/review/runs/{completed_review.id}/reports",
                json={"format": "xlsx"},
            )
    finally:
        app.dependency_overrides.pop(get_storage_service, None)
    # The uploaded object was cleaned up, leaving no orphan.
    assert storage.objects == {}


def test_generated_reports_are_immutable_and_independently_versioned(
    authorized_client, completed_review
):
    """Each generated artifact keeps its own bytes and version number.

    Regenerating the identical content is refused by the per-case checksum
    constraint, which is what makes an already generated report immutable.
    """
    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        xlsx = authorized_client.post(
            f"/api/v1/review/runs/{completed_review.id}/reports",
            json={"format": "xlsx"},
        ).json()
        xlsx_bytes = authorized_client.get(
            f"/api/v1/review/reports/{xlsx['document_id']}/download"
        ).content
        docx = authorized_client.post(
            f"/api/v1/review/runs/{completed_review.id}/reports",
            json={"format": "docx"},
        ).json()
        assert docx["document_id"] != xlsx["document_id"]
        assert docx["version_no"] > xlsx["version_no"]
        # The earlier artifact is untouched by the later generation.
        again = authorized_client.get(
            f"/api/v1/review/reports/{xlsx['document_id']}/download"
        ).content
        assert again == xlsx_bytes
        assert xlsx["checksum_sha256"] != docx["checksum_sha256"]
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


@pytest.mark.parametrize(
    ("format_name", "mime_type", "suffix"),
    [
        ("xlsx", XLSX_MIME, ".xlsx"),
        ("docx", DOCX_MIME, ".docx"),
    ],
)
def test_correction_request_report_requires_sent_or_later(
    authorized_client, runnable_review, format_name, mime_type, suffix
):
    from datetime import UTC, datetime, timedelta

    run = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=run_payload(runnable_review),
    ).json()
    findings = authorized_client.get(
        f"/api/v1/review/runs/{run['validation_run_id']}/findings"
    ).json()
    for index, finding in enumerate(findings):
        authorized_client.post(
            f"/api/v1/review/findings/{finding['finding_id']}/triage",
            json={
                "review_id": str(runnable_review.review_id),
                "decision": (
                    "CONFIRMED_ISSUE" if index == 0 else "DISMISSED_FALSE_POSITIVE"
                ),
                "reason": "判定理由",
            },
        )
    draft = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/correction-requests",
        json={
            "message": "請更正",
            "due_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
        },
    ).json()
    request_id = draft["correction_request_id"]

    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        # A DRAFT request has no immutable notice to export yet.
        blocked = authorized_client.post(
            f"/api/v1/review/correction-requests/{request_id}/reports",
            json={"format": format_name},
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "CORRECTION_REPORT_NOT_AVAILABLE"

        authorized_client.post(
            f"/api/v1/review/correction-requests/{request_id}/send", json={}
        )
        generated = authorized_client.post(
            f"/api/v1/review/correction-requests/{request_id}/reports",
            json={"format": format_name},
        )
        assert generated.status_code == 201
        body = generated.json()
        assert body["document_type"] == "correction-request"
        assert body["original_filename"] == f"correction-request-1{suffix}"
        assert "bucket_name" not in body
        assert "object_key" not in body

        downloaded = authorized_client.get(
            f"/api/v1/review/reports/{body['document_id']}/download"
        )
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith(mime_type)
    finally:
        app.dependency_overrides.pop(get_storage_service, None)
