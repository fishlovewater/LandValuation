from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.valuation.report_packages.factor_catalog import INDIVIDUAL_FACTORS


@dataclass(frozen=True)
class PdfField:
    code: str
    label: str
    section: str


def fs(section: str, rows: tuple[tuple[str, str], ...]) -> list[PdfField]:
    return [PdfField(code, label, section) for code, label in rows]


F01_FIELDS = fs("案件與交易資料", (
    ("case_no", "案號"), ("case_type", "案件類型"), ("valuation_base_date", "估價基準日"),
    ("price_zone_no", "地價區段號"), ("transaction_no", "買賣實例編號"),
    ("transaction_date", "交易日期"), ("location", "土地坐落"),
    ("land_category", "地目／用地類別"), ("transaction_type", "交易類型"),
    ("land_area_sqm", "土地面積（㎡）"), ("building_area_sqm", "建物面積（㎡）"),
    ("transaction_total_price", "交易總價（元）"), ("land_transaction_price", "土地交易價格（元）"),
    ("building_transaction_price", "建物交易價格（元）"), ("parking_transaction_price", "車位交易價格（元）"),
    ("price_information_source", "價格資訊來源"), ("transaction_conditions", "交易情形"),
)) + fs("權利、管制與現況", (
    ("rights_scope", "權利範圍"), ("ownership_type", "所有權型態"),
    ("land_use_zone", "使用分區或編定用地"), ("designated_use", "使用地類別"),
    ("current_use", "目前使用狀況"), ("building_status", "建物資料及現況"),
    ("encumbrance_status", "他項權利及負擔"), ("road_condition", "臨路條件"),
)) + fs("價格正常化與簽章", (
    ("building_price_deduction", "建物價格扣除（元）"), ("parking_price_deduction", "車位價格扣除（元）"),
    ("special_transaction_adjustment", "特殊交易情況修正率"),
    ("special_adjustment_source_notes", "特殊交易修正依據"),
    ("normal_land_total_price", "正常土地總價（元）"), ("normal_land_unit_price", "土地正常單價（元／㎡）"),
    ("normalization_notes", "價格正常化說明"), ("filled_date", "填表日期"),
    ("handler_name", "承辦員"), ("section_head_name", "課（股）長"),
    ("director_name", "主任（局、處長）"), ("appraiser_name", "不動產估價師"),
))


def f02_fields() -> list[PdfField]:
    result = fs("基本資料", (("case_no", "案號"), ("valuation_base_date", "估價基準日"),
        ("benchmark_land_id", "比準地編號"), ("benchmark_land_no", "比準地地號"),
        ("benchmark_location", "比準地土地坐落")))
    for target in range(1, 4):
        p = f"target_{target}"
        result += fs(f"比較標的 {target}－基本及價格調整", (
            (f"{p}_comparison_target_id", "比較標的編號"), (f"{p}_transaction_no", "買賣實例編號"),
            (f"{p}_location", "土地坐落"), (f"{p}_normal_unit_price", "土地正常單價（元／㎡）"),
            (f"{p}_transaction_date", "交易日期"), (f"{p}_time_adjustment_rate", "交易日期調整率"),
            (f"{p}_date_adjusted_price", "調整至估價基準日單價"), (f"{p}_price_zone_no", "地價區段號"),
            (f"{p}_regional_adjustment_rate", "區域因素調整率")))
        for factor in INDIVIDUAL_FACTORS:
            result += fs(f"比較標的 {target}－個別因素", (
                (f"{p}_{factor.code}_benchmark_condition", f"{factor.label}－比準地條件"),
                (f"{p}_{factor.code}_comparable_condition", f"{factor.label}－比較標的條件"),
                (f"{p}_{factor.code}_adjustment_rate", f"{factor.label}－調整率")))
        result += fs(f"比較標的 {target}－結果", (
            (f"{p}_individual_adjustment_rate", "個別因素調整合計"),
            (f"{p}_total_adjustment_absolute", "調整率絕對值加總"),
            (f"{p}_similarity_level", "價格形成因素相近程度"),
            (f"{p}_trial_price", "試算價格（元／㎡）"), (f"{p}_weight", "權重"),
            (f"{p}_weight_reason", "權重理由")))
    result += fs("比較法結論與簽章", (("benchmark_comparison_price", "比準地比較價格（元／㎡）"),
        ("benchmark_notes", "比準地及比較標的說明"), ("notes", "全案說明及備註"),
        ("filled_date", "填表日期"), ("handler_name", "承辦員"), ("section_head_name", "課（股）長"),
        ("director_name", "主任（局、處長）"), ("appraiser_name", "不動產估價師")))
    return result


