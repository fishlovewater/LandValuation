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
    assert structured.json()["findings"][0]["finding_code"] == "RATE-COMP-001"

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
