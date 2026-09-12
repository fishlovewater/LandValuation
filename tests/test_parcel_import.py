from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.core.spreadsheet_preview import SpreadsheetPreview, SpreadsheetPreviewSheet
from app.main import app
from app.valuation.parcel_import import parse_parcel_import_preview


def preview(rows, *, name="宗地個別因素清冊") -> SpreadsheetPreview:
    return SpreadsheetPreview(
        sheets=[
            SpreadsheetPreviewSheet(
                name=name,
                rows=rows,
                total_rows=len(rows),
                total_columns=max(len(row) for row in rows),
                truncated=False,
            )
        ],
        truncated=False,
    )


def parse(rows, *, existing=None, district="65000010", name="????????"):
    return parse_parcel_import_preview(
        preview(rows, name=name),
        case_district_code=district,
        existing_parcels=existing or [],
        document_id=uuid4(),
        filename="宗地個別因素清冊.xls",
    )


def test_official_transposed_table_7_creates_one_candidate_per_parcel_column() -> None:
    result = parse(
        [
            ["0 基本資料", "宗地流水號", "0001", "0002-01"],
            ["", "鄉鎮市區", "板橋區", "板橋區"],
            ["", "段小段名稱", "文化段一小段", "文化段一小段"],
            ["", "地號", 30, "31-1"],
            ["", "土地所有權人或管理人姓名", "甲一", "乙二等3人"],
            ["1 宗地條件", "7 面積(M²)", 878, "952.50"],
            ["5 行政條件", "22 使用分區或編定用地", "住宅區", "住宅區"],
        ]
    )

    assert result.layout == "OFFICIAL_TRANSPOSED"
    assert result.ready_count == 2
    assert result.needs_confirmation_count == 0
    assert result.duplicate_count == 0
    first, second = result.candidates
    assert first.source_location.endswith("C欄")
    assert first.source_serial == "0001"
    assert first.source_owner_name == "甲一"
    assert first.district_code == "65000010"
    assert first.district_name == "板橋區"
    assert first.section_name == "文化段"
    assert first.subsection_name == "一小段"
    assert first.land_no == "30"
    assert str(first.area_sqm) == "878"
    assert first.land_use_zone == "住宅區"
    assert second.source_serial == "0002-01"
    assert second.land_no == "31-1"
    assert str(second.area_sqm) == "952.50"


def test_row_table_layout_is_supported_and_carries_repeated_location_fields() -> None:
    result = parse(
        [
            ["宗地流水號", "鄉鎮市區", "段小段名稱", "地號", "面積(M2)", "使用分區或編定用地"],
            ["0001", "板橋區", "江翠段", "100", 100.25, "住宅區"],
            ["0002", "", "", "101", 88, "住宅區"],
        ],
        name="匯入資料",
    )

    assert result.layout == "ROW_TABLE"
    assert result.ready_count == 2
    assert [item.land_no for item in result.candidates] == ["100", "101"]
    assert result.candidates[1].district_name == "板橋區"
    assert result.candidates[1].section_name == "江翠段"


def test_existing_parcel_is_marked_duplicate_not_ready_for_reimport() -> None:
    existing_id = uuid4()
    result = parse(
        [
            ["宗地流水號", "鄉鎮市區", "段小段名稱", "地號", "面積(M2)"],
            ["0001", "板橋區", "文化段", "30", 878],
        ],
        existing=[
            SimpleNamespace(
                parcel_id=existing_id,
                district_code="65000010",
                section_name="文化段",
                subsection_name="",
                land_no="30",
            )
        ],
    )

    assert result.duplicate_count == 1
    assert result.ready_count == 0
    assert result.candidates[0].status == "DUPLICATE"
    assert result.candidates[0].existing_parcel_id == existing_id


def test_cross_district_or_missing_area_requires_human_confirmation() -> None:
    result = parse(
        [
            ["宗地流水號", "鄉鎮市區", "段小段名稱", "地號", "面積(M2)"],
            ["0001", "新店區", "文化段", "30", ""],
        ]
    )

    assert result.needs_confirmation_count == 1
    candidate = result.candidates[0]
    assert candidate.status == "NEEDS_CONFIRMATION"
    assert any("行政區與案件不一致" in error for error in candidate.errors)
    assert "面積無法辨識或不是正數" in candidate.errors


def test_missing_district_uses_case_district_with_visible_warning() -> None:
    result = parse(
        [
            ["宗地流水號", "鄉鎮市區", "段小段名稱", "地號", "面積(M2)"],
            ["0001", "", "文化段", "30", 100],
        ]
    )

    candidate = result.candidates[0]
    assert candidate.status == "READY"
    assert candidate.district_code == "65000010"
    assert candidate.warnings == ["清冊未填行政區，已帶入案件行政區"]


def test_unrecognized_spreadsheet_fails_closed() -> None:
    with pytest.raises(AppError) as captured:
        parse([["案件名稱", "測試"], ["備註", "沒有宗地欄位"]])

    assert captured.value.code == "PARCEL_IMPORT_LAYOUT_UNRECOGNIZED"


def test_parcel_import_routes_are_exposed_in_openapi() -> None:
    paths = app.openapi()["paths"]

    assert (
        "/api/v1/valuation/cases/{case_id}/documents/{document_id}/parcel-import-preview"
        in paths
    )
    assert (
        "/api/v1/valuation/cases/{case_id}/documents/{document_id}/parcel-import"
        in paths
    )
