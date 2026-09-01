from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import Iterable

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.valuation.extraction.field_analysis import FIELD_ANALYSIS_FIELDS
from app.valuation.official_field_catalog import OFFICIAL_PDF_FIELDS
from app.valuation.report_packages.factor_catalog import INDIVIDUAL_FACTORS, TEMPLATE_FACTORS

EXPLICIT_FIELD_LABELS: dict[str, str] = {
    # 一、宗地本身物理條件與個別因素 (F02 表4 比較法)
    "individual_area": "面積 (M²)",
    "individual_width": "寬度 (M)",
    "individual_depth": "深度 (M)",
    "individual_shape": "形狀",
    "individual_street_frontage": "臨街情形",
    "individual_terrain": "地勢",

    # 二、道路與交通條件（個別因素）
    "individual_road_type": "道路種類",
    "individual_front_road_width": "面前道路寬度 (M)",

    # 三、土地利用現況與改良
    "building_site_improvement_type": "建築基地改良項目",
    "building_site_improvements": "建築基地改良明細",
    "farmland_improvement_type": "農地改良項目",
    "farmland_improvements": "農地改良明細",
    "building_status": "房屋建築現況",
    "dominant_building_type": "建築形態",
    "current_land_use_type": "主要土地利用現況",

    # 四、特定周邊環境與工商活動
    "individual_school_proximity": "接近學校之程度",
    "school_proximity": "接近學校之程度",
    "individual_commercial_district_proximity": "接近商圈之程度",
    "commercial_district_proximity": "接近商圈之程度",
    "service_facility_proximity": "接近服務性設施之程度",
    "customer_traffic_level": "顧客通行量之多寡",
    "pedestrian_flow": "顧客通行量之多寡",
    "shop_contiguity_level": "店鋪之毗連狀態",
    "vacancy_rate": "店鋪之歇業狀態",

    # 五、嫌惡設施（獨立細項）
    "individual_undesirable_facility": "嫌惡設施之有無及接近程度",
    "substation_high_voltage_tower": "變電所或高壓鐵塔",
    "gas_oil_tank": "瓦斯槽或儲油槽",
    "cemetery": "墓地",
    "funeral_home": "殯儀館",
    "crematorium": "火葬場",
    "columbarium": "納骨塔",
    "funeral_facility": "殯葬設施之有無及接近程度",
    "sewage_plant": "污水處理場",
    "landfill_incinerator": "垃圾場、掩埋場或焚化爐",
    "waste_facility": "廢棄物處理設施之有無及接近程度",

    # 六、環境污染（獨立細項）
    "water_pollution": "水污染",
    "noise_pollution": "噪音污染",
    "air_pollution": "廢氣污染",
    "waste_pollution": "廢棄物污染",
    "environmental_pollution": "水、噪音、廢氣及廢棄物污染",

    # 七、估價計算與小計欄位
    "category_subtotal": "百分比小計",
    "subtotal_percentage": "百分比小計",
    "total_regional_factor_correction": "影響地價區域因素總修正數",
    "total_correction_percentage": "區域因素總修正數",
    "individual_factor_total": "個別因素調整百分率合計",
    "absolute_adjustment_total": "調整百分率絕對值加總",
    "trial_price": "試算價格（元／㎡）",
    "comparison_weight": "比較標的權重",
    "benchmark_comparison_price": "比準地比較價格（元／㎡）",

    # 八、名稱修復（修正括號截斷）
    "drainage_level": "保（排）水之良否",
    "drainage": "保（排）水之良否",
}


def _text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def get_field_label_zh(form_code: str, field_name: str) -> str:
    """Return the official Chinese label for a given form code and field name."""
    if field_name in EXPLICIT_FIELD_LABELS:
        return EXPLICIT_FIELD_LABELS[field_name]

    pdf_fields = OFFICIAL_PDF_FIELDS.get(form_code, ())
    for field in pdf_fields:
        if field.code == field_name:
            return field.label

    for factor in INDIVIDUAL_FACTORS:
        if factor.code == field_name:
            return factor.label

    for factor in TEMPLATE_FACTORS:
        if factor.code == field_name:
            return factor.label

    catalog = FIELD_ANALYSIS_FIELDS.get(form_code, {})
    raw_desc = catalog.get(field_name)
    if raw_desc:
        clean = re.split(r"[;；\n]", raw_desc)[0].strip()
        if clean:
            return clean

    for cat in FIELD_ANALYSIS_FIELDS.values():
        if field_name in cat:
            clean = re.split(r"[;；\n]", cat[field_name])[0].strip()
            if clean:
                return clean

    return field_name


