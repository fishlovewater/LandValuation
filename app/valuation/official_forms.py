"""Canonical blank form contracts derived from the supplied official PDFs.

The PDF files are layout/source references.  Case values shown in examples are
never copied into a new case.  Each field declares who is allowed to produce
the value so clients can distinguish uploaded facts, professional decisions,
rule-derived values, and deterministic calculations.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


OFFICIAL_SCHEMA_VERSION = "ntpc-official-forms-2026-v1"


@dataclass(frozen=True)
class OfficialField:
    code: str
    label: str
    value_type: str = "TEXT"
    source: str = "USER_OR_CONFIRMED_DOCUMENT"
    required_for_formal: bool = False
    unit: str | None = None


@dataclass(frozen=True)
class OfficialSection:
    code: str
    label: str
    fields: tuple[OfficialField, ...]


@dataclass(frozen=True)
class OfficialFormTemplate:
    form_code: str
    form_name: str
    source_title: str
    sections: tuple[OfficialSection, ...]
    calculated_fields: tuple[str, ...] = ()


def f(
    code: str,
    label: str,
    value_type: str = "TEXT",
    source: str = "USER_OR_CONFIRMED_DOCUMENT",
    required: bool = False,
    unit: str | None = None,
) -> OfficialField:
    return OfficialField(code, label, value_type, source, required, unit)


OFFICIAL_FORM_TEMPLATES: dict[str, OfficialFormTemplate] = {
    "S01": OfficialFormTemplate(
        "S01",
        "地價區段勘查表",
        "查估書表範本.pdf／表1",
        (
            OfficialSection("header", "基本資料", (
                f("investigation_period", "查估期間"),
                f("price_zone_no", "區段編號", required=True),
                f("district_boundary", "區段範圍", required=True),
                f("survey_date", "勘查日期", "DATE", required=True),
            )),
            OfficialSection("land_use_control", "土地使用管制", (
                f("urban_plan_status", "都市計畫內外"),
                f("land_use_zone", "使用分區或使用地類別"),
                f("building_coverage_rate", "建蔽率", "DECIMAL", unit="%"),
                f("floor_area_ratio", "容積率", "DECIMAL", unit="%"),
                f("prohibited_building", "有無禁止建築"),
                f("restricted_building", "有無限制建築"),
            )),
            OfficialSection("regional_factors", "區域因素勘查", (
                f("factor_observations", "交通、自然、公共建設、特殊設施、污染、工商活動等勘查結果", "LIST"),
            )),
            OfficialSection("site_status", "土地與建物現況", (
                f("land_improvement", "土地改良"),
                f("building_density", "建築密度"),
                f("building_type", "建築型態"),
                f("land_utilization", "土地利用現況"),
                f("site_opinion", "現場勘查意見"),
            )),
            OfficialSection("signatures", "簽章", (
                f("handler_name", "承辦員", source="USER_CONFIRMED"),
                f("section_head_name", "課（股）長", source="USER_CONFIRMED"),
                f("director_name", "主任（局、處長）", source="USER_CONFIRMED"),
                f("appraiser_name", "不動產估價師", source="USER_CONFIRMED"),
            )),
        ),
    ),
    "F01": OfficialFormTemplate(
        "F01",
        "買賣實例調查估價表",
        "買賣實例.pdf",
        (
            OfficialSection("transaction", "交易資料", (
                f("transaction_no", "實例編號", required=True),
                f("transaction_date", "交易日期", "DATE", required=True),
                f("location", "土地坐落", required=True),
                f("land_area_sqm", "土地面積", "DECIMAL", unit="㎡"),
                f("transaction_total_price", "交易總價", "DECIMAL", required=True, unit="元"),
                f("price_information_source", "價格資訊來源"),
                f("transaction_conditions", "交易情形"),
            )),
            OfficialSection("rights_and_use", "權利與使用現況", (
                f("rights_scope", "權利範圍"),
                f("land_use_zone", "使用分區或編定用地"),
                f("current_use", "目前使用狀況"),
                f("building_status", "建物資料"),
                f("encumbrance_status", "他項權利及負擔"),
            )),
            OfficialSection("price_normalization", "價格正常化", (
                f("building_price_deduction", "建物價格扣除", "DECIMAL", unit="元"),
                f("special_transaction_adjustment", "特殊交易情況修正", "DECIMAL", unit="%"),
                f("normal_land_total_price", "正常土地總價", "DECIMAL", "BACKEND_CALCULATED", unit="元"),
                f("normal_land_unit_price", "土地正常單價", "DECIMAL", "BACKEND_CALCULATED", True, "元/㎡"),
                f("normalization_notes", "價格正常化說明"),
            )),
        ),
        ("normal_land_total_price", "normal_land_unit_price"),
    ),
    "F02-RF": OfficialFormTemplate(
        "F02-RF",
        "影響地價區域因素分析明細表",
        "查估書表範本.pdf／表5-2",
        (
            OfficialSection("header", "基本資料", (
                f("case_no", "案號", source="CASE_CONTEXT", required=True),
                f("benchmark_land_id", "比準地", "UUID", required=True),
                f("comparison_targets", "比較標的1至3", "LIST", required=True),
                f("rule_version_id", "正式規則版本", "UUID", "PUBLISHED_RULE", True),
            )),
            OfficialSection("regional_factors", "區域因素", (
                f("factor_rows", "土地使用管制、交通運輸、自然條件、公共建設、特殊設施、環境污染、工商活動及其他因素", "LIST", required=True),
            )),
            OfficialSection("calculation", "修正結果", (
                f("group_subtotals", "各主要項目百分比小計", "OBJECT", "BACKEND_CALCULATED"),
                f("regional_adjustment_rates", "區域因素總修正數", "OBJECT", "BACKEND_CALCULATED", True, "%"),
            )),
        ),
        ("group_subtotals", "regional_adjustment_rates"),
    ),
    "F02": OfficialFormTemplate(
        "F02",
        "比較法調查估價表",
        "比較法查估.pdf／查估書表範本.pdf 表4",
        (
            OfficialSection("header", "基本資料", (
                f("valuation_base_date", "估價基準日", "DATE", "CASE_CONTEXT", True),
                f("case_no", "案號", source="CASE_CONTEXT", required=True),
                f("benchmark_land_id", "比準地", "UUID", required=True),
                f("comparison_targets", "比較標的1至3", "LIST", required=True),
            )),
            OfficialSection("price_adjustment", "價格調整", (
                f("normal_unit_price", "土地正常單價", "DECIMAL", "F01_RESULT", True, "元/㎡"),
                f("time_adjustment_rate", "交易日期調整百分率", "DECIMAL", "USER_CONFIRMED_RULE_INPUT", True, "%"),
                f("date_adjusted_price", "調整至估價基準日單價", "DECIMAL", "BACKEND_CALCULATED", unit="元/㎡"),
                f("regional_adjustment_rate", "區域因素調整百分率", "DECIMAL", "F02_RF_RESULT", True, "%"),
            )),
            OfficialSection("individual_factors", "個別因素調整", (
                f("individual_factors", "宗地、道路、接近、周邊環境、行政及其他條件", "LIST", required=True),
                f("individual_adjustment_rate", "個別因素調整合計", "DECIMAL", "BACKEND_CALCULATED", True, "%"),
            )),
            OfficialSection("result", "比較價格", (
                f("total_adjustment_absolute", "調整百分率絕對值加總", "DECIMAL", "BACKEND_CALCULATED", unit="%"),
                f("similarity_level", "價格形成因素相近程度", source="PUBLISHED_RULE"),
                f("trial_price", "試算價格", "DECIMAL", "BACKEND_CALCULATED", unit="元/㎡"),
                f("weight", "比較標的權重", "DECIMAL", "USER_CONFIRMED", True, "%"),
                f("benchmark_comparison_price", "比準地比較價格", "DECIMAL", "BACKEND_CALCULATED", True, "元/㎡"),
                f("notes", "備註及全案說明"),
            )),
        ),
        ("date_adjusted_price", "regional_adjustment_rate", "individual_adjustment_rate", "trial_price", "benchmark_comparison_price"),
    ),
    "F03": OfficialFormTemplate(
        "F03",
        "比準地地價估計表",
        "比準地查估.pdf",
        (
            OfficialSection("header", "基本資料", (
                f("valuation_base_date", "估價基準日", "DATE", "CASE_CONTEXT", True),
                f("benchmark_land_id", "比準地", "UUID", required=True),
                f("price_zone_no", "地價區段號", source="BENCHMARK_CONTEXT", required=True),
            )),
            OfficialSection("methods", "估價方法", (
                f("comparison_price", "比較法價格", "DECIMAL", "F02_RESULT", unit="元/㎡"),
                f("comparison_weight", "比較法權重", "DECIMAL", "USER_CONFIRMED", True, "%"),
                f("income_price", "收益法價格", "DECIMAL", unit="元/㎡"),
                f("income_weight", "收益法權重", "DECIMAL", "USER_CONFIRMED", True, "%"),
                f("decision_reason", "決定理由", source="USER_CONFIRMED"),
            )),
            OfficialSection("market", "市場資料", (
                f("market_period_start", "案例蒐集期間起日", "DATE"),
                f("market_period_end", "案例蒐集期間迄日", "DATE"),
                f("market_condition", "市場概況"),
                f("selection_scope_reason", "案例範圍及選取理由"),
            )),
            OfficialSection("result", "比準地價格", (
                f("benchmark_land_price", "比準地地價", "DECIMAL", "BACKEND_CALCULATED", True, "元/㎡"),
            )),
        ),
        ("benchmark_land_price",),
    ),
    "F04": OfficialFormTemplate(
        "F04",
        "徵收土地宗地市價估計表",
        "土地市價查估表.pdf",
        (
            OfficialSection("header", "案件與區段", (
                f("case_no", "案號", source="CASE_CONTEXT", required=True),
                f("valuation_base_date", "估價基準日", "DATE", "CASE_CONTEXT", True),
                f("price_zone_no", "地價區段號", required=True),
                f("benchmark_valuation_id", "比準地估價結果", "UUID", "F03_RESULT", True),
            )),
            OfficialSection("parcels", "宗地清冊", (
                f("parcel_rows", "宗地流水號、土地坐落、面積、權利範圍及使用分區", "LIST", required=True),
            )),
            OfficialSection("valuation", "宗地市價", (
                f("benchmark_land_price", "比準地地價", "DECIMAL", "F03_RESULT", True, "元/㎡"),
                f("parcel_adjustment_rate", "宗地個別條件修正率", "DECIMAL", "PUBLISHED_RULE", True, "%"),
                f("parcel_unit_price", "宗地單價", "DECIMAL", "BACKEND_CALCULATED", True, "元/㎡"),
                f("parcel_total_value", "宗地總價", "DECIMAL", "BACKEND_CALCULATED", True, "元"),
                f("notes", "備註"),
            )),
        ),
        ("parcel_unit_price", "parcel_total_value"),
    ),
}


FORMULA_POLICY = {
    "formula_code": "NTPC_COMPARISON_V1",
    "rounding_code": "NTPC_LAND_PRICE_V1",
    "source_roles": [
        "LEGAL_BASIS",
        "NATIONAL_MANUAL",
        "LOCAL_MANUAL",
        "FACTOR_STANDARD",
        "FORM_TEMPLATE",
    ],
    "formulas": {
        "F02.trial_price": "normal_unit_price * (1 + time_rate) * (1 + regional_rate) * (1 + individual_rate)",
        "F02.benchmark_comparison_price": "sum(trial_price * confirmed_weight)",
        "F03.benchmark_land_price": "comparison_price * comparison_weight + income_price * income_weight",
        "F04.parcel_unit_price": "benchmark_land_price * (1 + parcel_adjustment_rate)",
        "F04.parcel_total_value": "parcel_unit_price * parcel_area_sqm * ownership_ratio",
    },
    "safety": "範例數值不得成為正式規則；因素級距與修正率只能取自人工確認且已發布的規則版本。",
}


def _empty_value(field: OfficialField) -> Any:
    if field.value_type == "LIST":
        return []
    if field.value_type == "OBJECT":
        return {}
    return None


def template_contract(form_code: str) -> dict[str, Any]:
    template = OFFICIAL_FORM_TEMPLATES[form_code]
    return {
        "schema_version": OFFICIAL_SCHEMA_VERSION,
        "form_code": template.form_code,
        "form_name": template.form_name,
        "source_title": template.source_title,
        "sections": [
            {
                "code": section.code,
                "label": section.label,
                "fields": [field.__dict__ for field in section.fields],
            }
            for section in template.sections
        ],
        "calculated_fields": list(template.calculated_fields),
    }


def blank_form_content(form_code: str) -> dict[str, Any]:
    template = OFFICIAL_FORM_TEMPLATES[form_code]
    values = {
        field.code: _empty_value(field)
        for section in template.sections
        for field in section.fields
    }
    return {
        "schema_version": OFFICIAL_SCHEMA_VERSION,
        "template_source": template.source_title,
        "form_code": form_code,
        "data": values,
    }


def all_template_contracts() -> list[dict[str, Any]]:
    return [deepcopy(template_contract(code)) for code in OFFICIAL_FORM_TEMPLATES]
