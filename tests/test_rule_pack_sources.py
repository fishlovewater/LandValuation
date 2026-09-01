from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.exceptions import AppError
from app.valuation.rule_packs.schemas import RulePackSourceManifest
from app.valuation.rule_packs.service import RulePackService


class FakeStorage:
    def __init__(self, checksum: str = "a" * 64) -> None:
        self.checksum = checksum
        self.deleted: list[str] = []

    async def upload(self, object_key, data, length, content_type):
        assert data.read() == b"source"
        return {
            "bucket_name": "land-valuation",
            "object_key": object_key,
            "checksum_sha256": self.checksum,
            "file_size_bytes": length,
            "etag": "etag-1",
        }

    async def delete(self, object_key):
        self.deleted.append(object_key)

    async def object_exists(self, object_key):
        return object_key.startswith("knowledge/")


class FakeRepository:
    def __init__(self, existing_checksum: str | None = None) -> None:
        self.rule = SimpleNamespace(
            rule_version_id=uuid4(),
            rule_set_code="NTPC_JINSHAN_COMMERCIAL",
            version_no=1,
            status="DRAFT",
            jurisdiction_code="NEW_TAIPEI_CITY",
            effective_from=date(2026, 1, 1),
            effective_to=None,
        )
        self.existing_checksum = existing_checksum
        self.added_document = None
        self.added_link = None
        self.knowledge_document = None

    async def get(self, rule_version_id):
        return self.rule if rule_version_id == self.rule.rule_version_id else None

    async def next_source_order(self, rule_version_id):
        assert rule_version_id == self.rule.rule_version_id
        return 2

    async def next_version(self, rule_set_code):
        return 1

    async def list_sources(self, rule_version_id):
        if self.added_link is not None and self.knowledge_document is not None:
            return [(self.added_link, self.knowledge_document)]
        if self.existing_checksum is None:
            return []
        document = SimpleNamespace(
            checksum_sha256=self.existing_checksum,
            original_filename="existing.pdf",
        )
        return [(SimpleNamespace(), document)]

    async def add_source(self, document, source_link):
        source_link.rule_version_source_id = uuid4()
        document.created_at = datetime.now(timezone.utc)
        self.added_document = document
        self.added_link = source_link
        return source_link

    async def get_source(self, document_id):
        if self.knowledge_document and self.knowledge_document.document_id == document_id:
            return self.knowledge_document
        return None

    async def add_source_link(self, source_link):
        source_link.rule_version_source_id = uuid4()
        self.added_link = source_link
        return source_link

    async def create_rule_with_source_link(self, rule, source_link):
        now = datetime.now(timezone.utc)
        rule.created_at = now
        source_link.rule_version_source_id = uuid4()
        source_link.created_at = now
        self.rule = rule
        self.added_link = source_link
        return rule


def upload_file() -> UploadFile:
    return UploadFile(
        filename="土地徵收補償市價查估辦法.pdf",
        file=BytesIO(b"source"),
        headers={"content-type": "application/pdf"},
    )


@pytest.mark.asyncio
async def test_add_supplemental_rule_source_uses_same_versioned_prefix() -> None:
    repository = FakeRepository()
    storage = FakeStorage()
    service = RulePackService(None, storage, repository=repository)
    manifest = RulePackSourceManifest(
        source_role="LEGAL_BASIS",
        source_document_type="REGULATION",
        title="土地徵收補償市價查估辦法",
        source_reference="第十九條及第二十一條",
        page_reference="第19條、第21條",
        confirm_source_upload=True,
    )

    response = await service.add_source(
        repository.rule.rule_version_id,
        manifest,
        upload_file(),
        SimpleNamespace(user_id=uuid4()),
    )

    assert response.source_role == "LEGAL_BASIS"
    assert response.source_order == 2
    assert response.is_primary is False
    assert response.object_key.startswith(
        f"knowledge/rule-sources/{repository.rule.rule_version_id}/v1/"
    )
    assert repository.added_document.effective_from is None
    assert repository.added_document.metadata_["source_reference"] == (
        "第十九條及第二十一條"
    )
    assert storage.deleted == []


@pytest.mark.asyncio
async def test_duplicate_supplemental_source_is_removed_from_minio() -> None:
    checksum = "b" * 64
    repository = FakeRepository(existing_checksum=checksum)
    storage = FakeStorage(checksum=checksum)
    service = RulePackService(None, storage, repository=repository)
    manifest = RulePackSourceManifest(
        source_role="LEGAL_BASIS",
        source_document_type="REGULATION",
        title="重複來源",
        confirm_source_upload=True,
    )

    with pytest.raises(AppError) as exc_info:
        await service.add_source(
            repository.rule.rule_version_id,
            manifest,
            upload_file(),
            SimpleNamespace(user_id=uuid4()),
        )

    assert exc_info.value.code == "RULE_SOURCE_DUPLICATE"
    assert len(storage.deleted) == 1
    assert repository.added_document is None


