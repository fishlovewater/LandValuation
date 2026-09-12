import json
from pathlib import Path

from app.valuation.report_packages.factor_catalog import TEMPLATE_FACTORS


_CATALOG_DIRECTORY = Path(__file__).with_name("field_catalogs")


def _read_catalog(filename: str):
    with (_CATALOG_DIRECTORY / filename).open(encoding="utf-8") as source:
        return json.load(source)


F01_FIELD_ANALYSIS_FIELDS: dict[str, str] = _read_catalog("f01.json")
F02_FIELD_ANALYSIS_FIELDS: dict[str, str] = _read_catalog("f02.json")
F03_FIELD_ANALYSIS_FIELDS: dict[str, str] = _read_catalog("f03.json")
F04_FIELD_ANALYSIS_FIELDS: dict[str, str] = _read_catalog("f04.json")
S01_FIELD_ANALYSIS_FIELDS: dict[str, str] = _read_catalog("s01.json")
_F02_RF_COMMERCIAL_SOURCE_ITEMS: list[dict[str, object]] = _read_catalog(
    "f02_rf_commercial.json"
)

if len(_F02_RF_COMMERCIAL_SOURCE_ITEMS) != len(TEMPLATE_FACTORS):
    raise RuntimeError("F02-RF commercial catalog does not match the template factor count")


F02_RF_FIELD_ANALYSIS_FIELDS: dict[str, str] = {
    factor.code: (
        f"{factor.label}; commercial source item "
        f"{source_item['source_item_code']}: {source_item['label']}; "
        "extract only a document-grounded observed value or explicit level"
    )
    for factor, source_item in zip(
        TEMPLATE_FACTORS, _F02_RF_COMMERCIAL_SOURCE_ITEMS, strict=True
    )
}

# Keep the source-item to canonical AI field-name mapping available to the
# prompt validator as well as the report-package code.  The source workbook
# uses C1_01...C8_01 labels, while AI must return the corresponding
# ``TemplateFactor.code`` value.
F02_RF_SOURCE_ITEM_FIELD_MAP: dict[str, str] = {
    str(source_item["source_item_code"]): factor.code
    for factor, source_item in zip(
        TEMPLATE_FACTORS, _F02_RF_COMMERCIAL_SOURCE_ITEMS, strict=True
    )
}


# These labels are derived from the same catalogues injected into
# ``field_rules.md`` and AI prompts.  Candidate cards must not fall back to a
# vague form-level title simply because the field is not a formal-report field.
_FIELD_LABEL_OVERRIDES: dict[tuple[str, str], str] = {
    ("F01", "case_and_instance_refs"): "年期、區段號及實例編號",
    ("F01", "construction_unit_adjustment"): "建築單價調整率",
    ("F01", "normal_land_unit_price_raw"): "土地正常買賣單價精確值",
    ("F01", "normal_total_price_raw"): "正常買賣總價格精確值",
    ("F02", "basic_description"): "基本資料／土地標示",
    ("F02", "subject_role"): "比較標的角色",
}


FIELD_ANALYSIS_CATALOGS: dict[str, dict[str, str]] = {
    "F01": F01_FIELD_ANALYSIS_FIELDS,
    "F02": F02_FIELD_ANALYSIS_FIELDS,
    "F02-RF": F02_RF_FIELD_ANALYSIS_FIELDS,
    "F03": F03_FIELD_ANALYSIS_FIELDS,
    "F04": F04_FIELD_ANALYSIS_FIELDS,
    "S01": S01_FIELD_ANALYSIS_FIELDS,
}


def field_input_guidance(form_code: str, field_name: str) -> str:
    """Return the canonical evidence and input instruction for an AI field."""

    return FIELD_ANALYSIS_CATALOGS.get(form_code, {}).get(field_name, "")


def field_label_zh(form_code: str, field_name: str) -> str:
    """Return a concise Chinese field name for a candidate-confirmation card."""

    override = _FIELD_LABEL_OVERRIDES.get((form_code, field_name))
    if override:
        return override

    guidance = field_input_guidance(form_code, field_name)
    if guidance:
        # Catalog entries start with the canonical Chinese field meaning; later
        # clauses give evidence sources, calculation rules, and constraints.
        return guidance.split("；", 1)[0].strip()

    # Preserve an unknown key for diagnosis instead of concealing it with a
    # generic phrase such as "pending field".
    return field_name
