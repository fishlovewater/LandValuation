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