STANDARD_FORM_ORDER = ("F03", "F01", "S01", "F02-RF", "F02", "F04")


def build_confirmation_export_xlsx(
    *,
    case_no: str,
    case_title: str,
    generated_at: datetime,
    candidates: Iterable[object],
) -> bytes:
    """Build a human-readable Excel review export listing all fields line by line."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "欄位確認結果"

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="B7C9D6"),
        right=Side(style="thin", color="B7C9D6"),
        top=Side(style="thin", color="B7C9D6"),
        bottom=Side(style="thin", color="B7C9D6"),
    )
    align_left = Alignment(horizontal="left", vertical="top", wrap_text=True)

    ws.append(["欄位確認結果清單"])
    ws.cell(row=1, column=1).font = Font(size=14, bold=True)
    ws.append([f"案件：{case_no} {case_title}"])
    ws.append([f"產生時間（UTC）：{generated_at.isoformat()} 此文件包含完整表單欄位對照，未辨識到之欄位自動留白。"])
    ws.append([])

    headers = [
        "表單",
        "欄位代碼",
        "欄位中文名稱",
        "狀態",
        "確認/修正值",
        "擷取原始值",
        "來源證據原文",
        "頁碼",
        "分析來源",
        "信心度",
        "建立時間",
    ]
    header_row_idx = 5
    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row_idx, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    candidates_list = list(candidates)
    grouped: dict[tuple[str, str], list[object]] = defaultdict(list)
    for c in candidates_list:
        code = getattr(c, "form_code", "")
        name = getattr(c, "field_name", "")
        if code and name:
            grouped[(code, name)].append(c)

    candidate_form_codes = {getattr(c, "form_code", "") for c in candidates_list if getattr(c, "form_code", "")}
    ordered_forms = list(STANDARD_FORM_ORDER)
    for f in sorted(candidate_form_codes):
        if f not in ordered_forms:
            ordered_forms.append(f)

    for form_code in ordered_forms:
        defined_catalog = FIELD_ANALYSIS_FIELDS.get(form_code, {})
        defined_fields = list(defined_catalog.keys())
        if not defined_fields and form_code in OFFICIAL_PDF_FIELDS:
            defined_fields = [f.code for f in OFFICIAL_PDF_FIELDS[form_code]]

        candidate_field_names = [name for (fc, name) in grouped if fc == form_code]
        all_fields = list(defined_fields)
        for name in candidate_field_names:
            if name not in all_fields:
                all_fields.append(name)

        for field_name in all_fields:
            label_zh = get_field_label_zh(form_code, field_name)
            field_candidates = grouped.get((form_code, field_name), [])

            if field_candidates:
                for candidate in field_candidates:
                    confirmed_val = getattr(candidate, "confirmed_value", None)
                    extracted_val = getattr(candidate, "extracted_value", None)
                    page_num = getattr(candidate, "page_number", None)
                    provider = getattr(candidate, "analysis_provider", None)
                    confidence = getattr(candidate, "confidence_score", None)
                    created_at = getattr(candidate, "created_at", None)

                    row = [
                        form_code,
                        field_name,
                        label_zh,
                        _text(getattr(candidate, "field_status", "")),
                        _text(confirmed_val) if confirmed_val is not None else "",
                        _text(extracted_val) if extracted_val is not None else "",
                        _text(getattr(candidate, "source_text", "")),
                        _text(page_num) if page_num is not None else "",
                        _text(provider) if provider is not None else "",
                        _text(confidence) if confidence is not None else "",
                        created_at.isoformat() if isinstance(created_at, datetime) else _text(created_at),
                    ]
                    ws.append(row)
                    current_row = ws.max_row
                    for col_idx in range(1, len(headers) + 1):
                        cell = ws.cell(row=current_row, column=col_idx)
                        cell.alignment = align_left
                        cell.border = thin_border
            else:
                row = [
                    form_code,
                    field_name,
                    label_zh,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
                ws.append(row)
                current_row = ws.max_row
                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=current_row, column=col_idx)
                    cell.alignment = align_left
                    cell.border = thin_border

    column_widths = [12, 25, 25, 15, 30, 30, 50, 10, 15, 12, 22]
    for i, width in enumerate(column_widths, start=1):
        col_letter = get_column_letter(i)
        ws.column_dimensions[col_letter].width = width

    ws.freeze_panes = f"A{header_row_idx + 1}"

    output = BytesIO()
    wb.save(output)
    return output.getvalue()
