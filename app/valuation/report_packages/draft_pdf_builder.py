from io import BytesIO
from pathlib import Path
from decimal import Decimal

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from app.valuation.operations.report_builder import FONT_NAME, _register_cjk_font
from app.valuation.report_packages.factor_catalog import (
    INDIVIDUAL_FACTOR_BY_CODE,
    TEMPLATE_FACTOR_BY_CODE,
)


TEMPLATE_PATH = (
    Path(__file__).parent
    / "templates"
    / "comparison_commercial"
    / "blank_pages_1_3.pdf"
)
DRAFT_NOTICE = "草稿預覽－僅前三頁／不含地圖／未執行正式因素與價格計算"


def _draw_fitted(
    target: canvas.Canvas,
    value: object,
    x: float,
    y: float,
    max_width: float,
    *,
    size: float = 7,
) -> None:
    if value is None or value == "":
        return
    text = str(value)
    target.setFont(FONT_NAME, size)
    while text and pdfmetrics.stringWidth(text, FONT_NAME, size) > max_width:
        text = text[:-1]
    if text != str(value) and text:
        text = f"{text[:-3]}..." if len(text) >= 3 else "..."
    target.drawString(x, y, text)


def _clear_template_value(
    target: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    target.saveState()
    target.setFillColor(colors.white)
    target.setStrokeColor(colors.white)
    target.rect(x, y, width, height, fill=1, stroke=0)
    target.restoreState()


def _draw_notice(
    target: canvas.Canvas,
    width: float,
    y: float,
    notice: str = DRAFT_NOTICE,
) -> None:
    if not notice:
        return
    target.setFillColor(colors.HexColor("#FFF3CD"))
    target.setStrokeColor(colors.HexColor("#B8860B"))
    target.roundRect(22, y, width - 44, 16, 3, fill=1, stroke=1)
    target.setFillColor(colors.HexColor("#7A4E00"))
    target.setFont(FONT_NAME, 7.5)
    target.drawCentredString(width / 2, y + 5, notice)
    target.setFillColor(colors.black)


def _selected_benchmark(data: dict) -> dict | None:
    context = data["context"]
    selected_id = (
        data["f02_rf"].get("benchmark_land_id")
        or data["f02"].get("benchmark_land_id")
    )
    if selected_id is not None:
        return next(
            (
                item
                for item in context["benchmark_lands"]
                if item["benchmark_land_id"] == selected_id
            ),
            None,
        )
    if len(context["benchmark_lands"]) == 1:
        return context["benchmark_lands"][0]
    return None


def _draw_page_one(
    target: canvas.Canvas, data: dict, width: float, notice: str
) -> None:
    context = data["context"]
    draft = data["s01"]
    benchmark = _selected_benchmark(data)
    _draw_notice(target, width, 817, notice)
    target.setFillColor(colors.HexColor("#333333"))
    _draw_fitted(target, f"案號：{context['case_no']}", 420, 804, 145, size=6.5)
    _draw_fitted(target, draft.get("district_name"), 80, 767, 105, size=7)
    _draw_fitted(
        target,
        None if benchmark is None else benchmark.get("price_zone_no"),
        137,
        744,
        48,
        size=7,
    )
    _draw_fitted(target, draft.get("district_boundary"), 330, 744, 225, size=6.5)
    _draw_fitted(target, draft.get("urban_plan_status"), 205, 718, 70)
    _draw_fitted(target, draft.get("land_use_zone"), 205, 703, 70)
    coverage = draft.get("building_coverage_rate")
    ratio = draft.get("floor_area_ratio")
    _draw_fitted(target, None if coverage is None else f"{coverage}%", 205, 688, 70)
    _draw_fitted(target, None if ratio is None else f"{ratio}%", 205, 673, 70)
    _draw_fitted(target, draft.get("prohibited_building"), 205, 659, 70)
    _draw_fitted(target, draft.get("restricted_building"), 205, 638, 70, size=6)
    _clear_template_value(target, 145, 622, 78, 11)
    _draw_fitted(target, draft.get("main_road_name"), 151, 627, 72, size=6.5)
    road_width = draft.get("main_road_width_m")
    _draw_fitted(
        target,
        road_width,
        236,
        627,
        20,
        size=6.5,
    )
    average_width = draft.get("average_road_width_m")
    _draw_fitted(
        target,
        average_width,
        168,
        611,
        20,
        size=6.5,
    )
    survey_date = draft.get("survey_date")
    # The supplied blank template retains a sample survey date. Clear only
    # that value cell so the preview cannot present the sample as case data.
    _clear_template_value(target, 61, 134, 72, 13)
    _draw_fitted(
        target,
        None if survey_date is None else survey_date,
        64,
        138,
        65,
        size=6.5,
    )
    _draw_fitted(target, draft.get("handler_name"), 195, 138, 72, size=6.5)
    _draw_fitted(target, draft.get("section_head_name"), 320, 138, 48, size=6.5)
    _draw_fitted(target, draft.get("director_name"), 438, 138, 88, size=6.5)
    _draw_fitted(target, draft.get("appraiser_name"), 455, 70, 105, size=6.5)


def _draw_page_two(
    target: canvas.Canvas, data: dict, width: float, notice: str
) -> None:
    context = data["context"]
    draft = data["f02_rf"]
    benchmark = _selected_benchmark(data)
    _draw_notice(target, width, 817, notice)
    _draw_fitted(target, context["case_no"], 95, 761, 105, size=7)
    _draw_fitted(
        target,
        None if benchmark is None else benchmark.get("price_zone_no"),
        230,
        748,
        95,
        size=7,
    )

    row_map = {row["factor_code"]: row for row in draft.get("factor_rows", [])}
    target_x = {1: 291, 2: 386, 3: 481}
    for code, definition in TEMPLATE_FACTOR_BY_CODE.items():
        if definition.f02_rf_y is None:
            continue
        row = row_map.get(code)
        if row is None:
            continue
        benchmark_level = row.get("benchmark_confirmed_level") or row.get(
            "benchmark_reported_level"
        )
        _draw_fitted(target, benchmark_level, 230, definition.f02_rf_y, 28, size=6)
        for comparable in row.get("targets", []):
            level = comparable.get("confirmed_level") or comparable.get(
                "reported_level"
            )
            x = target_x.get(comparable.get("display_order"))
            if x is not None:
                _draw_fitted(target, level, x, definition.f02_rf_y, 25, size=6)
                rate = comparable.get("calculated_adjustment_rate")
                _draw_fitted(
                    target,
                    None if rate is None else f"{Decimal(str(rate)) * 100}%",
                    x + 27,
                    definition.f02_rf_y,
                    31,
                    size=5.5,
                )
    _draw_fitted(target, draft.get("appraiser_name"), 430, 80, 90, size=7)


def _draw_page_three_landscape(
    target: canvas.Canvas,
    data: dict,
    portrait_width: float,
    notice: str,
) -> None:
    context = data["context"]
    draft = data["f02"]
    benchmark = _selected_benchmark(data)
    target.saveState()
    target.translate(portrait_width, 0)
    target.rotate(90)
    landscape_width = A4[1]
    _draw_notice(target, landscape_width, 576, notice)
    _draw_fitted(
        target,
        context["valuation_base_date"],
        555,
        558,
        75,
        size=7,
    )
    _draw_fitted(target, context["case_no"], 720, 558, 70, size=7)
    _draw_fitted(
        target,
        None if benchmark is None else benchmark.get("benchmark_land_no"),
        255,
        544,
        75,
        size=6.5,
    )
    target_x = {1: 435, 2: 592, 3: 752}
    individual_y = {
        code: 446 - index * 14.2
        for index, code in enumerate(INDIVIDUAL_FACTOR_BY_CODE)
    }
    for item in draft.get("comparison_targets", []):
        x = target_x.get(item.get("display_order"))
        if x is not None:
            _draw_fitted(
                target,
                f"ID {str(item['comparison_target_id'])[:8]}",
                x,
                545,
                65,
                size=6,
            )
            _draw_fitted(
                target,
                item.get("transaction_date_snapshot"),
                x,
                530,
                70,
                size=5.5,
            )
            _draw_fitted(
                target,
                item.get("normal_unit_price_snapshot"),
                x,
                515,
                70,
                size=5.5,
            )
            _draw_fitted(
                target,
                _percent(item.get("time_adjustment_rate")),
                x + 45,
                500,
                35,
                size=5.5,
            )
            _draw_fitted(
                target,
                _percent(item.get("regional_adjustment_rate")),
                x + 45,
                485,
                35,
                size=5.5,
            )
            for factor in item.get("individual_factors", []):
                y = individual_y.get(factor.get("factor_code"))
                if y is None:
                    continue
                level = factor.get("comparable_confirmed_level") or factor.get(
                    "comparable_reported_level"
                )
                _draw_fitted(target, level, x - 53, y, 64, size=5.2)
                _draw_fitted(
                    target,
                    _percent(factor.get("calculated_adjustment_rate")),
                    x + 45,
                    y,
                    34,
                    size=5.2,
                )
            _draw_fitted(
                target,
                _percent(item.get("total_adjustment_absolute")),
                x + 30,
                146,
                48,
                size=5.8,
            )
            _draw_fitted(
                target,
                item.get("trial_price"),
                x,
                118,
                70,
                size=6,
            )
            _draw_fitted(
                target,
                _percent(item.get("weight")),
                x + 30,
                103,
                48,
                size=5.8,
            )
    _draw_fitted(
        target,
        draft.get("benchmark_comparison_price"),
        245,
        88,
        75,
        size=6.5,
    )
    _draw_fitted(target, draft.get("handler_name"), 105, 31, 75, size=6.5)
    _draw_fitted(target, draft.get("section_head_name"), 235, 31, 45, size=6.5)
    _draw_fitted(target, draft.get("director_name"), 360, 31, 32, size=6.5)
    _draw_fitted(target, draft.get("appraiser_name"), 505, 31, 95, size=6.5)
    target.restoreState()


def _overlay_for_page(
    page_number: int,
    data: dict,
    width: float,
    height: float,
    notice: str,
) -> bytes:
    buffer = BytesIO()
    target = canvas.Canvas(buffer, pagesize=(width, height))
    target.setTitle("完整查估書前三頁草稿預覽")
    target.setAuthor("Land Valuation Assistant")
    if page_number == 1:
        _draw_page_one(target, data, width, notice)
    elif page_number == 2:
        _draw_page_two(target, data, width, notice)
    else:
        _draw_page_three_landscape(target, data, width, notice)
    target.save()
    return buffer.getvalue()


def _percent(value: object) -> str | None:
    if value is None or value == "":
        return None
    return f"{Decimal(str(value)) * 100}%"


def _build_three_page_pdf(
    data: dict,
    *,
    notice: str,
    title: str,
    subject: str,
) -> bytes:
    """Overlay confirmed backend draft data on the supplied blank A4 pages."""
    _register_cjk_font()
    if not TEMPLATE_PATH.is_file():
        raise RuntimeError("前三頁查估書範本不存在")
    template = PdfReader(str(TEMPLATE_PATH))
    if len(template.pages) != 3:
        raise RuntimeError("前三頁查估書範本頁數必須為 3")

    writer = PdfWriter(clone_from=template)
    for page_number, page in enumerate(writer.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if abs(width - A4[0]) > 1 or abs(height - A4[1]) > 1:
            raise RuntimeError("前三頁查估書範本必須為 A4 直向頁面")
        overlay = PdfReader(
            BytesIO(
                _overlay_for_page(
                    page_number, data, width, height, notice
                )
            )
        ).pages[0]
        page.merge_page(overlay)

    writer.add_metadata(
        {
            "/Title": title,
            "/Author": "Land Valuation Assistant",
            "/Subject": subject,
        }
    )
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    verification = PdfReader(BytesIO(result))
    if len(verification.pages) != 3:
        raise RuntimeError("前三頁草稿 PDF 產生後頁數驗證失敗")
    return result


def build_three_page_draft_pdf(data: dict, *, draft_notice: str = DRAFT_NOTICE) -> bytes:
    """Overlay confirmed backend draft data on the supplied blank A4 pages."""
    return _build_three_page_pdf(
        data,
        notice=draft_notice,
        title="完整查估書前三頁草稿預覽",
        subject="不含地圖與正式因素、價格計算",
    )


def build_three_page_formal_pdf(data: dict) -> bytes:
    """Render the calculated first three pages without any draft marking."""
    return _build_three_page_pdf(
        data,
        notice="",
        title="完整查估書前三頁",
        subject="經正式規則計算及整份檢核的查估書前三頁",
    )


def build_three_page_source_preserved_draft_pdf(
    source_pdf_bytes: bytes,
    *,
    draft_notice: str = DRAFT_NOTICE,
) -> bytes:
    """Preserve the first three filled source pages and add a draft notice.

    This path is only used when the completed extraction contains all three
    known report headings. It avoids losing source-visible fields that do not
    yet have a structured database column.
    """
    _register_cjk_font()
    source = PdfReader(BytesIO(source_pdf_bytes))
    if len(source.pages) < 3:
        raise RuntimeError("已填寫查估書來源至少必須包含前三頁")

    writer = PdfWriter()
    for source_page in source.pages[:3]:
        width = float(source_page.mediabox.width)
        height = float(source_page.mediabox.height)
        is_a4_portrait = abs(width - A4[0]) <= 1 and abs(height - A4[1]) <= 1
        is_a4_landscape = abs(width - A4[1]) <= 1 and abs(height - A4[0]) <= 1
        if not (is_a4_portrait or is_a4_landscape):
            raise RuntimeError("已填寫查估書來源前三頁必須為 A4 頁面")
        writer.add_page(source_page)
        overlay_buffer = BytesIO()
        target = canvas.Canvas(overlay_buffer, pagesize=(width, height))
        _draw_notice(target, width, height - 25, draft_notice)
        target.save()
        overlay = PdfReader(BytesIO(overlay_buffer.getvalue())).pages[0]
        writer.pages[-1].merge_page(overlay)

    writer.add_metadata(
        {
            "/Title": "已填寫來源保留－完整查估書前三頁草稿",
            "/Author": "Land Valuation Assistant",
            "/Subject": "保留來源前三頁原始內容；未執行正式因素與價格計算",
        }
    )
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    verification = PdfReader(BytesIO(result))
    if len(verification.pages) != 3:
        raise RuntimeError("來源保留草稿 PDF 產生後頁數驗證失敗")
    return result
