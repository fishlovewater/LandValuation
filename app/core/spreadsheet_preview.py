from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from fastapi.concurrency import run_in_threadpool
from openpyxl import load_workbook
from pydantic import BaseModel


class SpreadsheetPreviewTooLargeError(ValueError):
    pass


class SpreadsheetPreviewSheet(BaseModel):
    name: str
    rows: list[list[str | int | float | bool | None]]
    total_rows: int
    total_columns: int
    truncated: bool


class SpreadsheetPreview(BaseModel):
    kind: str = "spreadsheet"
    sheets: list[SpreadsheetPreviewSheet]
    truncated: bool


def _cell_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def build_spreadsheet_preview(
    content: bytes,
    *,
    max_sheets: int = 8,
    max_rows: int = 80,
    max_columns: int = 24,
) -> SpreadsheetPreview:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        sheets: list[SpreadsheetPreviewSheet] = []
        workbook_truncated = len(workbook.sheetnames) > max_sheets
        for worksheet in workbook.worksheets[:max_sheets]:
            total_rows = worksheet.max_row or 0
            total_columns = worksheet.max_column or 0
            rows: list[list[str | int | float | bool | None]] = []
            for row in worksheet.iter_rows(
                min_row=1,
                max_row=min(total_rows, max_rows),
                min_col=1,
                max_col=min(total_columns, max_columns),
                values_only=True,
            ):
                rows.append([_cell_value(value) for value in row])
            truncated = total_rows > max_rows or total_columns > max_columns
            workbook_truncated = workbook_truncated or truncated
            sheets.append(
                SpreadsheetPreviewSheet(
                    name=worksheet.title,
                    rows=rows,
                    total_rows=total_rows,
                    total_columns=total_columns,
                    truncated=truncated,
                )
            )
        return SpreadsheetPreview(sheets=sheets, truncated=workbook_truncated)
    finally:
        workbook.close()


async def preview_storage_xlsx(
    storage,
    object_key: str,
    *,
    max_bytes: int = 10 * 1024 * 1024,
) -> SpreadsheetPreview:
    response = await storage.download(object_key)
    try:
        content = await run_in_threadpool(response.read, max_bytes + 1)
    finally:
        response.close()
        response.release_conn()
    if len(content) > max_bytes:
        raise SpreadsheetPreviewTooLargeError(
            f"spreadsheet preview exceeds {max_bytes} bytes"
        )
    return await run_in_threadpool(build_spreadsheet_preview, content)
