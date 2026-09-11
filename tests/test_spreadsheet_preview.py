from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
import pytest

from app.core.spreadsheet_preview import (
    XLS_MIME_TYPE,
    SpreadsheetPreviewTooLargeError,
    build_spreadsheet_preview,
    preview_storage_xlsx,
)


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    first = workbook.active
    first.title = "基本資料"
    first.append(["欄位", "值", "備註"])
    first.append(["估價基準日", date(2026, 9, 11), True])
    first.append(["單價", 123456.5, None])

    second = workbook.create_sheet("附件")
    second.append(["名稱", "狀態"])
    second.append(["地籍圖", "完成"])

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_build_spreadsheet_preview_serializes_values_and_multiple_sheets() -> None:
    preview = build_spreadsheet_preview(_workbook_bytes())

    assert preview.kind == "spreadsheet"
    assert [sheet.name for sheet in preview.sheets] == ["基本資料", "附件"]
    assert preview.sheets[0].rows[1] == ["估價基準日", "2026-09-11T00:00:00", True]
    assert preview.sheets[0].rows[2] == ["單價", 123456.5, None]
    assert preview.truncated is False


def test_build_spreadsheet_preview_reports_truncation_without_losing_dimensions() -> None:
    preview = build_spreadsheet_preview(
        _workbook_bytes(),
        max_sheets=1,
        max_rows=2,
        max_columns=2,
    )

    assert len(preview.sheets) == 1
    sheet = preview.sheets[0]
    assert sheet.total_rows == 3
    assert sheet.total_columns == 3
    assert sheet.rows == [["欄位", "值"], ["估價基準日", "2026-09-11T00:00:00"]]
    assert sheet.truncated is True
    assert preview.truncated is True


class _Response:
    def __init__(self, content: bytes):
        self.content = content
        self.closed = False
        self.released = False

    def read(self, amount: int) -> bytes:
        return self.content[:amount]

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _Storage:
    def __init__(self, response: _Response):
        self.response = response

    async def download(self, object_key: str) -> _Response:
        assert object_key == "cases/demo/source.xlsx"
        return self.response


@pytest.mark.asyncio
async def test_preview_storage_xlsx_stops_reading_after_configured_limit() -> None:
    response = _Response(b"x" * 17)

    with pytest.raises(SpreadsheetPreviewTooLargeError):
        await preview_storage_xlsx(
            _Storage(response),
            "cases/demo/source.xlsx",
            max_bytes=16,
        )

    assert response.closed is True
    assert response.released is True


def test_build_spreadsheet_preview_supports_legacy_xls() -> None:
    fixture = Path(__file__).with_name("fixtures") / "legacy-preview.xls"

    preview = build_spreadsheet_preview(fixture.read_bytes(), mime_type=XLS_MIME_TYPE)

    assert preview.kind == "spreadsheet"
    assert preview.truncated is False
    assert len(preview.sheets) == 1
    sheet = preview.sheets[0]
    assert sheet.name == "Legacy"
    assert sheet.total_rows == 2
    assert sheet.total_columns == 2
    assert sheet.rows == [["地號", "面積"], ["489", 123.5]]
