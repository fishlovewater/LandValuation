from copy import deepcopy
from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.exceptions import AppError
from app.valuation.official_forms import OFFICIAL_SCHEMA_VERSION
from app.valuation.report_packages.official_template_overlay import (
    OFFICIAL_TEMPLATE_MANIFEST_VERSION,
    build_template_manifest_skeleton,
    overlay_official_blank_template,
    validate_template_manifest,
)


def template_pdf(*, interactive: bool = False) -> bytes:
    stream = BytesIO()
    target = canvas.Canvas(stream, pagesize=A4)
    target.setFont("Helvetica", 10)
    target.drawString(36, A4[1] - 36, "ORIGINAL-BACKGROUND")
    if interactive:
        target.acroForm.textfield(
            name="legacy_field",
            x=36,
            y=A4[1] - 90,
            width=120,
            height=18,
            borderWidth=1,
        )
    target.showPage()
    target.drawString(36, A4[1] - 36, "ORIGINAL-PAGE-2")
    target.save()
    return stream.getvalue()


def complete_manifest(template: bytes) -> dict:
    manifest = build_template_manifest_skeleton(
        template,
        ["case_no", "confirmed"],
        template_name="Official blank fixture",
    )
    manifest["placements"] = [
        {
            "field_code": "case_no",
            "page": 1,
            "box": [170, A4[1] - 90, 180, 20],
            "font_size": 9,
            "align": "LEFT",
            "kind": "TEXT",
        },
        {
            "field_code": "confirmed",
            "page": 2,
            "box": [170, A4[1] - 90, 40, 20],
            "font_size": 9,
            "align": "CENTER",
            "kind": "CHECKMARK",
        },
    ]
    manifest["unmapped_fields"] = []
    return manifest


def test_manifest_skeleton_pins_exact_template_identity_without_guessing_coordinates() -> None:
    template = template_pdf()

    manifest = build_template_manifest_skeleton(
        template,
        ["case_no", "case_no", "valuation_base_date"],
        template_name="Official blank fixture",
    )

    assert manifest["manifest_version"] == OFFICIAL_TEMPLATE_MANIFEST_VERSION
    assert manifest["schema_version"] == OFFICIAL_SCHEMA_VERSION
    assert len(manifest["template_sha256"]) == 64
    assert len(manifest["pages"]) == 2
    assert manifest["placements"] == []
    assert manifest["unmapped_fields"] == ["case_no", "valuation_base_date"]


def test_incomplete_mapping_cannot_be_used_for_formal_overlay() -> None:
    template = template_pdf()
    manifest = build_template_manifest_skeleton(
        template,
        ["case_no"],
        template_name="Official blank fixture",
    )

    with pytest.raises(AppError) as raised:
        validate_template_manifest(template, manifest)

    assert raised.value.code == "OFFICIAL_TEMPLATE_MAPPING_INCOMPLETE"


def test_template_hash_mismatch_prevents_reusing_coordinates_on_a_new_official_pdf() -> None:
    template = template_pdf()
    manifest = complete_manifest(template)
    changed = template + b"\n%different-official-revision"

    with pytest.raises(AppError) as raised:
        validate_template_manifest(changed, manifest)

    assert raised.value.code == "OFFICIAL_TEMPLATE_HASH_MISMATCH"


def test_out_of_bounds_coordinate_is_rejected_before_pdf_generation() -> None:
    template = template_pdf()
    manifest = complete_manifest(template)
    broken = deepcopy(manifest)
    broken["placements"][0]["box"] = [A4[0] - 10, 10, 30, 20]

    with pytest.raises(AppError) as raised:
        validate_template_manifest(template, broken)

    assert raised.value.code == "OFFICIAL_TEMPLATE_PLACEMENT_OUT_OF_BOUNDS"


def test_overlay_preserves_original_pages_and_adds_only_calibrated_values() -> None:
    template = template_pdf(interactive=True)
    manifest = complete_manifest(template)

    rendered = overlay_official_blank_template(
        template,
        manifest,
        {"case_no": "CASE-001", "confirmed": True},
    )

    reader = PdfReader(BytesIO(rendered))
    assert len(reader.pages) == 2
    first_page_text = reader.pages[0].extract_text() or ""
    second_page_text = reader.pages[1].extract_text() or ""
    assert "ORIGINAL-BACKGROUND" in first_page_text
    assert "CASE-001" in first_page_text
    assert "ORIGINAL-PAGE-2" in second_page_text
    assert not (reader.get_fields() or {})
    assert not (reader.pages[0].get("/Annots") or [])