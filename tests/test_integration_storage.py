import io
import os
from uuid import uuid4

import pytest
from fastapi.concurrency import run_in_threadpool

from app.storage.client import get_minio_client
from app.storage.service import StorageService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="Set RUN_INTEGRATION=1 to test the configured MinIO instance",
)


@pytest.mark.asyncio
async def test_minio_upload_download_delete_round_trip() -> None:
    service = StorageService(get_minio_client())
    payload = b"land-valuation-fastapi-storage-test"
    object_key = f"knowledge/system-tests/{uuid4()}/v1/storage-test.txt"

    try:
        result = await service.upload(
            object_key,
            io.BytesIO(payload),
            len(payload),
            "text/plain",
        )
        assert result["bucket_name"] == service.bucket
        assert result["object_key"] == object_key

        response = await service.download(object_key)
        try:
            downloaded = await run_in_threadpool(response.read)
        finally:
            response.close()
            response.release_conn()
        assert downloaded == payload
    finally:
        await service.delete(object_key)
