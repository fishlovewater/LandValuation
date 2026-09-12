from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.exceptions import AppError
from app.valuation.official_field_catalog import OFFICIAL_PDF_FIELDS
from app.valuation.official_forms import OFFICIAL_FORM_TEMPLATES

PAGE_SIZE = landscape(A4)
TEMPLATE_VERSION = "ntpc-redrawn-field-complete-v2"
FONT_NAME = "OfficialCJK"
FONT_CANDIDATES = ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/kaiu.ttf")
ROWS_PER_PAGE = 22


def _font() -> str:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return FONT_NAME
    for value in FONT_CANDIDATES:
        if Path(value).exists():
            pdfmetrics.registerFont(TTFont(FONT_NAME, value))
            return FONT_NAME
    raise AppError("PDF_FONT_MISSING", "找不到可輸出繁體中文的 PDF 字型", 500)


def _layout(form_code: str) -> list[dict[str, Any]]:
    width, height = PAGE_SIZE
    margin, top, row_height, label_width = 26, height - 72, 22, 245
    rows = []
    for index, field in enumerate(OFFICIAL_PDF_FIELDS[form_code]):
        page, row = divmod(index, ROWS_PER_PAGE)
        y = top - (row + 1) * row_height
        rows.append({"field_code": field.code, "section_label": field.section, "label": field.label,
            "unit": None, "required_for_formal": False, "page": page + 1,
            "label_box": (margin, y, label_width, row_height),
            "value_box": (margin + label_width, y, width - margin * 2 - label_width, row_height)})
    return rows


FORM_FIELD_COORDINATES = {code: _layout(code) for code in ("F01", "F02", "F03", "F04")}


def _text(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, bool): return "是" if value else "否"
    return str(value)


def _header(c: canvas.Canvas, form_code: str, page: int, total: int) -> None:
    width, height = PAGE_SIZE
    c.setFont(_font(), 15)
    c.drawCentredString(width / 2, height - 27, OFFICIAL_FORM_TEMPLATES[form_code].form_name)
    c.setFont(_font(), 7)
    c.drawString(26, height - 45, f"欄位完整重繪版：{TEMPLATE_VERSION}")
    c.drawRightString(width - 26, height - 45, f"第 {page}/{total} 頁｜來源：{OFFICIAL_FORM_TEMPLATES[form_code].source_title}")


def _fit(c: canvas.Canvas, value: Any, x: float, y: float, width: float, height: float) -> None:
    text = _text(value)
    if not text: return
    size = 7.5
    while size > 5 and pdfmetrics.stringWidth(text, _font(), size) > width - 8: size -= .5
    c.setFont(_font(), size)
    c.drawString(x + 4, y + max(4, (height - size) / 2), text[:300])


def build_official_form_pdf(form_code: str, values: dict[str, Any] | None = None, *, interactive_blank: bool = False) -> bytes:
    if form_code not in FORM_FIELD_COORDINATES:
        raise AppError("OFFICIAL_PDF_FORM_UNSUPPORTED", "不支援此官方 PDF 表單", 422)
    if interactive_blank and values:
        raise AppError("OFFICIAL_PDF_MODE_CONFLICT", "互動空白版不可同時填值", 422)
    values = values or {}
    allowed = {item["field_code"] for item in FORM_FIELD_COORDINATES[form_code]}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise AppError("OFFICIAL_PDF_FIELD_UNKNOWN", "PDF 資料包含未定義欄位", 422, {"unknown_fields": unknown})
    stream = BytesIO()
    c = canvas.Canvas(stream, pagesize=PAGE_SIZE, pageCompression=1)
    c.setTitle(OFFICIAL_FORM_TEMPLATES[form_code].form_name)
    c.setAuthor("landvalue_ms backend")
    total = max(item["page"] for item in FORM_FIELD_COORDINATES[form_code])
    current = 0
    for item in FORM_FIELD_COORDINATES[form_code]:
        if item["page"] != current:
            if current: c.showPage()
            current = item["page"]
            _header(c, form_code, current, total)
        lx, y, lw, h = item["label_box"]
        vx, _, vw, _ = item["value_box"]
        c.setFillColor(colors.HexColor("#F1F5F9")); c.rect(lx, y, lw, h, fill=1, stroke=1)
        c.setFillColor(colors.white); c.rect(vx, y, vw, h, fill=1, stroke=1)
        c.setFillColor(colors.black); c.setFont(_font(), 7)
        c.drawString(lx + 4, y + 8, f"{item['section_label']}｜{item['label']}")
        if interactive_blank:
            c.acroForm.textfield(name=item["field_code"], tooltip=item["label"], x=vx + 1, y=y + 1,
                width=vw - 2, height=h - 2, borderWidth=0, fillColor=colors.white,
                textColor=colors.black, fontName="Helvetica", fontSize=7, forceBorder=False)
        else:
            _fit(c, values.get(item["field_code"]), vx, y, vw, h)
    c.showPage(); c.save()
    return stream.getvalue()


def coordinate_manifest(form_code: str) -> dict[str, Any]:
    fields = FORM_FIELD_COORDINATES[form_code]
    return {"template_version": TEMPLATE_VERSION, "form_code": form_code, "page_width": PAGE_SIZE[0],
        "page_height": PAGE_SIZE[1], "page_count": max(item["page"] for item in fields), "fields": fields}
