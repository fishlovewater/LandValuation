import hashlib
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.exceptions import AppError
from app.valuation.documents.repository import DocumentRepository
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

    async def get_by_checksum(self, case_id, checksum_sha256):
        return None

    async def get_inactive_by_checksum(self, case_id, checksum_sha256):
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


@pytest.mark.asyncio
async def test_source_document_removal_deactivates_metadata_and_removes_object() -> None:
    case_id = uuid4()
    document_id = uuid4()

    class DeleteRepository:
        async def get(self, supplied_case_id, supplied_document_id):
            assert (supplied_case_id, supplied_document_id) == (case_id, document_id)
            return SimpleNamespace(
                document_id=document_id,
                is_active=True,
                document_type=DocumentCategory.LAND_REGISTER.value,
                object_key="cases/test/land-register/source.pdf",
            )

        async def deactivate_document(self, supplied_case_id, supplied_document_id):
            assert (supplied_case_id, supplied_document_id) == (case_id, document_id)
            return True

    storage = FakeStorage()
    service = DocumentService(None, storage, repository=DeleteRepository())
    service.valuation = FakeValuation()

    await service.delete_source_document(
        case_id, document_id, SimpleNamespace(user_id=uuid4())
    )

    assert storage.deleted_key == "cases/test/land-register/source.pdf"


@pytest.mark.asyncio
async def test_checksum_lookup_ignores_removed_documents() -> None:
    class ReadSession:
        statement = None

        async def scalar(self, statement):
            self.statement = statement
            return None

    session = ReadSession()
    await DocumentRepository(session).get_by_checksum(uuid4(), "a" * 64)

    compiled = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "documents.is_active IS true" in compiled


@pytest.mark.asyncio
async def test_reuploading_a_removed_file_reactivates_its_document() -> None:
    case_id = uuid4()
    document_id = uuid4()
    group_id = uuid4()

    class ReactivationRepository(FakeRepository):
        def __init__(self):
            super().__init__()
            self.removed = SimpleNamespace(
                document_id=document_id,
                document_group_id=group_id,
                is_active=False,
            )
            self.reactivated = None

        async def get_inactive_by_checksum(self, supplied_case_id, checksum_sha256):
            assert supplied_case_id == case_id
            assert checksum_sha256 == hashlib.sha256(b"pdf-data").hexdigest()
            return self.removed

        async def next_version(self, supplied_case_id, supplied_group_id):
            assert (supplied_case_id, supplied_group_id) == (case_id, group_id)
            return 2

        async def reactivate(self, record, **values):
            self.reactivated = (record, values)
            record.is_active = True
            record.version_no = values["version_no"]
            return record

    storage = FakeStorage()
    repository = ReactivationRepository()
    service = DocumentService(None, storage, repository=repository)
    service.valuation = FakeValuation()

    record = await service.upload(
        case_id,
        DocumentCategory.CADASTRAL_MAP,
        upload_file(),
        SimpleNamespace(user_id=uuid4()),
    )

    assert record.document_id == document_id
    assert record.is_active is True
    assert record.version_no == 2
    assert repository.reactivated[1]["document_type"] == "cadastral-map"


@pytest.mark.asyncio
async def test_source_document_category_can_be_changed_to_a_formal_map() -> None:
    case_id = uuid4()
    document_id = uuid4()

    class ReclassifyRepository:
        async def get(self, supplied_case_id, supplied_document_id):
            assert (supplied_case_id, supplied_document_id) == (case_id, document_id)
            return SimpleNamespace(
                document_id=document_id,
                is_active=True,
                document_type=DocumentCategory.ORIGINAL.value,
                mime_type="image/png",
            )

        async def reclassify(self, record, category):
            record.document_type = category
            return record

    service = DocumentService(None, FakeStorage(), repository=ReclassifyRepository())
    service.valuation = FakeValuation()
    record = await service.reclassify_source_document(
        case_id,
        document_id,
        DocumentCategory.MAP_SECTION_SKETCH,
        SimpleNamespace(user_id=uuid4()),
    )

    assert record.document_type == "map-section-sketch"
