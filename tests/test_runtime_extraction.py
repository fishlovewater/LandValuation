from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.knowledge.runtime_extraction import (
    RuntimeKnowledgeExtractor,
    virtual_document_from_object,
)


class _Response:
    def __init__(self, data: bytes):
        self.data = data
        self.closed = False
        self.released = False
        self.read_sizes = []
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            chunk = self.data[self.offset :]
        else:
            chunk = self.data[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _Storage:
    def __init__(self, response: _Response):
        self.response = response
        self.downloaded = []

    async def download(self, object_key: str) -> _Response:
        self.downloaded.append(object_key)
        return self.response


class _MappingStorage:
    def __init__(self, responses):
        self.responses = responses
        self.downloaded = []

    async def download(self, object_key: str) -> _Response:
        self.downloaded.append(object_key)
        return self.responses[object_key]


@pytest.mark.asyncio
async def test_pending_text_source_is_available_without_status_update() -> None:
    response = _Response("比較法應依實例差異調整。".encode())
    document = SimpleNamespace(
        document_id=uuid4(),
        object_key="knowledge/manuals/example/v1/guide.md",
        original_filename="guide.md",
        mime_type="text/markdown",
        extraction_status="PENDING",
        publication_status="DRAFT",
    )

    candidates = await RuntimeKnowledgeExtractor(_Storage(response)).candidates([document])

    assert len(candidates) == 1
    assert candidates[0].chunk.content == "比較法應依實例差異調整。"
    assert candidates[0].document.extraction_status == "PENDING"
    assert candidates[0].document.publication_status == "DRAFT"
    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_unreadable_source_is_reported_without_changing_status() -> None:
    response = _Response(b"not a supported knowledge format")
    document = SimpleNamespace(
        document_id=uuid4(),
        title="掃描文件",
        object_key="knowledge/manuals/example/v1/scan.bin",
        original_filename="scan.bin",
        mime_type="application/octet-stream",
        extraction_status="PENDING",
        publication_status="DRAFT",
    )

    result = await RuntimeKnowledgeExtractor(_Storage(response)).extract([document])

    assert result.candidates == []
    assert result.unreadable_sources[0].original_filename == "scan.bin"
    assert "不支援" in result.unreadable_sources[0].reason
    assert document.extraction_status == "PENDING"


@pytest.mark.asyncio
async def test_declared_oversized_source_is_rejected_before_download():
    storage = _Storage(_Response(b"must not be downloaded"))
    document = SimpleNamespace(
        document_id=uuid4(),
        object_key="knowledge/manuals/example/v1/large.txt",
        original_filename="large.txt",
        mime_type="text/plain",
        object_size_bytes=10 * 1024 * 1024 + 1,
    )

    result = await RuntimeKnowledgeExtractor(storage).extract([document])

    assert result.candidates == []
    assert storage.downloaded == []
    assert "大小" in result.unreadable_sources[0].reason


@pytest.mark.asyncio
async def test_runtime_extraction_limits_object_count_before_download():
    first_key = "knowledge/manuals/example/v1/first.txt"
    second_key = "knowledge/manuals/example/v1/second.txt"
    storage = _MappingStorage(
        {
            first_key: _Response(b"first"),
            second_key: _Response(b"second"),
        }
    )
    settings = SimpleNamespace(
        knowledge_runtime_max_objects=1,
        knowledge_runtime_max_object_bytes=100,
        knowledge_runtime_max_total_bytes=1000,
        knowledge_runtime_max_total_characters=1000,
    )
    documents = [
        SimpleNamespace(
            document_id=uuid4(),
            object_key=first_key,
            original_filename="first.txt",
            mime_type="text/plain",
        ),
        SimpleNamespace(
            document_id=uuid4(),
            object_key=second_key,
            original_filename="second.txt",
            mime_type="text/plain",
        ),
    ]

    result = await RuntimeKnowledgeExtractor(storage, settings=settings).extract(documents)

    assert [item.chunk.content for item in result.candidates] == ["first"]
    assert storage.downloaded == [first_key]
    assert "物件數上限" in result.unreadable_sources[0].reason


@pytest.mark.asyncio
async def test_runtime_extraction_limits_total_declared_bytes_before_download():
    first_key = "knowledge/manuals/example/v1/first.txt"
    second_key = "knowledge/manuals/example/v1/second.txt"
    storage = _MappingStorage(
        {
            first_key: _Response(b"123456"),
            second_key: _Response(b"abcdef"),
        }
    )
    settings = SimpleNamespace(
        knowledge_runtime_max_objects=10,
        knowledge_runtime_max_object_bytes=10,
        knowledge_runtime_max_total_bytes=10,
        knowledge_runtime_max_total_characters=1000,
    )
    documents = [
        SimpleNamespace(
            document_id=uuid4(),
            object_key=first_key,
            original_filename="first.txt",
            mime_type="text/plain",
            file_size_bytes=6,
        ),
        SimpleNamespace(
            document_id=uuid4(),
            object_key=second_key,
            original_filename="second.txt",
            mime_type="text/plain",
            file_size_bytes=6,
        ),
    ]

    result = await RuntimeKnowledgeExtractor(storage, settings=settings).extract(documents)

    assert [item.chunk.content for item in result.candidates] == ["123456"]
    assert storage.downloaded == [first_key]
    assert "總大小上限" in result.unreadable_sources[0].reason


@pytest.mark.asyncio
async def test_runtime_extraction_defensively_caps_unknown_size_downloads():
    response = _Response(b"abcdef")
    storage = _Storage(response)
    settings = SimpleNamespace(
        knowledge_runtime_max_objects=10,
        knowledge_runtime_max_object_bytes=4,
        knowledge_runtime_max_total_bytes=100,
        knowledge_runtime_max_total_characters=100,
    )
    document = SimpleNamespace(
        document_id=uuid4(),
        object_key="knowledge/manuals/example/v1/unknown.txt",
        original_filename="unknown.txt",
        mime_type="text/plain",
    )

    result = await RuntimeKnowledgeExtractor(storage, settings=settings).extract([document])

    assert result.candidates == []
    assert response.read_sizes == [5]
    assert "bytes" in result.unreadable_sources[0].reason


@pytest.mark.asyncio
async def test_runtime_extraction_counts_defensive_read_bytes_toward_total_limit():
    first_key = "knowledge/manuals/example/v1/unknown-large.txt"
    second_key = "knowledge/manuals/example/v1/second.txt"
    storage = _MappingStorage(
        {
            first_key: _Response(b"abcdef"),
            second_key: _Response(b"second"),
        }
    )
    settings = SimpleNamespace(
        knowledge_runtime_max_objects=10,
        knowledge_runtime_max_object_bytes=4,
        knowledge_runtime_max_total_bytes=5,
        knowledge_runtime_max_total_characters=100,
    )
    documents = [
        SimpleNamespace(
            document_id=uuid4(),
            object_key=first_key,
            original_filename="unknown-large.txt",
            mime_type="text/plain",
        ),
        SimpleNamespace(
            document_id=uuid4(),
            object_key=second_key,
            original_filename="second.txt",
            mime_type="text/plain",
        ),
    ]

    result = await RuntimeKnowledgeExtractor(storage, settings=settings).extract(documents)

    assert result.candidates == []
    assert storage.downloaded == [first_key]


@pytest.mark.asyncio
async def test_runtime_extraction_caps_total_extracted_characters():
    storage = _Storage(_Response(b"abcdefgh"))
    settings = SimpleNamespace(
        knowledge_runtime_max_objects=10,
        knowledge_runtime_max_object_bytes=100,
        knowledge_runtime_max_total_bytes=100,
        knowledge_runtime_max_total_characters=5,
    )
    document = SimpleNamespace(
        document_id=uuid4(),
        object_key="knowledge/manuals/example/v1/long.txt",
        original_filename="long.txt",
        mime_type="text/plain",
    )

    result = await RuntimeKnowledgeExtractor(storage, settings=settings).extract([document])

    assert sum(len(item.chunk.content) for item in result.candidates) == 5
    assert result.candidates[0].chunk.content == "abcde"


def test_virtual_document_keeps_minio_object_size_metadata():
    document = virtual_document_from_object(
        "land-valuation",
        SimpleNamespace(
            object_name="knowledge/manuals/example/v1/guide.md",
            content_type="text/markdown",
            size=1234,
        ),
    )

    assert document.object_size_bytes == 1234