F03_FIELDS = fs("基本資料", (("case_no", "案號"), ("valuation_base_date", "估價基準日"),
    ("benchmark_land_id", "比準地編號"), ("benchmark_land_no", "比準地地號"),
    ("price_zone_no", "地價區段號"), ("benchmark_location", "土地坐落"),
    ("benchmark_area_sqm", "面積（㎡）"), ("land_use_zone", "使用分區或編定用地"))) + fs("估價方法與權重", (
    ("comparison_price", "比較法價格（元／㎡）"), ("comparison_weight", "比較法權重"),
    ("income_price", "收益法價格（元／㎡）"), ("income_weight", "收益法權重"),
    ("benchmark_land_price", "比準地地價（元／㎡）"), ("decision_reason", "價格決定理由"))) + fs("市場資料與簽章", (
    ("market_period_start", "案例蒐集期間起日"), ("market_period_end", "案例蒐集期間迄日"),
    ("market_condition", "市場概況"), ("selection_scope_reason", "案例範圍及選取理由"),
    ("notes", "備註"), ("filled_date", "填表日期"), ("handler_name", "承辦員"),
    ("section_head_name", "課（股）長"), ("director_name", "主任（局、處長）"),
    ("appraiser_name", "不動產估價師")))


def f04_fields(max_rows: int = 20) -> list[PdfField]:
    result = fs("案件、區段與比準地", (("case_no", "案號"), ("valuation_base_date", "估價基準日"),
        ("price_zone_no", "地價區段號"), ("benchmark_valuation_id", "比準地估價結果編號"),
        ("benchmark_land_no", "比準地地號"), ("benchmark_land_price", "比準地地價（元／㎡）"),
        ("rule_version_id", "正式規則版本")))
    for row in range(1, max_rows + 1):
        p = f"parcel_{row}"
        result += fs(f"宗地清冊第 {row} 筆", ((f"{p}_serial_no", "流水號"), (f"{p}_parcel_id", "宗地編號"),
            (f"{p}_district_code", "行政區"), (f"{p}_section_name", "地段"), (f"{p}_subsection_name", "小段"),
            (f"{p}_land_no", "地號"), (f"{p}_area_sqm", "面積（㎡）"),
            (f"{p}_ownership_numerator", "權利範圍分子"), (f"{p}_ownership_denominator", "權利範圍分母"),
            (f"{p}_ownership_ratio", "權利比例"), (f"{p}_land_use_zone", "使用分區"),
            (f"{p}_designated_use", "編定用地"), (f"{p}_parcel_adjustment_rate", "宗地修正率"),
            (f"{p}_parcel_unit_price", "宗地單價（元／㎡）"), (f"{p}_parcel_total_value", "宗地總價（元）"),
            (f"{p}_notes", "備註")))
    result += fs("合計與簽章", (("parcel_count", "宗地筆數"), ("total_area_sqm", "面積合計（㎡）"),
        ("total_value", "宗地市價合計（元）"), ("notes", "全案備註"), ("filled_date", "填表日期"),
        ("handler_name", "承辦員"), ("section_head_name", "課（股）長"),
        ("director_name", "主任（局、處長）"), ("appraiser_name", "不動產估價師")))
    return result


OFFICIAL_PDF_FIELDS = {"F01": tuple(F01_FIELDS), "F02": tuple(f02_fields()), "F03": tuple(F03_FIELDS), "F04": tuple(f04_fields())}


def flatten_pdf_values(form_code: str, data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    values = {**{k: v for k, v in context.items() if not isinstance(v, (list, dict))},
              **{k: v for k, v in data.items() if not isinstance(v, (list, dict))}}
    if form_code == "F02":
        for target in data.get("comparison_targets") or []:
            order = target.get("display_order")
            if order not in (1, 2, 3):
                continue
            p = f"target_{order}"
            for key, value in target.items():
                if key != "individual_factors": values[f"{p}_{key}"] = value
            for factor in target.get("individual_factors") or []:
                code = factor.get("factor_code")
                if code:
                    values[f"{p}_{code}_benchmark_condition"] = factor.get("benchmark_confirmed_level") or factor.get("benchmark_reported_level")
                    values[f"{p}_{code}_comparable_condition"] = factor.get("comparable_confirmed_level") or factor.get("comparable_reported_level")
                    values[f"{p}_{code}_adjustment_rate"] = factor.get("calculated_adjustment_rate")
    if form_code == "F04":
        parcels = {str(item.get("parcel_id")): item for item in context.get("parcels", [])}
        total_area = total_value = 0.0
        for index, row in enumerate((data.get("parcel_rows") or [])[:20], 1):
            p = f"parcel_{index}"
            details = parcels.get(str(row.get("parcel_id")), {})
            for key, value in {**details, **row, "serial_no": index}.items(): values[f"{p}_{key}"] = value
            total_area += float(details.get("area_sqm") or 0)
            total_value += float(row.get("parcel_total_value") or 0)
        values.update(parcel_count=len(data.get("parcel_rows") or []), total_area_sqm=total_area, total_value=total_value)
    allowed = {field.code for field in OFFICIAL_PDF_FIELDS[form_code]}
    return {key: value for key, value in values.items() if key in allowed}
