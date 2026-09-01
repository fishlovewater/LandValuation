from io import BytesIO
from typing import Any

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from app.valuation.operations.report_builder import FONT_NAME, _register_cjk_font
from app.valuation.report_packages.draft_pdf_builder import (
    build_three_page_draft_pdf,
    build_three_page_formal_pdf,
)


MAP_PAGES = (
    ("MAP-01", "地價區段略圖", "map-section-sketch"),
    ("MAP-02", "地價使用分區圖", "map-zoning"),
    ("MAP-03", "地價區段圖", "map-land-value-section"),
)


def _fitted_text(target: canvas.Canvas, text: str, x: float, y: float, width: float) -> None:
    value = text
    size = 8.0
    while value and pdfmetrics.stringWidth(value, FONT_NAME, size) > width:
        value = value[:-1]
    if value != text and len(value) > 3:
        value = value[:-3] + "..."
    target.setFont(FONT_NAME, size)
    target.drawString(x, y, value)


def _draw_chrome(
    target: canvas.Canvas,
    code: str,
    title: str,
    *,
    filename: str | None,
    missing: bool,
    preview_error: bool = False,
    formal: bool = False,
) -> None:
    width, height = A4
    if not formal:
        target.setFillColor(colors.HexColor("#FFF3CD"))
        target.setStrokeColor(colors.HexColor("#B8860B"))
        target.roundRect(24, height - 28, width - 48, 17, 3, fill=1, stroke=1)
        target.setFillColor(colors.HexColor("#7A4E00"))
        target.setFont(FONT_NAME, 7.5)
        target.drawCentredString(
            width / 2,
            height - 22,
            "草稿預覽－附圖僅採用本案件使用者上傳文件；未完成正式六頁檢核",
        )
    target.setFillColor(colors.black)
    target.setFont(FONT_NAME, 14)
    target.drawString(35, height - 50, f"{code}  {title}")
    target.setFont(FONT_NAME, 8)
    if not formal:
        target.drawRightString(width - 35, height - 48, "DRAFT")

    if missing:
        target.setStrokeColor(colors.HexColor("#888888"))
        target.setDash(5, 4)
        target.rect(45, 120, width - 90, height - 220, fill=0, stroke=1)
        target.setDash()
        target.setFillColor(colors.HexColor("#666666"))
        target.setFont(FONT_NAME, 14)
        target.drawCentredString(width / 2, height / 2 + 10, "尚未上傳正式附圖文件")
        target.setFont(FONT_NAME, 9)
        target.drawCentredString(
            width / 2,
            height / 2 - 12,
            "請由案件文件 API 上傳對應的 PNG、JPEG 或 PDF",
        )
    elif preview_error:
        target.setFillColor(colors.HexColor("#A61B1B"))
        target.setFont(FONT_NAME, 11)
        target.drawCentredString(width / 2, height / 2, "已上傳文件，但此草稿無法預覽其格式")

    target.setFillColor(colors.HexColor("#444444"))
    source = "來源：未上傳" if filename is None else f"來源：{filename}"
    _fitted_text(target, source, 35, 35, width - 70)
    if not formal:
        target.setFont(FONT_NAME, 7)
        target.drawRightString(width - 35, 22, "自動 Static Map 不得代替本頁正式附圖")


