"""Import the project-approved PDF source library into PostgreSQL and MinIO.

The manifest is authoritative for classification only. The importer does not infer
effective dates, publish documents, extract text, or create valuation rules.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import selectors
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select

from app.db.session import AsyncSessionFactory, dispose_engine
from app.knowledge.models import KnowledgeDocumentRecord
from app.storage.client import get_minio_client
from app.storage.service import StorageService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "knowledge_sources_manifest.json"
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "需要放入MINIO的東西"
DOCUMENT_NAMESPACE = UUID("b3e83cd2-d97b-4478-95a2-4c95981f0992")
CATEGORY_TYPES = {
    "regulations": frozenset({"REGULATION"}),
    "standards": frozenset({"STANDARD", "EXAMPLE_REFERENCE"}),
    "manuals": frozenset({"MANUAL"}),
}


@dataclass(frozen=True)
class SourceSpec:
    filename: str
    category: str
    document_type: str
    version_no: int

    @property
    def document_code(self) -> str:
        digest = hashlib.sha256(self.filename.encode("utf-8")).hexdigest()[:24]
        return f"PROJECT_SOURCE_{digest.upper()}"

    @property
    def document_id(self) -> UUID:
        return uuid5(DOCUMENT_NAMESPACE, f"{self.document_code}:v{self.version_no}")

    @property
    def object_key(self) -> str:
        return (
            f"knowledge/{self.category}/{self.document_id}/"
            f"v{self.version_no}/{self.filename}"
        )


def _load_manifest(path: Path) -> list[SourceSpec]:
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"無法讀取來源 manifest：{path}") from exc

    if payload.get("manifest_version") != 1:
        raise ValueError("只支援 manifest_version=1")
    rows = payload.get("sources")
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest.sources 必須是非空陣列")

    specs: list[SourceSpec] = []
    filenames: set[str] = set()
    identities: set[tuple[str, int]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("每一筆來源必須是 object")
        filename = str(row.get("filename", "")).strip()
        category = str(row.get("category", "")).strip()
        document_type = str(row.get("document_type", "")).strip()
        version_no = row.get("version_no")
        if (
            not filename
            or Path(filename).name != filename
            or not filename.lower().endswith(".pdf")
        ):
            raise ValueError(f"不合法的 PDF 檔名：{filename!r}")
        if category not in CATEGORY_TYPES:
            raise ValueError(f"不支援的知識分類：{category}")
        if document_type not in CATEGORY_TYPES[category]:
            raise ValueError(f"{filename} 的 category 與 document_type 不一致")
        if not isinstance(version_no, int) or version_no <= 0:
            raise ValueError(f"{filename} 的 version_no 必須是正整數")
        identity = (filename, version_no)
        if filename in filenames or identity in identities:
            raise ValueError(f"manifest 有重複來源：{filename}")
        filenames.add(filename)
        identities.add(identity)
        specs.append(SourceSpec(filename, category, document_type, version_no))
    return specs


def _file_sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


async def _stored_sha256(storage: StorageService, object_key: str) -> str:
    response = await storage.download(object_key)
    checksum = hashlib.sha256()
    try:
        for chunk in response.stream(1024 * 1024):
            checksum.update(chunk)
    finally:
        response.close()
        response.release_conn()
    return checksum.hexdigest()


def _validate_files(specs: list[SourceSpec], source_dir: Path) -> dict[str, tuple[Path, str, int]]:
    values: dict[str, tuple[Path, str, int]] = {}
    for spec in specs:
        path = source_dir / spec.filename
        if not path.is_file():
            raise ValueError(f"缺少 manifest 指定原檔：{path}")
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"原檔不可為空：{path}")
        values[spec.filename] = (path, _file_sha256(path), size)
    return values


async def _import(
    specs: list[SourceSpec],
    files: dict[str, tuple[Path, str, int]],
) -> dict[str, int]:
    storage = StorageService(get_minio_client())
    if not await storage.bucket_ready():
        raise RuntimeError("MinIO land-valuation bucket 不存在")

    created = 0
    repaired = 0
    reclassified = 0
    unchanged = 0
    uploaded_this_run: list[str] = []
    try:
        async with AsyncSessionFactory() as session:
            for spec in specs:
                path, checksum, size = files[spec.filename]
                existing = await session.scalar(
                    select(KnowledgeDocumentRecord).where(
                        KnowledgeDocumentRecord.document_code == spec.document_code,
                        KnowledgeDocumentRecord.version_no == spec.version_no,
                    )
                )
                if existing is not None:
                    expected = {
                        "document_id": spec.document_id,
                        "original_filename": spec.filename,
                        "bucket_name": "land-valuation",
                        "object_key": spec.object_key,
                        "checksum_sha256": checksum,
                    }
                    mismatches = [
                        name
                        for name, value in expected.items()
                        if getattr(existing, name) != value
                    ]
                    if mismatches:
                        raise RuntimeError(
                            f"既有 metadata 與 manifest／原檔不一致：{spec.filename} "
                            f"({', '.join(mismatches)})"
                        )
                    if existing.document_type != spec.document_type:
                        if not (
                            existing.document_type == "STANDARD"
                            and spec.document_type == "EXAMPLE_REFERENCE"
                        ):
                            raise RuntimeError(
                                "既有 document_type 不可自動改寫："
                                f"{spec.filename} ({existing.document_type} -> "
                                f"{spec.document_type})"
                            )
                        existing.document_type = spec.document_type
                        existing.metadata_ = {
                            **(existing.metadata_ or {}),
                            "source_usage": "EXAMPLE_REFERENCE",
                            "formal_rule_eligible": False,
                        }
                        reclassified += 1

                object_exists = await storage.object_exists(spec.object_key)
                if object_exists:
                    if await _stored_sha256(storage, spec.object_key) != checksum:
                        raise RuntimeError(
                            f"MinIO 同 key 物件內容不同，拒絕覆寫：{spec.object_key}"
                        )
                else:
                    with path.open("rb") as stream:
                        uploaded = await storage.upload(
                            spec.object_key,
                            stream,
                            size,
                            "application/pdf",
                        )
                    if uploaded["checksum_sha256"] != checksum:
                        await storage.delete(spec.object_key)
                        raise RuntimeError(f"上傳後 SHA-256 不一致：{spec.filename}")
                    uploaded_this_run.append(spec.object_key)

                if existing is None:
                    session.add(
                        KnowledgeDocumentRecord(
                            document_id=spec.document_id,
                            document_code=spec.document_code,
                            title=Path(spec.filename).stem,
                            document_type=spec.document_type,
                            original_filename=spec.filename,
                            mime_type="application/pdf",
                            bucket_name="land-valuation",
                            object_key=spec.object_key,
                            checksum_sha256=checksum,
                            file_size_bytes=size,
                            storage_etag=(uploaded.get("etag") if not object_exists else None),
                            version_no=spec.version_no,
                            effective_from=None,
                            effective_to=None,
                            extraction_status="PENDING",
                            metadata_={
                                "classification_source": "MinIO使用手冊_HackMD.md",
                                "effective_date_status": "UNKNOWN",
                                "source_usage": spec.document_type,
                                "formal_rule_eligible": (
                                    spec.document_type != "EXAMPLE_REFERENCE"
                                ),
                            },
                            publication_status="DRAFT",
                        )
                    )
                    created += 1
                elif not object_exists:
                    existing.storage_etag = str(uploaded.get("etag"))
                    repaired += 1
                else:
                    unchanged += 1
            await session.commit()
    except Exception:
        for object_key in reversed(uploaded_this_run):
            try:
                await storage.delete(object_key)
            except Exception:
                pass
        raise
    finally:
        await dispose_engine()
    return {
        "created": created,
        "repaired": repaired,
        "reclassified": reclassified,
        "unchanged": unchanged,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    specs = _load_manifest(args.manifest.resolve())
    files = _validate_files(specs, args.source_dir.resolve())
    category_counts = {
        category: sum(spec.category == category for spec in specs)
        for category in CATEGORY_TYPES
    }
    document_type_counts = {
        document_type: sum(spec.document_type == document_type for spec in specs)
        for document_type in sorted(
            {spec.document_type for spec in specs}
        )
    }
    if args.dry_run:
        print(
            json.dumps(
                {
                    "validated": len(specs),
                    "categories": category_counts,
                    "document_types": document_type_counts,
                },
                ensure_ascii=False,
            )
        )
        return
    if sys.platform == "win32":
        result = asyncio.run(
            _import(specs, files),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        result = asyncio.run(_import(specs, files))
    print(
        json.dumps(
            {
                "validated": len(specs),
                "categories": category_counts,
                "document_types": document_type_counts,
                **result,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
