from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


FONT_NAME = "F03CJK"


def _register_cjk_font() -> None:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    candidates = (
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf"),
        Path("C:/Windows/Fonts/msjh.ttc"),
        Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
    )
    font_path = next((path for path in candidates if path.is_file()), None)
    if font_path is None:
        raise RuntimeError("F03 PDF CJK font is not installed")
    pdfmetrics.registerFont(
        TTFont(FONT_NAME, str(font_path), subfontIndex=0)
    )


def build_f03_report_pdf(data: dict) -> bytes:
    """Build the fixed Day 5 F03 PDF only from supplied backend records."""
    _register_cjk_font()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="F03 比準地地價估計表",
        author="Land Valuation Assistant",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "F03Title",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=18,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#102A43"),
    )
    heading_style = ParagraphStyle(
        "F03Heading",
        parent=styles["Heading2"],
        fontName=FONT_NAME,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1F4E78"),
        spaceBefore=8,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "F03Body",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=14,
        wordWrap="CJK",
    )
    small_style = ParagraphStyle(
        "F03Small",
        parent=body_style,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#52616B"),
    )

    def text(value) -> Paragraph:
        display = "—" if value is None or value == "" else str(value)
        return Paragraph(escape(display), body_style)

    def section(title: str, rows: list[tuple[str, object]]) -> list:
        table_data = [[text(label), text(value)] for label, value in rows]
        table = Table(table_data, colWidths=[48 * mm, 125 * mm], repeatRows=0)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF2F8")),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#243B53")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9FB3C8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return [Paragraph(escape(title), heading_style), table]

    story = [
        Paragraph("F03 比準地地價估計表", title_style),
        Spacer(1, 5 * mm),
    ]
    story.extend(
        section(
            "案件資料",
            [
                ("案件編號", data["case_no"]),
                ("案件名稱", data["case_title"]),
                ("估價基準日", data["valuation_base_date"]),
                ("縣市／行政區代碼", f"{data['city_code']} / {data['district_code']}"),
                ("表單版本", data["form_version"]),
            ],
        )
    )
    story.extend(
        section(
            "比準地資料",
            [
                ("比準地編號", data["benchmark_land_no"]),
                ("地價區段編號", data["price_zone_no"]),
                ("段／小段／地號", data["parcel_display"]),
                ("面積（平方公尺）", data["area_sqm"]),
            ],
        )
    )
    story.extend(
        section(
            "計算結果",
            [
                ("比較法價格", data["comparison_price"]),
                ("比較法權重", data["comparison_weight"]),
                ("收益法價格", data["income_price"]),
                ("收益法權重", data["income_weight"]),
                ("比準地地價（TWD）", data["benchmark_land_price"]),
                ("公式版本", data["formula_version"]),
                ("計算結果 ID", data["calculation_id"]),
            ],
        )
    )
    story.extend(
        section(
            "製作前檢核",
            [
                ("檢核規則版本", data["ruleset_version"]),
                ("通過／警告／錯誤", data["validation_summary"]),
                ("檢核結果 ID", data["validation_run_id"]),
            ],
        )
    )
    story.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph(
                "本文件由後端已確認資料與固定計算規則產生；AI 不會重新生成價格或案件事實。",
                small_style,
            ),
            Paragraph(
                f"產生追蹤 ID：{escape(str(data.get('request_id') or '—'))}",
                small_style,
            ),
        ]
    )

    document.build(story)
    return buffer.getvalue()
