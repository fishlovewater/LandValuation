from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi.concurrency import run_in_threadpool
from pypdf import PdfReader
from sqlalchemy import func, select

from app.auth.models import User
from app.core.config import get_settings
from app.db.session import AsyncSessionFactory, dispose_engine
from app.knowledge.models import KnowledgeChunk, KnowledgeDocumentRecord
from app.storage.client import get_minio_client
from app.storage.service import StorageService

_CHUNK_CHARACTERS = 2800
_ARTICLE_PATTERN = re.compile(r"第\s*[0-9一二三四五六七八九十百千之\-]+\s*條")


@dataclass(frozen=True)
class OfficialSourceSpec:
    document_code: str
    filename: str
    title: str
    document_type: str
    source_revision_date: str | None = None
    force_ocr: bool = False

    @property
    def object_key(self) -> str:
        return f"knowledge/official/{self.filename}"


OFFICIAL_SOURCES: tuple[OfficialSourceSpec, ...] = (
    OfficialSourceSpec(
        document_code="LAW-LAND-EXPROPRIATION",
        filename="土地徵收條例.pdf",
        title="土地徵收條例",
        document_type="REGULATION",
        source_revision_date="2012-01-04",
    ),
    OfficialSourceSpec(
        document_code="LAW-LAND-EXPROPRIATION-ENFORCEMENT",
        filename="土地徵收條例施行細則.pdf",
        title="土地徵收條例施行細則",
        document_type="REGULATION",
        source_revision_date="2019-12-16",
    ),
    OfficialSourceSpec(
        document_code="REG-LAND-EXPROPRIATION-MARKET-VALUE",
        filename="土地徵收補償市價查估辦法.pdf",
        title="土地徵收補償市價查估辦法",
        document_type="REGULATION",
        source_revision_date="2014-11-14",
    ),
    OfficialSourceSpec(
        document_code="MANUAL-MOI-MARKET-VALUE-2015",
        filename="土地徵收補償市價查估作業手冊.pdf",
        title="土地徵收補償市價查估作業手冊",
        document_type="MANUAL",
        source_revision_date="2015-03",
    ),
    OfficialSourceSpec(
        document_code="MANUAL-NTPC-FORMS-CH4-10",
        filename="新北市土地徵收補償市價查估書表製作手冊4-10章.pdf",
        title="新北市土地徵收補償市價查估書表製作手冊第4至10章",
        document_type="MANUAL",
        force_ocr=True,
    ),
    OfficialSourceSpec(
        document_code="MANUAL-NTPC-FORMS-CH11",
        filename="新北市土地徵收補償市價查估書表製作手冊11章(提案表範例).pdf",
        title="新北市土地徵收補償市價查估書表製作手冊第11章（提案表範例）",
        document_type="MANUAL",
        force_ocr=True,
    ),
)


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    method: str


