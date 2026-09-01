from io import BytesIO

from pypdf import PdfReader

from app.valuation.official_field_catalog import OFFICIAL_PDF_FIELDS, flatten_pdf_values
from app.valuation.official_pdf_builder import (
    FORM_FIELD_COORDINATES,
    PAGE_SIZE,
    TEMPLATE_VERSION,
    build_official_form_pdf,
    coordinate_manifest,
)


def declared_fields(form_code: str) -> set[str]:
    return {field.code for field in OFFICIAL_PDF_FIELDS[form_code]}


def test_all_f01_f04_fields_have_one_fixed_coordinate_and_acroform_widget() -> None:
    for code in ("F01", "F02", "F03", "F04"):
        coordinates = FORM_FIELD_COORDINATES[code]
        names = [item["field_code"] for item in coordinates]
        assert len(names) == len(set(names))
        assert set(names) == declared_fields(code)
        reader = PdfReader(BytesIO(build_official_form_pdf(code, interactive_blank=True)))
        assert len(reader.pages) == coordinate_manifest(code)["page_count"]
        assert set(reader.get_fields() or {}) == declared_fields(code)
        assert sum(len(page.get("/Annots") or []) for page in reader.pages) == len(names)


def test_every_coordinate_is_inside_a4_landscape_page() -> None:
    width, height = PAGE_SIZE
    for code in ("F01", "F02", "F03", "F04"):
        manifest = coordinate_manifest(code)
        assert manifest["template_version"] == TEMPLATE_VERSION
        for item in manifest["fields"]:
            for x, y, w, h in (item["label_box"], item["value_box"]):
                assert 0 <= x < width
                assert 0 <= y < height
                assert w > 0 and h > 0
                assert x + w <= width
                assert y + h <= height


def test_filled_pdf_is_static_and_contains_no_editable_widgets() -> None:
    pdf = build_official_form_pdf(
        "F01",
        {"transaction_no": "TX-001", "location": "TEST-LOCATION"},
    )
    reader = PdfReader(BytesIO(pdf))
    assert not (reader.get_fields() or {})
    assert not (reader.pages[0].get("/Annots") or [])
    text = reader.pages[0].extract_text()
    assert "TX-001" in text
    assert "TEST-LOCATION" in text


def test_f02_expands_all_three_targets_and_twenty_individual_factors() -> None:
    names = declared_fields("F02")
    for target in range(1, 4):
        factor_fields = {name for name in names if name.startswith(f"target_{target}_individual_")}
        assert len(factor_fields) == 20 * 3 + 1
        assert f"target_{target}_trial_price" in names
        assert f"target_{target}_weight" in names


def test_f04_expands_twenty_parcel_rows_with_all_official_columns() -> None:
    names = declared_fields("F04")
    columns = ("serial_no", "parcel_id", "district_code", "section_name", "subsection_name",
        "land_no", "area_sqm", "ownership_numerator", "ownership_denominator", "ownership_ratio",
        "land_use_zone", "designated_use", "parcel_adjustment_rate", "parcel_unit_price",
        "parcel_total_value", "notes")
    for row in range(1, 21):
        assert {f"parcel_{row}_{column}" for column in columns}.issubset(names)


def test_nested_f02_values_are_flattened_into_fixed_pdf_cells() -> None:
    values = flatten_pdf_values("F02", {"comparison_targets": [{"display_order": 1,
        "comparison_target_id": "target-a", "individual_factors": [{"factor_code": "individual_area",
        "benchmark_confirmed_level": "L3", "comparable_confirmed_level": "L2",
        "calculated_adjustment_rate": "0.03"}]}]})
    assert values["target_1_comparison_target_id"] == "target-a"
    assert values["target_1_individual_area_benchmark_condition"] == "L3"
    assert values["target_1_individual_area_comparable_condition"] == "L2"
    assert values["target_1_individual_area_adjustment_rate"] == "0.03"
