"""Read MinIO knowledge files on demand without changing document status.

This is intentionally a read-only runtime path.  It creates transient chunks
for a request and never writes ``knowledge.chunks`` or changes a document from
``PENDING`` to ``COMPLETED``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi.concurrency import run_in_threadpool

from app.knowledge.service import RetrievedKnowledge
from app.storage.service import StorageService

logger = logging.getLogger(__name__)
_CHUNK_CHARACTERS = 3_000


@dataclass(frozen=True)
class RuntimeKnowledgeChunk:
    chunk_id: UUID
    chunk_no: int
    content: str
    page_start: int | None
    page_end: int | None
    section_title: str | None = None
    article_no: str | None = None


@dataclass(frozen=True)
class VirtualKnowledgeDocument:
    """Read-only metadata for a MinIO object that has no database row yet."""

    document_id: UUID
    document_code: str
    title: str
    document_type: str
    original_filename: str
    mime_type: str
    bucket_name: str
    object_key: str
    version_no: int = 1
    effective_from: None = None
    effective_to: None = None


@dataclass(frozen=True)
class UnreadableRuntimeSource:
    document_id: UUID
    document_title: str
    original_filename: str
    reason: str


@dataclass(frozen=True)
class RuntimeExtractionResult:
    candidates: list[RetrievedKnowledge]
    unreadable_sources: list[UnreadableRuntimeSource]


class NoReadableTextError(ValueError):
    """A source exists but needs OCR or a supported parser."""


class RuntimeKnowledgeExtractor:
    """Build per-request chunks from MinIO objects without persistent writes."""

    def __init__(self, storage: StorageService):
        self.storage = storage

    async def extract(self, documents: list[object]) -> RuntimeExtractionResult:
        results: list[RetrievedKnowledge] = []
        unreadable_sources: list[UnreadableRuntimeSource] = []
        for document in documents:
            try:
                pages = await self._extract_pages(document)
                chunks = self._chunks(document, pages)
                if not chunks:
                    raise NoReadableTextError("文件沒有可擷取的文字；掃描型 PDF 需要 OCR。")
            except NoReadableTextError as exc:
                unreadable_sources.append(self._unreadable(document, str(exc)))
                continue
            except Exception:  # A single unreadable source must not block other sources.
                logger.exception(
                    "Knowledge source could not be read on demand",
                    extra={"document_id": str(document.document_id)},
                )
                unreadable_sources.append(
                    self._unreadable(document, "檔案無法解析；請確認檔案格式、完整性或 OCR 設定。")
                )
                continue
            results.extend(chunks)
        return RuntimeExtractionResult(results, unreadable_sources)

    async def candidates(self, documents: list[object]) -> list[RetrievedKnowledge]:
        """Compatibility helper for callers that only need readable chunks."""

        return (await self.extract(documents)).candidates

    async def _extract_pages(self, document: object) -> list[tuple[int | None, str]]:
        response = await self.storage.download(document.object_key)
        try:
            data = await run_in_threadpool(response.read)
        finally:
            response.close()
            response.release_conn()

        suffix = PurePosixPath(document.original_filename).suffix.lower()
        if suffix == ".pdf" or getattr(document, "mime_type", "") == "application/pdf":
            return await run_in_threadpool(self._pdf_pages, data)
        if suffix in {".txt", ".md", ".csv"}:
            return [(None, data.decode("utf-8-sig", errors="replace"))]
        raise NoReadableTextError(f"目前不支援 {suffix or '此'} 檔案格式的文字擷取。")

    @staticmethod
    def _pdf_pages(data: bytes) -> list[tuple[int | None, str]]:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return [(index, page.extract_text() or "") for index, page in enumerate(reader.pages, start=1)]

    @staticmethod
    def _chunks(document: object, pages: list[tuple[int | None, str]]) -> list[RetrievedKnowledge]:
        results: list[RetrievedKnowledge] = []
        chunk_no = 0
        for page_number, page_text in pages:
            normalized = "\n".join(line.strip() for line in page_text.splitlines() if line.strip())
            for offset in range(0, len(normalized), _CHUNK_CHARACTERS):
                content = normalized[offset : offset + _CHUNK_CHARACTERS]
                if not content:
                    continue
                chunk_no += 1
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                chunk = RuntimeKnowledgeChunk(
                    chunk_id=uuid5(
                        NAMESPACE_URL,
                        f"runtime-knowledge:{document.document_id}:{page_number}:{offset}:{content_hash}",
                    ),
                    chunk_no=chunk_no,
                    content=content,
                    page_start=page_number,
                    page_end=page_number,
                )
                results.append(RetrievedKnowledge(document=document, chunk=chunk))
        return results

    @staticmethod
    def _unreadable(document: object, reason: str) -> UnreadableRuntimeSource:
        return UnreadableRuntimeSource(
            document_id=document.document_id,
            document_title=getattr(document, "title", document.original_filename),
            original_filename=document.original_filename,
            reason=reason,
        )


def virtual_document_from_object(bucket_name: str, object_info: object) -> VirtualKnowledgeDocument:
    """Create stable, in-memory metadata for every object under knowledge/."""

    object_key = object_info.object_name
    filename = PurePosixPath(object_key).name
    document_id = uuid5(NAMESPACE_URL, f"minio://{bucket_name}/{object_key}")
    stem = PurePosixPath(filename).stem
    digest = hashlib.sha256(object_key.encode("utf-8")).hexdigest()[:16].upper()
    return VirtualKnowledgeDocument(
        document_id=document_id,
        document_code=f"MINIO-{digest}",
        title=stem or filename,
        document_type="OTHER",
        original_filename=filename,
        mime_type=getattr(object_info, "content_type", None) or "application/octet-stream",
        bucket_name=bucket_name,
        object_key=object_key,
    )
