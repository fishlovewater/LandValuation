"""Read MinIO knowledge files on demand without changing document status.

This is intentionally a read-only runtime path.  It creates transient chunks
for a request and never writes ``knowledge.chunks`` or changes a document from
``PENDING`` to ``COMPLETED``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
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
    metadata_: dict | None = field(default_factory=dict)
    object_size_bytes: int | None = None


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


class RuntimeExtractionError(ValueError):
    def __init__(self, message: str, *, bytes_read: int = 0):
        super().__init__(message)
        self.bytes_read = max(0, bytes_read)


class NoReadableTextError(RuntimeExtractionError):
    """A source exists but needs OCR or a supported parser."""


class RuntimeExtractionLimitError(RuntimeExtractionError):
    """A source exceeded a configured runtime extraction limit."""


class RuntimeKnowledgeExtractor:
    """Build per-request chunks from MinIO objects without persistent writes."""

    def __init__(self, storage: StorageService, settings=None):
        self.storage = storage
        settings = settings or get_settings()
        self.max_objects = settings.knowledge_runtime_max_objects
        self.max_object_bytes = settings.knowledge_runtime_max_object_bytes
        self.max_total_bytes = settings.knowledge_runtime_max_total_bytes
        self.max_total_characters = settings.knowledge_runtime_max_total_characters

    async def extract(self, documents: list[object]) -> RuntimeExtractionResult:
        results: list[RetrievedKnowledge] = []
        unreadable_sources: list[UnreadableRuntimeSource] = []
        total_bytes = 0
        total_characters = 0
        for index, document in enumerate(documents):
            if index >= self.max_objects:
                unreadable_sources.append(
                    self._unreadable(document, "已達本次知識文件物件數上限，未下載此來源。")
                )
                break
            declared_size = self._declared_size(document)
            if declared_size is not None and declared_size > self.max_object_bytes:
                unreadable_sources.append(
                    self._unreadable(document, "文件超過單一文件大小上限，未下載此來源。")
                )
                continue
            remaining_bytes = self.max_total_bytes - total_bytes
            if remaining_bytes <= 0:
                unreadable_sources.append(
                    self._unreadable(document, "已達本次知識文件總大小上限，未下載此來源。")
                )
                continue
            if declared_size is not None and declared_size > remaining_bytes:
                unreadable_sources.append(
                    self._unreadable(document, "會超過本次知識文件總大小上限，未下載此來源。")
                )
                continue
            if total_characters >= self.max_total_characters:
                unreadable_sources.append(
                    self._unreadable(document, "已達本次知識文字總字元上限，未處理此來源。")
                )
                continue
            bytes_counted = 0
            try:
                pages, bytes_read = await self._extract_pages(
                    document, min(self.max_object_bytes, remaining_bytes)
                )
                total_bytes += bytes_read
                bytes_counted = bytes_read
                chunks = self._chunks(
                    document,
                    pages,
                    max_characters=self.max_total_characters - total_characters,
                )
                if not chunks:
                    raise NoReadableTextError("文件沒有可擷取的文字；掃描型 PDF 需要 OCR。")
            except RuntimeExtractionError as exc:
                if not bytes_counted:
                    total_bytes += min(exc.bytes_read, remaining_bytes)
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
            total_characters += sum(len(item.chunk.content) for item in chunks)
            results.extend(chunks)
        return RuntimeExtractionResult(results, unreadable_sources)

    async def candidates(self, documents: list[object]) -> list[RetrievedKnowledge]:
        """Compatibility helper for callers that only need readable chunks."""

        return (await self.extract(documents)).candidates

    async def _extract_pages(
        self, document: object, max_bytes: int | None = None
    ) -> tuple[list[tuple[int | None, str]], int]:
        if max_bytes is None:
            max_bytes = self.max_object_bytes
        response = await self.storage.download(document.object_key)
        try:
            data = await run_in_threadpool(self._read_limited, response, max_bytes)
        finally:
            response.close()
            response.release_conn()

        if len(data) > max_bytes:
            raise RuntimeExtractionLimitError(
                "文件超過單一請求可讀取的 bytes 上限，未解析此來源。",
                bytes_read=len(data),
            )

        suffix = PurePosixPath(document.original_filename).suffix.lower()
        try:
            if suffix == ".pdf" or getattr(document, "mime_type", "") == "application/pdf":
                return await run_in_threadpool(self._pdf_pages, data), len(data)
            if suffix in {".txt", ".md", ".csv"}:
                return [(None, data.decode("utf-8-sig", errors="replace"))], len(data)
        except RuntimeExtractionError:
            raise
        except Exception as exc:
            raise RuntimeExtractionError(
                "檔案無法解析；請確認檔案格式、完整性或 OCR 設定。",
                bytes_read=len(data),
            ) from exc
        raise NoReadableTextError(
            f"目前不支援 {suffix or '此'} 檔案格式的文字擷取。",
            bytes_read=len(data),
        )

    @staticmethod
    def _read_limited(response: object, max_bytes: int) -> bytes:
        remaining = max_bytes + 1
        data = bytearray()
        while remaining:
            chunk = response.read(remaining)
            if not chunk:
                break
            if len(chunk) >= remaining:
                data.extend(chunk[:remaining])
                break
            data.extend(chunk)
            remaining -= len(chunk)
        return bytes(data)

    @staticmethod
    def _pdf_pages(data: bytes) -> list[tuple[int | None, str]]:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return [(index, page.extract_text() or "") for index, page in enumerate(reader.pages, start=1)]

    @staticmethod
    def _chunks(
        document: object,
        pages: list[tuple[int | None, str]],
        *,
        max_characters: int | None = None,
    ) -> list[RetrievedKnowledge]:
        results: list[RetrievedKnowledge] = []
        chunk_no = 0
        remaining_characters = max_characters
        for page_number, page_text in pages:
            normalized = "\n".join(line.strip() for line in page_text.splitlines() if line.strip())
            for offset in range(0, len(normalized), _CHUNK_CHARACTERS):
                if remaining_characters is not None and remaining_characters <= 0:
                    return results
                content = normalized[offset : offset + _CHUNK_CHARACTERS]
                if remaining_characters is not None:
                    content = content[:remaining_characters]
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
                if remaining_characters is not None:
                    remaining_characters -= len(content)
        return results

    @staticmethod
    def _declared_size(document: object) -> int | None:
        for name in ("object_size_bytes", "file_size_bytes", "size"):
            value = getattr(document, name, None)
            if isinstance(value, bool) or value is None:
                continue
            try:
                size = int(value)
            except (TypeError, ValueError):
                continue
            if size >= 0:
                return size
        return None

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
        object_size_bytes=getattr(object_info, "size", None),
    )