def _reportlab_map_page(
    code: str,
    title: str,
    document: dict[str, Any] | None,
    *,
    formal: bool = False,
) -> PageObject:
    buffer = BytesIO()
    target = canvas.Canvas(buffer, pagesize=A4)
    target.setTitle(f"{code} {title} 草稿")
    missing = document is None
    preview_error = False
    filename = None if document is None else str(document.get("filename") or "")

    if document is not None:
        try:
            reader = ImageReader(BytesIO(document["content"]))
            image_width, image_height = reader.getSize()
            max_width = A4[0] - 70
            max_height = A4[1] - 135
            scale = min(max_width / image_width, max_height / image_height)
            draw_width = image_width * scale
            draw_height = image_height * scale
            target.drawImage(
                reader,
                (A4[0] - draw_width) / 2,
                62 + (max_height - draw_height) / 2,
                width=draw_width,
                height=draw_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            preview_error = True

    if formal and (missing or preview_error):
        raise RuntimeError(f"正式附圖 {code} 無法讀取或預覽")

    _draw_chrome(
        target,
        code,
        title,
        filename=filename,
        missing=missing,
        preview_error=preview_error,
        formal=formal,
    )
    target.save()
    return PdfReader(BytesIO(buffer.getvalue())).pages[0]


def _pdf_map_page(
    code: str,
    title: str,
    document: dict[str, Any],
    *,
    formal: bool = False,
) -> PageObject:
    source_reader = PdfReader(BytesIO(document["content"]))
    if not source_reader.pages:
        return _reportlab_map_page(
            code, title, {**document, "content": b""}, formal=formal
        )
    source_writer = PdfWriter(clone_from=source_reader)
    source = source_writer.pages[0]
    if source.rotation:
        source.transfer_rotation_to_content()

    source_width = float(source.mediabox.width)
    source_height = float(source.mediabox.height)
    max_width = A4[0] - 70
    max_height = A4[1] - 135
    scale = min(max_width / source_width, max_height / source_height)
    x = (A4[0] - source_width * scale) / 2
    y = 62 + (max_height - source_height * scale) / 2
    page_writer = PdfWriter()
    page = page_writer.add_blank_page(width=A4[0], height=A4[1])
    page.merge_transformed_page(
        source,
        Transformation().scale(scale).translate(x, y),
    )
    overlay_buffer = BytesIO()
    target = canvas.Canvas(overlay_buffer, pagesize=A4)
    _draw_chrome(
        target,
        code,
        title,
        filename=str(document.get("filename") or ""),
        missing=False,
        formal=formal,
    )
    target.save()
    page.merge_page(PdfReader(BytesIO(overlay_buffer.getvalue())).pages[0])
    output = BytesIO()
    page_writer.write(output)
    return PdfReader(BytesIO(output.getvalue())).pages[0]


def _map_page(
    code: str,
    title: str,
    document: dict[str, Any] | None,
    *,
    formal: bool = False,
) -> PageObject:
    if document is None:
        return _reportlab_map_page(code, title, None, formal=formal)
    mime_type = str(document.get("mime_type") or "").lower()
    content = document.get("content")
    if not isinstance(content, bytes):
        if formal:
            raise RuntimeError(f"正式附圖 {code} 內容格式錯誤")
        return _reportlab_map_page(
            code, title, {**document, "content": b""}, formal=formal
        )
    if mime_type == "application/pdf" or content.startswith(b"%PDF"):
        try:
            return _pdf_map_page(code, title, document, formal=formal)
        except Exception:
            if formal:
                raise
            return _reportlab_map_page(
                code, title, {**document, "content": b""}, formal=formal
            )
    return _reportlab_map_page(code, title, document, formal=formal)


def build_six_page_draft_pdf(
    data: dict[str, Any],
    map_documents: dict[str, dict[str, Any]],
) -> bytes:
    """Build a six-page DRAFT. Missing maps become explicit placeholder pages."""
    _register_cjk_font()
    first_three = PdfReader(
        BytesIO(
            build_three_page_draft_pdf(
                data,
                draft_notice=(
                    "草稿預覽－六頁合併／附圖僅採案件上傳文件／"
                    "未執行正式因素與價格計算"
                ),
            )
        )
    )
    writer = PdfWriter()
    for page in first_three.pages:
        writer.add_page(page)
    for code, title, document_type in MAP_PAGES:
        writer.add_page(_map_page(code, title, map_documents.get(document_type)))
    writer.add_metadata(
        {
            "/Title": "完整查估書六頁草稿預覽",
            "/Author": "Land Valuation Assistant",
            "/Subject": "未完成正式因素計算與六頁檢核；附圖僅來自使用者上傳文件",
        }
    )
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    verification = PdfReader(BytesIO(result))
    if len(verification.pages) != 6:
        raise RuntimeError("六頁草稿 PDF 產生後頁數驗證失敗")
    for page in verification.pages:
        if abs(float(page.mediabox.width) - A4[0]) > 1 or abs(
            float(page.mediabox.height) - A4[1]
        ) > 1:
            raise RuntimeError("六頁草稿 PDF 必須全部為 A4 直向")
    return result


def build_six_page_formal_pdf(
    data: dict[str, Any],
    map_documents: dict[str, dict[str, Any]],
) -> bytes:
    """Build the immutable six-page report after the formal validation gate."""
    _register_cjk_font()
    missing = [
        document_type
        for _, _, document_type in MAP_PAGES
        if document_type not in map_documents
    ]
    if missing:
        raise RuntimeError("正式六頁 PDF 缺少附圖：" + ", ".join(missing))

    first_three = PdfReader(BytesIO(build_three_page_formal_pdf(data)))
    writer = PdfWriter()
    for page in first_three.pages:
        writer.add_page(page)
    for code, title, document_type in MAP_PAGES:
        writer.add_page(
            _map_page(
                code,
                title,
                map_documents[document_type],
                formal=True,
            )
        )
    writer.add_metadata(
        {
            "/Title": "完整六頁土地市價查估書",
            "/Author": "Land Valuation Assistant",
            "/Subject": "經正式規則計算及整份檢核",
        }
    )
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    verification = PdfReader(BytesIO(result))
    if len(verification.pages) != 6:
        raise RuntimeError("正式六頁 PDF 產生後頁數驗證失敗")
    for page in verification.pages:
        if abs(float(page.mediabox.width) - A4[0]) > 1 or abs(
            float(page.mediabox.height) - A4[1]
        ) > 1:
            raise RuntimeError("正式六頁 PDF 必須全部為 A4 直向")
    return result
