from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from typing import Any, Iterable

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from app.core.exceptions import AppError
from app.valuation.official_forms import OFFICIAL_SCHEMA_VERSION
from app.valuation.operations.report_builder import FONT_NAME, _register_cjk_font


OFFICIAL_TEMPLATE_MANIFEST_VERSION = "official-template-overlay-v1"
SUPPORTED_PLACEMENT_KINDS = {"TEXT", "CHECKMARK"}
SUPPORTED_ALIGNMENTS = {"LEFT", "CENTER", "RIGHT"}
PAGE_SIZE_TOLERANCE = 1.0


def _template_hash(template_pdf_bytes: bytes) -> str:
    return sha256(template_pdf_bytes).hexdigest()


def _page_sizes(reader: PdfReader) -> list[dict[str, float]]:
    return [
        {
            "width": float(page.mediabox.width),
            "height": float(page.mediabox.height),
        }
        for page in reader.pages
    ]


def build_template_manifest_skeleton(
    template_pdf_bytes: bytes,
    field_codes: Iterable[str],
    *,
    template_name: str,
    schema_version: str = OFFICIAL_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Create template identity metadata without guessing any field coordinates."""

    reader = PdfReader(BytesIO(template_pdf_bytes))
    if not reader.pages:
        raise AppError("OFFICIAL_TEMPLATE_EMPTY", "官方空白 PDF 不可沒有頁面", 422)
    normalized_fields = sorted(
        {str(code).strip() for code in field_codes if str(code).strip()}
    )
    return {
        "manifest_version": OFFICIAL_TEMPLATE_MANIFEST_VERSION,
        "schema_version": schema_version,
        "template_name": template_name,
        "template_sha256": _template_hash(template_pdf_bytes),
        "pages": _page_sizes(reader),
        "strip_annotations": True,
        "placements": [],
        "unmapped_fields": normalized_fields,
    }


def _validate_page_sizes(
    reader: PdfReader,
    expected_pages: list[dict[str, Any]],
) -> None:
    actual_pages = _page_sizes(reader)
    if len(actual_pages) != len(expected_pages):
        raise AppError(
            "OFFICIAL_TEMPLATE_PAGE_COUNT_MISMATCH",
            "官方空白 PDF 頁數與座標 manifest 不一致",
            422,
            {"expected": len(expected_pages), "actual": len(actual_pages)},
        )
    for index, (actual, expected) in enumerate(zip(actual_pages, expected_pages), 1):
        try:
            expected_width = float(expected["width"])
            expected_height = float(expected["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(
                "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
                "官方模板 manifest 的頁面尺寸格式錯誤",
                422,
                {"page": index},
            ) from exc
        if (
            abs(actual["width"] - expected_width) > PAGE_SIZE_TOLERANCE
            or abs(actual["height"] - expected_height) > PAGE_SIZE_TOLERANCE
        ):
            raise AppError(
                "OFFICIAL_TEMPLATE_PAGE_SIZE_MISMATCH",
                "官方空白 PDF 尺寸與座標 manifest 不一致",
                422,
                {
                    "page": index,
                    "expected": [expected_width, expected_height],
                    "actual": [actual["width"], actual["height"]],
                },
            )


def validate_template_manifest(
    template_pdf_bytes: bytes,
    manifest: dict[str, Any],
    *,
    require_complete: bool = True,
) -> dict[str, Any]:
    """Validate template identity and every overlay rectangle before rendering."""

    if manifest.get("manifest_version") != OFFICIAL_TEMPLATE_MANIFEST_VERSION:
        raise AppError(
            "OFFICIAL_TEMPLATE_MANIFEST_VERSION_UNSUPPORTED",
            "官方模板 manifest 版本不支援",
            422,
        )
    if manifest.get("schema_version") != OFFICIAL_SCHEMA_VERSION:
        raise AppError(
            "OFFICIAL_TEMPLATE_SCHEMA_VERSION_MISMATCH",
            "官方模板欄位版本與目前系統欄位版本不一致",
            422,
            {
                "expected": OFFICIAL_SCHEMA_VERSION,
                "actual": manifest.get("schema_version"),
            },
        )
    expected_hash = str(manifest.get("template_sha256") or "").lower()
    actual_hash = _template_hash(template_pdf_bytes)
    if expected_hash != actual_hash:
        raise AppError(
            "OFFICIAL_TEMPLATE_HASH_MISMATCH",
            "官方空白 PDF 與已校準的模板版本不同，禁止套用舊座標",
            422,
            {"expected": expected_hash, "actual": actual_hash},
        )

    reader = PdfReader(BytesIO(template_pdf_bytes))
    expected_pages = manifest.get("pages")
    if not isinstance(expected_pages, list) or not expected_pages:
        raise AppError(
            "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
            "官方模板 manifest 缺少頁面尺寸資料",
            422,
        )
    _validate_page_sizes(reader, expected_pages)

    placements = manifest.get("placements")
    if not isinstance(placements, list):
        raise AppError(
            "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
            "官方模板 manifest placements 格式錯誤",
            422,
        )
    unmapped_fields = manifest.get("unmapped_fields") or []
    if not isinstance(unmapped_fields, list):
        raise AppError(
            "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
            "官方模板 manifest unmapped_fields 格式錯誤",
            422,
        )
    if require_complete and unmapped_fields:
        raise AppError(
            "OFFICIAL_TEMPLATE_MAPPING_INCOMPLETE",
            "官方空白 PDF 尚有欄位未完成座標校準",
            409,
            {"unmapped_fields": sorted({str(item) for item in unmapped_fields})},
        )

    seen: set[tuple[Any, ...]] = set()
    for index, placement in enumerate(placements, 1):
        if not isinstance(placement, dict):
            raise AppError(
                "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
                "官方模板欄位座標格式錯誤",
                422,
                {"placement": index},
            )
        field_code = str(placement.get("field_code") or "").strip()
        if not field_code:
            raise AppError(
                "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
                "官方模板欄位座標缺少 field_code",
                422,
                {"placement": index},
            )
        try:
            page_number = int(placement["page"])
            box = tuple(float(value) for value in placement["box"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(
                "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
                "官方模板欄位 page/box 格式錯誤",
                422,
                {"field_code": field_code},
            ) from exc
        if len(box) != 4:
            raise AppError(
                "OFFICIAL_TEMPLATE_MANIFEST_INVALID",
                "官方模板欄位 box 必須為 x, y, width, height",
                422,
                {"field_code": field_code},
            )
        if page_number < 1 or page_number > len(expected_pages):
            raise AppError(
                "OFFICIAL_TEMPLATE_PLACEMENT_OUT_OF_BOUNDS",
                "官方模板欄位指定了不存在的頁面",
                422,
                {"field_code": field_code, "page": page_number},
            )
        x, y, width, height = box
        page_size = expected_pages[page_number - 1]
        page_width = float(page_size["width"])
        page_height = float(page_size["height"])
        if (
            x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or x + width > page_width + PAGE_SIZE_TOLERANCE
            or y + height > page_height + PAGE_SIZE_TOLERANCE
        ):
            raise AppError(
                "OFFICIAL_TEMPLATE_PLACEMENT_OUT_OF_BOUNDS",
                "官方模板欄位座標超出 PDF 頁面範圍",
                422,
                {"field_code": field_code, "page": page_number, "box": list(box)},
            )
        kind = str(placement.get("kind") or "TEXT").upper()
        if kind not in SUPPORTED_PLACEMENT_KINDS:
            raise AppError(
                "OFFICIAL_TEMPLATE_PLACEMENT_KIND_UNSUPPORTED",
                "官方模板欄位類型不支援",
                422,
                {"field_code": field_code, "kind": kind},
            )
        alignment = str(placement.get("align") or "LEFT").upper()
        if alignment not in SUPPORTED_ALIGNMENTS:
            raise AppError(
                "OFFICIAL_TEMPLATE_ALIGNMENT_UNSUPPORTED",
                "官方模板文字對齊方式不支援",
                422,
                {"field_code": field_code, "align": alignment},
            )
        identity = (field_code, page_number, *box)
        if identity in seen:
            raise AppError(
                "OFFICIAL_TEMPLATE_DUPLICATE_PLACEMENT",
                "官方模板存在重複欄位座標",
                422,
                {"field_code": field_code, "page": page_number},
            )
        seen.add(identity)

    return deepcopy(manifest)


def _value_text(value: Any, kind: str) -> str:
    if kind == "CHECKMARK":
        return "✓" if bool(value) else ""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _resolve_value(values: Any, path: str) -> Any:
    current = values
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current


def _fit_line(text: str, width: float, font_size: float) -> tuple[str, str]:
    if not text:
        return "", ""
    usable = max(width, 1)
    for end in range(len(text), 0, -1):
        candidate = text[:end]
        if pdfmetrics.stringWidth(candidate, FONT_NAME, font_size) <= usable:
            return candidate, text[end:]
    return text[:1], text[1:]


def _draw_value(
    target: canvas.Canvas,
    value: Any,
    placement: dict[str, Any],
) -> None:
    kind = str(placement.get("kind") or "TEXT").upper()
    text = _value_text(value, kind)
    if not text:
        return
    x, y, width, height = (float(item) for item in placement["box"])
    font_size = float(placement.get("font_size") or 8.0)
    min_font_size = float(placement.get("min_font_size") or 5.0)
    max_lines = max(1, int(placement.get("max_lines") or 1))
    padding = max(0.0, float(placement.get("padding") or 1.5))
    alignment = str(placement.get("align") or "LEFT").upper()
    available_width = max(1.0, width - padding * 2)
    available_height = max(1.0, height - padding * 2)

    while font_size > min_font_size and font_size * max_lines > available_height:
        font_size -= 0.5
    font_size = max(min_font_size, font_size)

    lines: list[str] = []
    remaining = text
    while remaining and len(lines) < max_lines:
        line, remaining = _fit_line(remaining, available_width, font_size)
        lines.append(line)
    if remaining and lines:
        last = lines[-1]
        ellipsis = "…"
        while last and pdfmetrics.stringWidth(
            last + ellipsis, FONT_NAME, font_size
        ) > available_width:
            last = last[:-1]
        lines[-1] = (last + ellipsis) if last else ellipsis

    target.setFont(FONT_NAME, font_size)
    leading = min(available_height / max(len(lines), 1), font_size * 1.25)
    total_height = leading * len(lines)
    baseline = (
        y
        + padding
        + max(0.0, (available_height - total_height) / 2)
        + total_height
        - font_size
    )
    for line in lines:
        if alignment == "CENTER":
            target.drawCentredString(x + width / 2, baseline, line)
        elif alignment == "RIGHT":
            target.drawRightString(x + width - padding, baseline, line)
        else:
            target.drawString(x + padding, baseline, line)
        baseline -= leading


def overlay_official_blank_template(
    template_pdf_bytes: bytes,
    manifest: dict[str, Any],
    values: dict[str, Any],
) -> bytes:
    """Stamp verified values onto the original official PDF without redrawing it."""

    validated = validate_template_manifest(template_pdf_bytes, manifest)
    _register_cjk_font()
    reader = PdfReader(BytesIO(template_pdf_bytes))
    placements_by_page: dict[int, list[dict[str, Any]]] = {}
    for placement in validated["placements"]:
        placements_by_page.setdefault(int(placement["page"]), []).append(placement)

    writer = PdfWriter()
    for page_number, source_page in enumerate(reader.pages, 1):
        writer.add_page(source_page)
        page = writer.pages[-1]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        page_placements = placements_by_page.get(page_number, [])
        if page_placements:
            overlay_buffer = BytesIO()
            target = canvas.Canvas(overlay_buffer, pagesize=(width, height))
            for placement in page_placements:
                value_path = str(
                    placement.get("value_path") or placement["field_code"]
                )
                _draw_value(
                    target,
                    _resolve_value(values, value_path),
                    placement,
                )
            target.save()
            overlay_page = PdfReader(BytesIO(overlay_buffer.getvalue())).pages[0]
            page.merge_page(overlay_page)
        if validated.get("strip_annotations", True):
            page.pop(NameObject("/Annots"), None)

    if validated.get("strip_annotations", True):
        writer._root_object.pop(NameObject("/AcroForm"), None)
    writer.add_metadata(
        {
            "/Title": str(
                validated.get("template_name") or "官方空白估價書填值版"
            ),
            "/Author": "Land Valuation Assistant",
            "/Subject": (
                "原官方空白 PDF 背景保留；欄位以已校準 manifest 疊加。"
                f" manifest={OFFICIAL_TEMPLATE_MANIFEST_VERSION}"
            ),
        }
    )
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()

    verification = PdfReader(BytesIO(result))
    _validate_page_sizes(verification, validated["pages"])
    if validated.get("strip_annotations", True) and (verification.get_fields() or {}):
        raise AppError(
            "OFFICIAL_TEMPLATE_OUTPUT_NOT_STATIC",
            "正式官方模板輸出仍包含可編輯表單欄位",
            500,
        )
    return result


__all__ = [
    "OFFICIAL_TEMPLATE_MANIFEST_VERSION",
    "build_template_manifest_skeleton",
    "overlay_official_blank_template",
    "validate_template_manifest",
]