@dataclass(frozen=True)
class ChunkPayload:
    chunk_id: UUID
    chunk_no: int
    content: str
    page_number: int
    section_title: str | None
    article_no: str | None
    checksum_sha256: str
    extraction_method: str


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = "".join(
        char
        for char in normalized
        if char in {"\n", "\t"} or unicodedata.category(char)[0] != "C"
    )
    lines = [" ".join(line.split()) for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _extract_text_pages(pdf_bytes: bytes) -> list[ExtractedPage]:
    reader = PdfReader(BytesIO(pdf_bytes))
    return [
        ExtractedPage(
            page_number=index,
            text=_normalize_text(page.extract_text() or ""),
            method="PDF_TEXT",
        )
        for index, page in enumerate(reader.pages, start=1)
    ]


def _require_ocr_tools() -> None:
    missing = [name for name in ("pdftoppm", "tesseract") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "OCR tools are required for official manual indexing: " + ", ".join(missing)
        )


def _ocr_pages(
    pdf_bytes: bytes,
    *,
    languages: str,
    dpi: int,
    psm: int,
) -> list[ExtractedPage]:
    _require_ocr_tools()
    page_count = len(PdfReader(BytesIO(pdf_bytes)).pages)
    results: list[ExtractedPage] = []
    with tempfile.TemporaryDirectory(prefix="knowledge-official-") as temp_dir:
        temp_path = Path(temp_dir)
        pdf_path = temp_path / "source.pdf"
        pdf_path.write_bytes(pdf_bytes)
        for page_number in range(1, page_count + 1):
            prefix = temp_path / f"page-{page_number:04d}"
            subprocess.run(
                [
                    "pdftoppm",
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-r",
                    str(dpi),
                    "-png",
                    "-singlefile",
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=90,
            )
            image_path = prefix.with_suffix(".png")
            completed = subprocess.run(
                [
                    "tesseract",
                    str(image_path),
                    "stdout",
                    "-l",
                    languages,
                    "--psm",
                    str(psm),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=90,
            )
            text = _normalize_text(completed.stdout.decode("utf-8", errors="replace"))
            image_path.unlink(missing_ok=True)
            results.append(
                ExtractedPage(
                    page_number=page_number,
                    text=text,
                    method="OCR",
                )
            )
    return results


def _section_title(text: str) -> str | None:
    if not text:
        return None
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:300] or None


def _article_no(text: str) -> str | None:
    match = _ARTICLE_PATTERN.search(text)
    return " ".join(match.group(0).split()) if match else None


def build_chunks(document_id: UUID, pages: list[ExtractedPage]) -> list[ChunkPayload]:
    chunks: list[ChunkPayload] = []
    chunk_no = 0
    for page in pages:
        if not page.text:
            continue
        for offset in range(0, len(page.text), _CHUNK_CHARACTERS):
            content = page.text[offset : offset + _CHUNK_CHARACTERS].strip()
            if not content:
                continue
            chunk_no += 1
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunks.append(
                ChunkPayload(
                    chunk_id=uuid5(
                        NAMESPACE_URL,
                        f"official-knowledge:{document_id}:{page.page_number}:{offset}:{content_hash}",
                    ),
                    chunk_no=chunk_no,
                    content=content,
                    page_number=page.page_number,
                    section_title=_section_title(page.text),
                    article_no=_article_no(content),
                    checksum_sha256=content_hash,
                    extraction_method=page.method,
                )
            )
    return chunks


async def _read_object(storage: StorageService, object_key: str) -> bytes:
    response = await storage.download(object_key)
    try:
        return await run_in_threadpool(response.read)
    finally:
        response.close()
        response.release_conn()


async def _approver_id(username: str) -> UUID:
    async with AsyncSessionFactory() as session:
        user_id = await session.scalar(
            select(User.user_id).where(User.username == username, User.is_active.is_(True))
        )
        if user_id is None:
            raise RuntimeError(f"active approval user not found: {username}")
        return user_id


async def _index_source(
    spec: OfficialSourceSpec,
    *,
    storage: StorageService,
    approver_id: UUID,
    object_info: object,
    languages: str,
    ocr_dpi: int,
    ocr_psm: int,
) -> dict[str, object]:
    pdf_bytes = await _read_object(storage, spec.object_key)
    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    document_id = uuid5(NAMESPACE_URL, f"official-knowledge:{spec.document_code}:v1")

    async with AsyncSessionFactory() as session:
        existing = await session.scalar(
            select(KnowledgeDocumentRecord).where(
                KnowledgeDocumentRecord.object_key == spec.object_key
            )
        )
        if existing is not None and existing.checksum_sha256.strip() != checksum:
            raise RuntimeError(
                f"published official source changed in place: {spec.object_key}; "
                "store the new official version under a new object key/version instead"
            )
        if existing is not None:
            chunk_count = await session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == existing.document_id)
            )
            if (
                existing.extraction_status == "COMPLETED"
                and existing.publication_status == "PUBLISHED"
                and (chunk_count or 0) > 0
            ):
                return {
                    "document_code": spec.document_code,
                    "title": spec.title,
                    "status": "SKIPPED_ALREADY_INDEXED",
                    "pages": None,
                    "chunks": int(chunk_count or 0),
                }

    if spec.force_ocr:
        pages = await run_in_threadpool(
            _ocr_pages,
            pdf_bytes,
            languages=languages,
            dpi=ocr_dpi,
            psm=ocr_psm,
        )
    else:
        pages = await run_in_threadpool(_extract_text_pages, pdf_bytes)
    chunks = build_chunks(document_id, pages)
    if not chunks:
        raise RuntimeError(f"no readable text extracted from {spec.filename}")

    now = datetime.now(UTC)
    metadata = {
        "source_usage": "OFFICIAL_REFERENCE",
        "formal_rule_eligible": True,
        "importer": "app.knowledge.import_official",
        "source_revision_date": spec.source_revision_date,
        "extraction_methods": sorted({page.method for page in pages if page.text}),
        "page_count": len(pages),
    }

    async with AsyncSessionFactory() as session:
        existing = await session.scalar(
            select(KnowledgeDocumentRecord).where(
                KnowledgeDocumentRecord.object_key == spec.object_key
            )
        )
        if existing is None:
            document = KnowledgeDocumentRecord(
                document_id=document_id,
                document_code=spec.document_code,
                title=spec.title,
                document_type=spec.document_type,
                original_filename=spec.filename,
                mime_type="application/pdf",
                bucket_name=storage.bucket,
                object_key=spec.object_key,
                checksum_sha256=checksum,
                file_size_bytes=len(pdf_bytes),
                storage_etag=getattr(object_info, "etag", None),
                version_no=1,
                effective_from=None,
                effective_to=None,
                extraction_status="COMPLETED",
                metadata_=metadata,
                created_by_user_id=approver_id,
                publication_status="PUBLISHED",
                approved_by_user_id=approver_id,
                approved_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(document)
        else:
            document = existing
            document.document_code = spec.document_code
            document.title = spec.title
            document.document_type = spec.document_type
            document.original_filename = spec.filename
            document.mime_type = "application/pdf"
            document.bucket_name = storage.bucket
            document.checksum_sha256 = checksum
            document.file_size_bytes = len(pdf_bytes)
            document.storage_etag = getattr(object_info, "etag", None)
            document.extraction_status = "COMPLETED"
            document.metadata_ = metadata
            document.publication_status = "PUBLISHED"
            document.approved_by_user_id = approver_id
            document.approved_at = now
            document.updated_at = now

        existing_chunk_ids = set(
            (
                await session.scalars(
                    select(KnowledgeChunk.chunk_id).where(
                        KnowledgeChunk.document_id == document.document_id
                    )
                )
            ).all()
        )
        for payload in chunks:
            if payload.chunk_id in existing_chunk_ids:
                continue
            session.add(
                KnowledgeChunk(
                    chunk_id=payload.chunk_id,
                    document_id=document.document_id,
                    chunk_no=payload.chunk_no,
                    content=payload.content,
                    page_start=payload.page_number,
                    page_end=payload.page_number,
                    section_title=payload.section_title,
                    article_no=payload.article_no,
                    token_count=None,
                    content_checksum_sha256=payload.checksum_sha256,
                    metadata_json={"extraction_method": payload.extraction_method},
                    created_at=now,
                )
            )
        await session.commit()

    return {
        "document_code": spec.document_code,
        "title": spec.title,
        "status": "INDEXED",
        "pages": len(pages),
        "chunks": len(chunks),
        "extraction_methods": sorted({page.method for page in pages if page.text}),
    }


async def index_official_sources(
    *,
    approved_by_username: str,
    languages: str,
    ocr_dpi: int,
    ocr_psm: int,
) -> list[dict[str, object]]:
    storage = StorageService(get_minio_client())
    object_infos = {
        item.object_name: item
        for item in await storage.list_objects("knowledge/")
        if not item.object_name.endswith("/")
    }
    approver_id = await _approver_id(approved_by_username)
    results: list[dict[str, object]] = []
    for spec in OFFICIAL_SOURCES:
        object_info = object_infos.get(spec.object_key)
        if object_info is None:
            raise RuntimeError(f"official knowledge object missing from MinIO: {spec.object_key}")
        result = await _index_source(
            spec,
            storage=storage,
            approver_id=approver_id,
            object_info=object_info,
            languages=languages,
            ocr_dpi=ocr_dpi,
            ocr_psm=ocr_psm,
        )
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return results


def _parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Index the fixed official land-valuation knowledge PDFs already stored in MinIO."
    )
    parser.add_argument("--approved-by-username", default="valuation_demo")
    parser.add_argument("--ocr-languages", default=settings.local_ocr_languages)
    parser.add_argument("--ocr-dpi", type=int, default=180)
    parser.add_argument("--ocr-psm", type=int, default=6)
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    try:
        results = await index_official_sources(
            approved_by_username=args.approved_by_username,
            languages=args.ocr_languages,
            ocr_dpi=args.ocr_dpi,
            ocr_psm=args.ocr_psm,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "documents": len(results),
                    "indexed": sum(item["status"] == "INDEXED" for item in results),
                    "skipped": sum(
                        item["status"] == "SKIPPED_ALREADY_INDEXED" for item in results
                    ),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