@pytest.mark.asyncio
async def test_existing_knowledge_document_can_be_linked_without_reupload() -> None:
    repository = FakeRepository()
    now = datetime.now(timezone.utc)
    repository.knowledge_document = SimpleNamespace(
        document_id=uuid4(),
        document_type="MANUAL",
        title="新北市土地徵收補償市價查估書表製作手冊",
        original_filename="新北市查估書表製作手冊.pdf",
        mime_type="application/pdf",
        bucket_name="land-valuation",
        object_key="knowledge/manuals/document-id/v1/manual.pdf",
        checksum_sha256="c" * 64,
        file_size_bytes=1234,
        storage_etag="etag-existing",
        metadata_={},
        publication_status="DRAFT",
        created_at=now,
    )
    storage = FakeStorage()
    service = RulePackService(None, storage, repository=repository)

    from app.valuation.rule_packs.schemas import ExistingRulePackSourceLinkRequest

    response = await service.link_existing_source(
        repository.rule.rule_version_id,
        ExistingRulePackSourceLinkRequest(
            source_document_id=repository.knowledge_document.document_id,
            source_role="LOCAL_MANUAL",
            source_reference="第5章至第8章",
            page_reference="第41頁至第69頁",
            confirm_link=True,
        ),
        SimpleNamespace(user_id=uuid4()),
    )

    assert response.source_role == "LOCAL_MANUAL"
    assert response.source_reference == "第5章至第8章"
    assert response.object_key.startswith("knowledge/manuals/")
    assert repository.added_document is None


@pytest.mark.asyncio
async def test_example_reference_cannot_be_primary_rule_source() -> None:
    repository = FakeRepository()
    now = datetime.now(timezone.utc)
    repository.knowledge_document = SimpleNamespace(
        document_id=uuid4(),
        document_type="EXAMPLE_REFERENCE",
        title="評價基準明細表範例",
        original_filename="評價基準明細表範例.pdf",
        mime_type="application/pdf",
        bucket_name="land-valuation",
        object_key="knowledge/standards/document-id/v1/standard.pdf",
        checksum_sha256="d" * 64,
        file_size_bytes=2345,
        storage_etag="etag-existing",
        metadata_={},
        publication_status="DRAFT",
        created_at=now,
    )
    service = RulePackService(None, FakeStorage(), repository=repository)

    from app.valuation.rule_packs.schemas import ExistingKnowledgeRulePackCreateRequest

    with pytest.raises(AppError) as exc_info:
        await service.create_from_existing_source(
            ExistingKnowledgeRulePackCreateRequest(
                source_document_id=repository.knowledge_document.document_id,
                rule_set_code="NTPC_RULE_DRAFT",
                version_name="等待確認的規則草稿",
                effective_date_status="UNKNOWN",
                land_use_types=["RESIDENTIAL", "COMMERCIAL"],
                source_reference="由使用者後續確認頁碼",
                confirm_source_link=True,
            ),
            SimpleNamespace(user_id=uuid4()),
        )

    assert exc_info.value.code == "EXAMPLE_REFERENCE_NOT_RULE_SOURCE"
    assert repository.added_link is None


@pytest.mark.asyncio
async def test_formal_existing_standard_can_be_primary_without_reupload() -> None:
    repository = FakeRepository()
    now = datetime.now(timezone.utc)
    repository.knowledge_document = SimpleNamespace(
        document_id=uuid4(),
        document_type="STANDARD",
        title="新北市正式評價基準明細表",
        original_filename="新北市正式評價基準明細表.pdf",
        mime_type="application/pdf",
        bucket_name="land-valuation",
        object_key="knowledge/standards/document-id/v1/standard.pdf",
        checksum_sha256="e" * 64,
        file_size_bytes=2345,
        storage_etag="etag-existing",
        metadata_={"formal_rule_eligible": True},
        publication_status="DRAFT",
        created_at=now,
    )
    service = RulePackService(None, FakeStorage(), repository=repository)

    from app.valuation.rule_packs.schemas import ExistingKnowledgeRulePackCreateRequest

    response = await service.create_from_existing_source(
        ExistingKnowledgeRulePackCreateRequest(
            source_document_id=repository.knowledge_document.document_id,
            rule_set_code="NTPC_RULE_DRAFT",
            version_name="正式規則草稿",
            effective_date_status="UNKNOWN",
            land_use_types=["RESIDENTIAL"],
            confirm_source_link=True,
        ),
        SimpleNamespace(user_id=uuid4()),
    )

    assert response.status == "DRAFT"
    assert response.source_count == 1
    assert response.source_object_key.startswith("knowledge/standards/")
    assert repository.rule.district_scope == {"mode": "ALL", "district_codes": []}
