from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.exceptions import AppError
from app.valuation.documents.schemas import DocumentCategory
from app.valuation.documents.service import DocumentService, safe_filename


class FakeStorage:
    def __init__(self) -> None:
        self.uploaded_key = None
        self.deleted_key = None

    async def upload(self, object_key, data, length, content_type):
        self.uploaded_key = object_key
        assert data.read() == b"pdf-data"
        return {
            "bucket_name": "land-valuation",
            "object_key": object_key,
            "checksum_sha256": "a" * 64,
            "file_size_bytes": length,
            "etag": "etag",
        }

    async def delete(self, object_key):
        self.deleted_key = object_key


class FakeRepository:
    def __init__(self, fail_create=False) -> None:
        self.fail_create = fail_create
        self.deactivated = None

    async def latest_in_group(self, case_id, group_id):
        return None

    async def next_version(self, case_id, group_id):
        return 1

    async def deactivate_group(self, case_id, group_id):
        self.deactivated = group_id

    async def create(self, record):
        if self.fail_create:
            raise RuntimeError("metadata failed")
        record.uploaded_at = SimpleNamespace()
        return record


class FakeValuation:
    async def _owned_editable_case(self, case_id, user):
        return SimpleNamespace(case_id=case_id)


def upload_file() -> UploadFile:
    return UploadFile(
        file=BytesIO(b"pdf-data"),
        filename="土地 登記.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )


def test_safe_filename_removes_path_and_unsafe_characters() -> None:
    assert safe_filename("../土地 登記?.pdf") == "土地_登記_.pdf"


@pytest.mark.asyncio
async def test_document_key_uses_group_and_version() -> None:
    storage = FakeStorage()
    repository = FakeRepository()
    service = DocumentService(None, storage, repository=repository)
    service.valuation = FakeValuation()
    case_id = uuid4()
    user = SimpleNamespace(user_id=uuid4())

    record = await service.upload(
        case_id,
        DocumentCategory.LAND_REGISTER,
        upload_file(),
        user,
    )

    assert record.object_key.startswith(
        f"cases/{case_id}/land-register/{record.document_group_id}/v1/"
    )
    assert "localhost" not in record.object_key


@pytest.mark.asyncio
async def test_metadata_failure_deletes_uploaded_object() -> None:
    storage = FakeStorage()
    service = DocumentService(None, storage, repository=FakeRepository(True))
    service.valuation = FakeValuation()

    with pytest.raises(RuntimeError, match="metadata failed"):
        await service.upload(
            uuid4(),
            DocumentCategory.LAND_REGISTER,
            upload_file(),
            SimpleNamespace(user_id=uuid4()),
        )

    assert storage.deleted_key == storage.uploaded_key


@pytest.mark.asyncio
async def test_formal_map_upload_rejects_unpreviewable_mime_type() -> None:
    storage = FakeStorage()
    service = DocumentService(None, storage, repository=FakeRepository())
    service.valuation = FakeValuation()
    file = UploadFile(
        file=BytesIO(b"pdf-data"),
        filename="not-a-map.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(AppError) as exc_info:
        await service.upload(
            uuid4(),
            DocumentCategory.MAP_SECTION_SKETCH,
            file,
            SimpleNamespace(user_id=uuid4()),
        )

    assert getattr(exc_info.value, "code", None) == "MAP_MIME_TYPE_UNSUPPORTED"
    assert storage.uploaded_key is None
