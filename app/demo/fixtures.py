"""Small immutable fixtures used by the persistent development Demo.

The builders in this module contain data only.  Database ownership, storage
uploads, and transaction boundaries stay in :mod:`app.demo.lifecycle`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from uuid import UUID, uuid4

DEMO_CASE_NO = "DEMO-F03-PERSISTENT-001"
DEMO_CASE_TITLE = "Persistent Four-Subsystem F03 Demo"
DEMO_KNOWLEDGE_CODE = "DEMO-F03-PERSISTENT-SOURCE"
DEMO_KNOWLEDGE_TITLE = "估價依據與查估程序示範來源"
SUPPORTED_QUESTION = "請說明目前案件的估價依據。"
NO_SOURCE_QUESTION = "此來源是否規範深海採礦設備折舊？"


@dataclass(frozen=True)
class KnowledgeFixture:
    code: str
    title: str
    content: str
    content_checksum_sha256: str
    page_start: int = 1
    page_end: int = 1
    section_title: str = "估價依據"
    article_no: str = "第 1 條"


@dataclass(frozen=True)
class F03Fixture:
    """The minimum structured F03 values needed by the Demo seed."""

    form_code: str
    form_content: dict[str, object]
    district_code: str
    section_name: str
    land_no: str
    area_sqm: str
    land_use_zone: str


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_content(content: str | bytes) -> str:
    value = content if isinstance(content, bytes) else content.encode("utf-8")
    return sha256_bytes(value)


def knowledge_source() -> KnowledgeFixture:
    """Return the one source that can support the stable Demo question.

    This text deliberately contains no deep-sea-mining claim.  Retrieval can
    therefore demonstrate both a positive evidence candidate and a safe
    no-source result without a provider or a fabricated answer.
    """

    content = (
        "估價依據：本示範案件採用新北市土地估價作業規則及案件日期適用的正式規則版本。"
        "估價人員應以公告地價、區段位置、土地使用分區、面積與可追溯的比較標的資料為依據，"
        "並將確認的 F03 比準地地價估計結果及其決定理由保存於案件版本。"
    )
    return KnowledgeFixture(
        code=DEMO_KNOWLEDGE_CODE,
        title=DEMO_KNOWLEDGE_TITLE,
        content=content,
        content_checksum_sha256=sha256_content(content),
    )


def f03_fixture(*, case_id: UUID | None = None) -> F03Fixture:
    """Build deterministic structured values for one valid F03 draft."""

    return F03Fixture(
        form_code="F03",
        form_content={
            "schema_version": "f03-demo-v1",
            "case_id": str(case_id) if case_id is not None else None,
            "valuation_basis": "published_rule_source",
            "calculation_status": "CALCULATED",
            "data": {
                "valuation_base_date": "2026-09-08",
                "benchmark_comparison_price": "125000",
                "decision_reason": "依正式規則版本與可追溯比較標的計算。",
            },
        },
        district_code="板橋區",
        section_name="示範段",
        land_no="001",
        area_sqm="100.0000",
        land_use_zone="COMMERCIAL",
    )


def build_demo_pdf(title: str = DEMO_CASE_TITLE) -> bytes:
    """Build a tiny valid PDF using the project's ReportLab dependency.

    ReportLab is imported lazily so safe CLI parsing and fake-cursor unit tests
    remain runnable on a host that has only the application test dependencies.
    The PDF intentionally contains ASCII metadata; the authoritative Knowledge
    text is persisted in PostgreSQL chunks as UTF-8 content.
    """

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover - exercised by environment
        raise RuntimeError("REPORTLAB_REQUIRED_FOR_DEMO_FIXTURE") from exc

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=0)
    pdf.setTitle(title.encode("ascii", "replace").decode("ascii"))
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(48, 790, title.encode("ascii", "replace").decode("ascii"))
    pdf.setFont("Helvetica", 10)
    pdf.drawString(48, 765, "Development-only persistent valuation evidence")
    pdf.drawString(48, 748, DEMO_CASE_NO)
    pdf.save()
    return output.getvalue()


def case_object_key(case_id: UUID, document_id: UUID, filename: str) -> str:
    return f"cases/{case_id}/demo/{uuid4()}/{document_id}-{filename}"


def knowledge_object_key(document_id: UUID, filename: str) -> str:
    return f"knowledge/{document_id}/demo/{uuid4()}/{filename}"


__all__ = [
    "DEMO_CASE_NO",
    "DEMO_CASE_TITLE",
    "DEMO_KNOWLEDGE_CODE",
    "DEMO_KNOWLEDGE_TITLE",
    "SUPPORTED_QUESTION",
    "NO_SOURCE_QUESTION",
    "KnowledgeFixture",
    "F03Fixture",
    "sha256_bytes",
    "sha256_content",
    "knowledge_source",
    "f03_fixture",
    "build_demo_pdf",
    "case_object_key",
    "knowledge_object_key",
]
