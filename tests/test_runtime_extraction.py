from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.knowledge.runtime_extraction import RuntimeKnowledgeExtractor


class _Response:
    def __init__(self, data: bytes):
        self.data = data
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self.data

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _Storage:
    def __init__(self, response: _Response):
        self.response = response

    async def download(self, _object_key: str) -> _Response:
        return self.response


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
