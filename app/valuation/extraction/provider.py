import csv
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import AppError


FIELD_PATTERNS = (
    (
        "valuation_base_date",
        re.compile(
            r"(?:估價基準日|估價日期|勘查日期|查估日期|基準日)\s*[：:]?\s*"
            r"(?P<value>(?:\d{7,8}|\d{2,4}[年/.-]\d{1,2}[月/.-]\d{1,2}日?))"
        ),
    ),
    (
        "benchmark_land_no",
        re.compile(
            r"(?:比準地地號|比準地號|比較標的地號)\s*[：:]\s*"
            r"(?P<value>[^\s，,；;。]+)"
        ),
    ),
    (
        "price_zone_no",
        re.compile(
            r"(?:地價區段號|地價區段|區段號)\s*[：:]\s*"
            r"(?P<value>[^\s，,；;。]+)"
        ),
    ),
)




@dataclass(frozen=True)
class CandidateValue:
    field_name: str
    value: str
    confidence: Decimal
    source_page: int
    source_text: str
    form_code: str = "F03"


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    page_count: int
    candidates: tuple[CandidateValue, ...]
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentExtractionProvider:
    provider_name = "LOCAL_PDF"

    async def extract(self, content: bytes) -> ExtractionResult:
        raise NotImplementedError


HEURISTIC_LINE_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("valuation_base_date", re.compile(r"(?:估價基準日|估價日期|基準日)\s*[：:\s]\s*(?P<value>(?:\d{7,8}|\d{2,4}[年/.-]\d{1,2}[月/.-]\d{1,2}日?))")),
    ("benchmark_land_no", re.compile(r"(?:比準地地號|比準地號|比較標的地號|比準地)\s*[：:\s]\s*(?P<value>[^\s，,；;。]+地號|[^\s，,；;。]+)")),
    ("price_zone_no", re.compile(r"(?:地價區段編號|地價區段號|地價區段|區段號)\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("transaction_no", re.compile(r"(?:實例編號|交易案例編號|買賣實例編號)\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("transaction_date", re.compile(r"交易日期\s*[：:\s]\s*(?P<value>\d{2,4}[年/.-]\d{1,2}[月/.-]\d{1,2}日?)")),
    ("transaction_total_price", re.compile(r"(?:土地正常單價|總價格|成交總價)\s*[：:\s]\s*(?P<value>[\d,]+(?:\.\d+)?(?:\s*元／㎡|\s*元)?)")),
    ("urban_plan_status", re.compile(r"(?:都市計畫內外?|都市計畫)\s*[：:\s]\s*(?P<value>都市計畫內|都市計畫外|都內|都外)")),
    ("land_use_zone", re.compile(r"使用分區\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("building_coverage_rate", re.compile(r"建蔽率\s*[：:\s]\s*(?P<value>\d+(?:\.\d+)?\s*%?)")),
    ("floor_area_ratio", re.compile(r"容積率\s*[：:\s]\s*(?P<value>\d+(?:\.\d+)?\s*%?)")),
    ("prohibited_building", re.compile(r"(?:禁止建築|禁建)\s*[：:\s]\s*(?P<value>無|有|否|是)")),
    ("restricted_building", re.compile(r"(?:限制建築|限建)\s*[：:\s]\s*(?P<value>無|有|否|是)")),
    ("terrain", re.compile(r"(?:地勢狀況|地勢)\s*[：:\s]\s*(?P<value>平坦|平地|緩坡|微坡|低窪|陡坡)")),
    ("drainage", re.compile(r"排水良否\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("waste_facility", re.compile(r"廢棄物處理設施\s*[：:\s]\s*(?P<value>無|有|未發現)")),
    ("funeral_facility", re.compile(r"(?:墓地|殯儀館|火葬場|納骨塔)\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("main_road_width", re.compile(r"主要道路\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("average_road_width", re.compile(r"區段內道路平均寬度\s*[：:\s]\s*(?P<value>\d+(?:\.\d+)?\s*公尺)")),
    ("market_proximity", re.compile(r"市場\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("park_proximity", re.compile(r"公園\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("tourist_facility_proximity", re.compile(r"觀光遊憩設施\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
    ("parking_convenience", re.compile(r"停車場\s*[：:\s]\s*(?P<value>[^\s，,；;。]+)")),
)


def _normalized_candidate_value(field_name: str, value: str) -> str:
    """Normalize unambiguous date displays before asking a human to confirm.

    Government appraisal samples commonly print ROC dates compactly (for
    example ``1050901``).  The candidate keeps the OCR source text separately,
    while the proposed value is converted to the ISO date format accepted by
    the F03 API.  Ambiguous or invalid values are left untouched for manual
    correction.
    """

    if field_name != "valuation_base_date":
        return value
    raw = value.strip()
    compact = re.fullmatch(r"(\d{3})(\d{2})(\d{2})", raw)
    if compact:
        year, month, day = (int(part) for part in compact.groups())
        try:
            return date(year + 1911, month, day).isoformat()
        except ValueError:
            return value
    gregorian_compact = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", raw)
    if gregorian_compact:
        year, month, day = (int(part) for part in gregorian_compact.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return value
    separated = re.fullmatch(r"(\d{2,4})\D+(\d{1,2})\D+(\d{1,2})\D*", raw)
    if separated:
        year, month, day = (int(part) for part in separated.groups())
        if year < 1911:
            year += 1911
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return value
    return value


def _candidate_values(
    pages: list[str],
    *,
    page_lines: dict[int, list[tuple[str, Decimal]]] | None = None,
    default_confidence: Decimal = Decimal("0.9000"),
) -> tuple[CandidateValue, ...]:
    candidates: list[CandidateValue] = []
    seen: set[str] = set()

    for page_number, page_text in enumerate(pages, 1):
        lines = [line.strip() for line in page_text.split("\n") if line.strip()]
        for line in lines:
            for field_name, pattern in HEURISTIC_LINE_PATTERNS:
                if field_name in seen:
                    continue
                match = pattern.search(line)
                if match is None:
                    continue
                seen.add(field_name)
                raw_value = match.group("value").strip()
                val = _normalized_candidate_value(field_name, raw_value)
                confidence = default_confidence
                if page_lines is not None:
                    matching_confidences = [
                        line_confidence
                        for line_text, line_confidence in page_lines.get(page_number, [])
                        if raw_value in line_text
                    ]
                    if matching_confidences:
                        confidence = min(matching_confidences)
                candidates.append(
                    CandidateValue(
                        field_name=field_name,
                        value=val,
                        confidence=confidence,
                        source_page=page_number,
                        source_text=line,
                    )
                )

        for field_name, pattern in FIELD_PATTERNS:
            if field_name in seen:
                continue
            match = pattern.search(page_text)
            if match is None:
                continue
            seen.add(field_name)
            confidence = default_confidence
            if page_lines is not None:
                value = match.group("value")
                matching_confidences = [
                    line_confidence
                    for line_text, line_confidence in page_lines.get(page_number, [])
                    if value in line_text
                ]
                confidence = (
                    min(matching_confidences)
                    if matching_confidences
                    else Decimal("0.0000")
                )
            candidates.append(
                CandidateValue(
                    field_name=field_name,
                    value=_normalized_candidate_value(field_name, match.group("value")),
                    confidence=confidence,
                    source_page=page_number,
                    source_text=match.group(0),
                )
            )
    return tuple(candidates)



class LocalPdfExtractionProvider(DocumentExtractionProvider):
    provider_name = "LOCAL_PDF"
    _patterns = FIELD_PATTERNS

    async def extract(self, content: bytes) -> ExtractionResult:
        return await run_in_threadpool(self._extract_sync, content)

    def _extract_sync(self, content: bytes) -> ExtractionResult:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise AppError(
                "PDF_DEPENDENCY_MISSING",
                "文字型 PDF 擷取需要安裝 pypdf",
                503,
            ) from exc
        reader = PdfReader(BytesIO(content))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        full_text = "\n\n".join(text for text in pages if text)
        return ExtractionResult(
            text=full_text,
            page_count=len(pages),
            candidates=_candidate_values(pages),
            provider=self.provider_name,
        )


class XlsxExtractionProvider(DocumentExtractionProvider):
    provider_name = "LOCAL_XLSX"
    max_sheets = 30
    max_rows_per_sheet = 5000
    max_columns_per_sheet = 200
    max_nonempty_cells = 100000
    max_text_chars = 2_000_000

    async def extract(self, content: bytes) -> ExtractionResult:
        return await run_in_threadpool(self._extract_sync, content)

    @staticmethod
    def _comparison_target_candidates(
        rows: list[tuple[str, list[str]]], sheet_number: int
    ) -> tuple[CandidateValue, ...]:
        """Read the known comparison-target sheet without asking AI to infer roles."""
        values: dict[str, tuple[str, str]] = {}
        for line, cells in rows:
            for index, label in enumerate(cells[:-1]):
                key = re.sub(r"\s+", "", label).casefold()
                value = cells[index + 1]
                if key in {
                    "\u5be6\u4f8b\u7de8\u865f", "\u4ea4\u6613\u65e5\u671f", "\u884c\u653f\u5340", "\u6bb5", "\u5730\u865f", "\u9762\u7a4d",
                    "\u571f\u5730\u6b63\u5e38\u55ae\u50f9", "\u4ea4\u6613\u7e3d\u50f9", "\u6210\u4ea4\u7e3d\u50f9", "\u6b63\u5e38\u8cb7\u8ce3\u7e3d\u50f9\u683c",
                } and value:
                    values.setdefault(key, (value, line))

        candidates: list[CandidateValue] = []

        def add(field_name: str, value_key: str) -> None:
            found = values.get(value_key)
            if found is None:
                return
            value, source_text = found
            candidates.append(CandidateValue(
                field_name=field_name, value=value, confidence=Decimal("1.0000"),
                source_page=sheet_number, source_text=source_text, form_code="F01",
            ))

        add("case_and_instance_refs", "\u5be6\u4f8b\u7de8\u865f")
        add("transaction_date", "\u4ea4\u6613\u65e5\u671f")
        add("land_area", "\u9762\u7a4d")
        add("normal_land_unit_price_raw", "\u571f\u5730\u6b63\u5e38\u55ae\u50f9")
        for total_price_label in ("\u4ea4\u6613\u7e3d\u50f9", "\u6210\u4ea4\u7e3d\u50f9", "\u6b63\u5e38\u8cb7\u8ce3\u7e3d\u50f9\u683c"):
            if total_price_label in values:
                add("transaction_total_price", total_price_label)
                break

        address_keys = ("\u884c\u653f\u5340", "\u6bb5", "\u5730\u865f")
        if all(key in values for key in address_keys):
            address = "".join(values[key][0] for key in address_keys)
            if not address.endswith("\u5730\u865f"):
                address += "\u5730\u865f"
            source_text = "\n".join(dict.fromkeys(values[key][1] for key in address_keys))
            candidates.append(CandidateValue(
                field_name="property_registry_fields", value=address,
                confidence=Decimal("1.0000"), source_page=sheet_number,
                source_text=source_text, form_code="F01",
            ))
        return tuple(candidates)
    def _extract_sync(self, content: bytes) -> ExtractionResult:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise AppError(
                "XLSX_DEPENDENCY_MISSING",
                "Excel 擷取需要安裝 openpyxl",
                503,
            ) from exc
        try:
            workbook = load_workbook(
                BytesIO(content),
                read_only=True,
                data_only=False,
                keep_links=False,
            )
        except Exception as exc:
            raise AppError(
                "XLSX_SOURCE_INVALID",
                "Excel 檔案已損壞、加密或格式無法讀取",
                422,
            ) from exc

        try:
            if len(workbook.worksheets) > self.max_sheets:
                raise AppError(
                    "XLSX_LIMIT_EXCEEDED",
                    f"Excel 工作表數量不可超過 {self.max_sheets}",
                    422,
                )
            sheets: list[str] = []
            candidates: list[CandidateValue] = []
            nonempty_cells = 0
            total_chars = 0
            for sheet_number, worksheet in enumerate(workbook.worksheets, 1):
                lines = [f"[工作表：{worksheet.title}]"]
                structured_rows: list[tuple[str, list[str]]] = []
                for row_number, row in enumerate(
                    worksheet.iter_rows(max_col=self.max_columns_per_sheet), 1
                ):
                    if row_number > self.max_rows_per_sheet:
                        raise AppError(
                            "XLSX_LIMIT_EXCEEDED",
                            f"工作表 {worksheet.title} 超過 {self.max_rows_per_sheet} 列",
                            422,
                        )
                    values: list[str] = []
                    for cell in row:
                        if cell.value is None:
                            continue
                        nonempty_cells += 1
                        if nonempty_cells > self.max_nonempty_cells:
                            raise AppError(
                                "XLSX_LIMIT_EXCEEDED",
                                "Excel 非空白儲存格數量超過系統上限",
                                422,
                            )
                        value = str(cell.value).replace("\r\n", " ").replace("\n", " ")
                        values.append(f"[{cell.coordinate}] {value}")
                    if values:
                        line = " | ".join(values)
                        total_chars += len(line)
                        if total_chars > self.max_text_chars:
                            raise AppError(
                                "XLSX_LIMIT_EXCEEDED",
                                "Excel 可擷取文字量超過系統上限",
                                422,
                            )
                        lines.append(line)
                        structured_rows.append(
                            (line, [str(cell.value).strip() for cell in row if cell.value is not None])
                        )
                sheets.append("\n".join(lines))
                if "\u6bd4\u8f03\u6a19\u7684" in worksheet.title:
                    candidates.extend(
                        self._comparison_target_candidates(structured_rows, sheet_number)
                    )
        finally:
            workbook.close()

        full_text = "\n\n".join(sheets)
        return ExtractionResult(
            text=full_text,
            page_count=len(sheets),
            # PDF heuristics assume label/value punctuation and can misread XLSX
            # cell separators. XLSX fields are deliberately left to the grounded
            # field-analysis prompt, which verifies candidates against this text.
            candidates=tuple(candidates),
            provider=self.provider_name,
        )


class XlsExtractionProvider(DocumentExtractionProvider):
    """Extract text from the legacy binary Excel format used by official forms.

    The land-acquisition appraisal handbook's parcel-factor workbook can arrive
    as ``.xls``.  Preview already supports that format; this provider keeps the
    extraction path consistent so the same file can proceed to grounded field
    analysis instead of becoming preview-only evidence.
    """

    provider_name = "LOCAL_XLS"
    max_sheets = XlsxExtractionProvider.max_sheets
    max_rows_per_sheet = XlsxExtractionProvider.max_rows_per_sheet
    max_columns_per_sheet = XlsxExtractionProvider.max_columns_per_sheet
    max_nonempty_cells = XlsxExtractionProvider.max_nonempty_cells
    max_text_chars = XlsxExtractionProvider.max_text_chars

    async def extract(self, content: bytes) -> ExtractionResult:
        return await run_in_threadpool(self._extract_sync, content)

    @staticmethod
    def _cell_text(xlrd_module: Any, workbook: Any, cell: Any) -> str:
        if cell.ctype in (xlrd_module.XL_CELL_EMPTY, xlrd_module.XL_CELL_BLANK):
            return ""
        if cell.ctype == xlrd_module.XL_CELL_BOOLEAN:
            return "true" if bool(cell.value) else "false"
        if cell.ctype == xlrd_module.XL_CELL_DATE:
            try:
                return xlrd_module.xldate_as_datetime(
                    cell.value, workbook.datemode
                ).isoformat()
            except Exception:
                return str(cell.value).strip()
        if cell.ctype == xlrd_module.XL_CELL_NUMBER:
            number = float(cell.value)
            return str(int(number)) if number.is_integer() else str(number)
        return str(cell.value).replace("\r\n", " ").replace("\n", " ").strip()

    def _extract_sync(self, content: bytes) -> ExtractionResult:
        try:
            import xlrd
        except ImportError as exc:
            raise AppError(
                "XLS_DEPENDENCY_MISSING",
                "舊版 Excel 擷取需要安裝 xlrd",
                503,
            ) from exc

        try:
            workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
        except Exception as exc:
            raise AppError(
                "XLS_SOURCE_INVALID",
                "Excel 檔案已損壞、加密或格式無法讀取",
                422,
            ) from exc

        try:
            if workbook.nsheets > self.max_sheets:
                raise AppError(
                    "XLS_LIMIT_EXCEEDED",
                    f"Excel 工作表數量不可超過 {self.max_sheets}",
                    422,
                )

            sheets: list[str] = []
            candidates: list[CandidateValue] = []
            nonempty_cells = 0
            total_chars = 0

            for sheet_number in range(1, workbook.nsheets + 1):
                worksheet = workbook.sheet_by_index(sheet_number - 1)
                if worksheet.nrows > self.max_rows_per_sheet:
                    raise AppError(
                        "XLS_LIMIT_EXCEEDED",
                        f"工作表 {worksheet.name} 超過 {self.max_rows_per_sheet} 列",
                        422,
                    )
                if worksheet.ncols > self.max_columns_per_sheet:
                    raise AppError(
                        "XLS_LIMIT_EXCEEDED",
                        f"工作表 {worksheet.name} 超過 {self.max_columns_per_sheet} 欄",
                        422,
                    )

                lines = [f"[工作表：{worksheet.name}]"]
                structured_rows: list[tuple[str, list[str]]] = []
                for row_index in range(worksheet.nrows):
                    row_values: list[str] = []
                    rendered_values: list[str] = []
                    for column_index in range(worksheet.ncols):
                        cell = worksheet.cell(row_index, column_index)
                        value = self._cell_text(xlrd, workbook, cell)
                        if not value:
                            continue
                        nonempty_cells += 1
                        if nonempty_cells > self.max_nonempty_cells:
                            raise AppError(
                                "XLS_LIMIT_EXCEEDED",
                                "Excel 非空白儲存格數量超過系統上限",
                                422,
                            )
                        row_values.append(value)
                        rendered_values.append(
                            f"[R{row_index + 1}C{column_index + 1}] {value}"
                        )
                    if rendered_values:
                        line = " | ".join(rendered_values)
                        total_chars += len(line)
                        if total_chars > self.max_text_chars:
                            raise AppError(
                                "XLS_LIMIT_EXCEEDED",
                                "Excel 可擷取文字量超過系統上限",
                                422,
                            )
                        lines.append(line)
                        structured_rows.append((line, row_values))

                sheets.append("\n".join(lines))
                if "比較標的" in worksheet.name:
                    candidates.extend(
                        XlsxExtractionProvider._comparison_target_candidates(
                            structured_rows, sheet_number
                        )
                    )
        finally:
            workbook.release_resources()

        return ExtractionResult(
            text="\n\n".join(sheets),
            page_count=len(sheets),
            candidates=tuple(candidates),
            provider=self.provider_name,
        )


def _default_command_runner(
    command: list[str], timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _join_ocr_tokens(tokens: list[str]) -> str:
    result = ""
    for token in tokens:
        if not result:
            result = token
            continue
        previous = result[-1]
        current = token[0]
        if (
            previous.isascii()
            and current.isascii()
            and previous.isalnum()
            and current.isalnum()
        ):
            result += " "
        result += token
    return result


class LocalOcrPdfExtractionProvider(DocumentExtractionProvider):
    provider_name = "LOCAL_OCR"

    def __init__(
        self,
        settings: Settings,
        *,
        command_runner: Callable[
            [list[str], float], subprocess.CompletedProcess[str]
        ] = _default_command_runner,
        executable_finder: Callable[[str], str | None] = shutil.which,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.command_runner = command_runner
        self.executable_finder = executable_finder
        self.monotonic = monotonic

    async def extract(self, content: bytes) -> ExtractionResult:
        return await run_in_threadpool(self._extract_sync, content)

    def _extract_sync(self, content: bytes) -> ExtractionResult:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise AppError(
                "PDF_DEPENDENCY_MISSING",
                "本機 OCR 需要安裝 pypdf",
                503,
            ) from exc

        page_count = len(PdfReader(BytesIO(content)).pages)
        if page_count > self.settings.local_ocr_max_pages:
            raise AppError(
                "LOCAL_OCR_PAGE_LIMIT_EXCEEDED",
                f"本機 OCR 最多處理 {self.settings.local_ocr_max_pages} 頁",
                422,
            )

        pdftoppm = self.executable_finder("pdftoppm")
        tesseract = self.executable_finder("tesseract")
        if not pdftoppm or not tesseract:
            raise AppError(
                "LOCAL_OCR_DEPENDENCY_MISSING",
                "本機 OCR 需要 Poppler pdftoppm 與 Tesseract",
                503,
            )

        deadline = self.monotonic() + self.settings.local_ocr_timeout_seconds
        with tempfile.TemporaryDirectory(prefix="land-valuation-ocr-") as temp_name:
            temp_dir = Path(temp_name)
            input_path = temp_dir / "input.pdf"
            output_prefix = temp_dir / "page"
            input_path.write_bytes(content)
            self._run_command(
                [
                    pdftoppm,
                    "-png",
                    "-r",
                    str(self.settings.local_ocr_dpi),
                    "-f",
                    "1",
                    "-l",
                    str(page_count),
                    str(input_path),
                    str(output_prefix),
                ],
                deadline,
                "LOCAL_OCR_RENDER_FAILED",
                "PDF 頁面轉圖失敗",
            )
            image_paths = sorted(
                temp_dir.glob("page-*.png"),
                key=self._rendered_page_number,
            )
            if len(image_paths) != page_count:
                raise AppError(
                    "LOCAL_OCR_RENDER_INCOMPLETE",
                    "PDF 頁面轉圖結果不完整",
                    503,
                )

            page_lines: dict[int, list[tuple[str, Decimal]]] = {}
            pages: list[str] = []
            for page_number, image_path in enumerate(image_paths, 1):
                tsv = self._run_command(
                    [
                        tesseract,
                        str(image_path),
                        "stdout",
                        "-l",
                        self.settings.local_ocr_languages,
                        "--psm",
                        str(self.settings.local_ocr_psm),
                        "tsv",
                    ],
                    deadline,
                    "LOCAL_OCR_FAILED",
                    "本機 OCR 文字辨識失敗",
                )
                lines = self._parse_tsv(tsv)
                page_lines[page_number] = lines
                pages.append("\n".join(text for text, _confidence in lines))

        return ExtractionResult(
            text="\n\n".join(text for text in pages if text),
            page_count=page_count,
            candidates=_candidate_values(pages, page_lines=page_lines),
            provider=self.provider_name,
        )

    def _run_command(
        self,
        command: list[str],
        deadline: float,
        error_code: str,
        error_message: str,
    ) -> str:
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise AppError(
                "LOCAL_OCR_TIMEOUT",
                "本機 OCR 處理逾時",
                503,
            )
        try:
            result = self.command_runner(command, remaining)
        except subprocess.TimeoutExpired as exc:
            raise AppError(
                "LOCAL_OCR_TIMEOUT",
                "本機 OCR 處理逾時",
                503,
            ) from exc
        if result.returncode != 0:
            raise AppError(error_code, error_message, 503)
        return result.stdout

    @staticmethod
    def _rendered_page_number(path: Path) -> int:
        match = re.search(r"-(\d+)\.png$", path.name)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_tsv(tsv: str) -> list[tuple[str, Decimal]]:
        grouped_words: dict[tuple[str, str, str], list[tuple[str, Decimal]]] = {}
        for row in csv.DictReader(StringIO(tsv), delimiter="\t"):
            text = (row.get("text") or "").strip()
            if row.get("level") != "5" or not text:
                continue
            try:
                confidence = Decimal(row.get("conf") or "-1")
            except ArithmeticError:
                continue
            if confidence < 0:
                continue
            key = (
                row.get("block_num") or "0",
                row.get("par_num") or "0",
                row.get("line_num") or "0",
            )
            grouped_words.setdefault(key, []).append((text, confidence))

        lines: list[tuple[str, Decimal]] = []
        for words in grouped_words.values():
            text = _join_ocr_tokens([word for word, _confidence in words])
            confidence = sum(
                (word_confidence for _word, word_confidence in words),
                Decimal("0"),
            ) / Decimal(len(words))
            normalized_confidence = min(
                max(confidence / Decimal("100"), Decimal("0")),
                Decimal("1"),
            ).quantize(Decimal("0.0001"))
            lines.append((text, normalized_confidence))
        return lines


class TextractPdfExtractionProvider(DocumentExtractionProvider):
    provider_name = "TEXTRACT"

    def __init__(
        self,
        settings: Settings,
        *,
        s3_client: Any | None = None,
        textract_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not settings.textract_region or not settings.textract_s3_bucket:
            raise AppError(
                "TEXTRACT_NOT_CONFIGURED",
                "Textract 尚未設定 AWS Region 與 S3 工作 bucket",
                503,
            )
        self.settings = settings
        self.sleep = sleep
        self.monotonic = monotonic
        if s3_client is not None and textract_client is not None:
            self.s3 = s3_client
            self.textract = textract_client
            return
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise AppError(
                "TEXTRACT_DEPENDENCY_MISSING",
                "Textract provider 需要 boto3",
                503,
            ) from exc
        client_config = Config(
            read_timeout=settings.textract_timeout_seconds,
            connect_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
        )
        self.s3 = s3_client or boto3.client(
            "s3",
            region_name=settings.textract_region,
            config=client_config,
        )
        self.textract = textract_client or boto3.client(
            "textract",
            region_name=settings.textract_region,
            config=client_config,
        )

    async def extract(self, content: bytes) -> ExtractionResult:
        return await run_in_threadpool(self._extract_sync, content)

    def _extract_sync(self, content: bytes) -> ExtractionResult:
        object_key = (
            f"{self.settings.textract_s3_prefix.rstrip('/')}/"
            f"{uuid4()}.pdf"
        )
        uploaded = False
        try:
            self.s3.put_object(
                Bucket=self.settings.textract_s3_bucket,
                Key=object_key,
                Body=content,
                ContentType="application/pdf",
            )
            uploaded = True
            return self._detect_text(object_key)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "TEXTRACT_UNAVAILABLE",
                "Textract 暫時無法使用",
                503,
            ) from exc
        finally:
            if uploaded:
                try:
                    self.s3.delete_object(
                        Bucket=self.settings.textract_s3_bucket,
                        Key=object_key,
                    )
                except Exception as exc:
                    raise AppError(
                        "TEXTRACT_TEMP_CLEANUP_FAILED",
                        "Textract 臨時文件清理失敗",
                        503,
                    ) from exc

    def _detect_text(self, object_key: str) -> ExtractionResult:
        use_analysis = hasattr(self.textract, "start_document_analysis")
        if use_analysis:
            started = self.textract.start_document_analysis(
                DocumentLocation={
                    "S3Object": {
                        "Bucket": self.settings.textract_s3_bucket,
                        "Name": object_key,
                    }
                },
                FeatureTypes=["FORMS", "TABLES", "LAYOUT"],
            )
            getter = self.textract.get_document_analysis
        else:
            started = self.textract.start_document_text_detection(
                DocumentLocation={
                    "S3Object": {
                        "Bucket": self.settings.textract_s3_bucket,
                        "Name": object_key,
                    }
                }
            )
            getter = self.textract.get_document_text_detection

        job_id = started["JobId"]
        deadline = self.monotonic() + self.settings.textract_timeout_seconds
        while True:
            response = getter(JobId=job_id, MaxResults=1000)
            status = response.get("JobStatus")
            if status == "IN_PROGRESS":
                now = self.monotonic()
                if now >= deadline:
                    raise AppError("TEXTRACT_TIMEOUT", "Textract \u8655\u7406\u903e\u6642\uff0c\u8acb\u7a0d\u5f8c\u91cd\u8a66", 503)
                self.sleep(
                    min(
                        self.settings.textract_poll_interval_seconds,
                        max(deadline - now, 0),
                    )
                )
                continue
            if status == "FAILED":
                raise AppError("TEXTRACT_FAILED", "Textract \u7121\u6cd5\u5b8c\u6210\u6587\u4ef6\u64f7\u53d6", 503)
            if status == "PARTIAL_SUCCESS":
                raise AppError("TEXTRACT_PARTIAL_SUCCESS", "Textract \u53ea\u5b8c\u6210\u90e8\u5206\u9801\u9762\uff0c\u672a\u5efa\u7acb\u4e0d\u5b8c\u6574\u64f7\u53d6\u7d50\u679c", 503)
            if status != "SUCCEEDED":
                raise AppError("TEXTRACT_INVALID_STATUS", "Textract \u56de\u50b3\u672a\u77e5\u8655\u7406\u72c0\u614b", 503)
            break

        responses = [response]
        next_token = response.get("NextToken")
        while next_token:
            response = getter(JobId=job_id, MaxResults=1000, NextToken=next_token)
            if response.get("JobStatus") != "SUCCEEDED":
                raise AppError("TEXTRACT_RESULT_INCOMPLETE", "Textract \u5206\u9801\u7d50\u679c\u4e0d\u5b8c\u6574", 503)
            responses.append(response)
            next_token = response.get("NextToken")
        return self._build_result(responses, structured=use_analysis)

    @staticmethod
    def _block_text(block: dict[str, Any], blocks_by_id: dict[str, dict[str, Any]]) -> str:
        values: list[str] = []
        for relationship in block.get("Relationships", []):
            if relationship.get("Type") != "CHILD":
                continue
            for child_id in relationship.get("Ids", []):
                child = blocks_by_id.get(child_id, {})
                if child.get("BlockType") == "WORD":
                    value = str(child.get("Text", "")).strip()
                    if value:
                        values.append(value)
                elif child.get("BlockType") == "SELECTION_ELEMENT":
                    if str(child.get("SelectionStatus", "")).upper() == "SELECTED":
                        values.append("\u5df2\u52fe\u9078")
        return " ".join(values)

    def _build_result(
        self,
        responses: list[dict[str, Any]],
        *,
        structured: bool = False,
    ) -> ExtractionResult:
        page_count = 0
        page_lines: dict[int, list[tuple[str, Decimal]]] = {}
        all_blocks: list[dict[str, Any]] = []
        for response in responses:
            page_count = max(page_count, int(response.get("DocumentMetadata", {}).get("Pages", 0)))
            all_blocks.extend(response.get("Blocks", []))

        if not structured:
            for block in all_blocks:
                if block.get("BlockType") != "LINE":
                    continue
                text = str(block.get("Text", "")).strip()
                if not text:
                    continue
                page_number = max(int(block.get("Page", 1)), 1)
                confidence = min(
                    max(Decimal(str(block.get("Confidence", 0))) / Decimal("100"), Decimal("0")),
                    Decimal("1"),
                ).quantize(Decimal("0.0001"))
                page_lines.setdefault(page_number, []).append((text, confidence))
                page_count = max(page_count, page_number)
            pages = [
                "\n".join(text for text, _confidence in page_lines.get(page, []))
                for page in range(1, page_count + 1)
            ]
            return ExtractionResult(
                text="\n\n".join(text for text in pages if text),
                page_count=page_count,
                candidates=_candidate_values(pages, page_lines=page_lines),
                provider=self.provider_name,
            )

        blocks_by_id = {str(block.get("Id")): block for block in all_blocks if block.get("Id")}
        page_extras: dict[int, list[str]] = {}
        metadata_blocks: list[dict[str, Any]] = []
        for block in all_blocks:
            block_type = block.get("BlockType")
            page_number = max(int(block.get("Page", 1)), 1)
            page_count = max(page_count, page_number)
            if block_type not in {"LINE", "TABLE", "CELL", "KEY_VALUE_SET", "SELECTION_ELEMENT"}:
                continue
            confidence = None
            if block.get("Confidence") is not None:
                confidence = float(
                    min(
                        max(Decimal(str(block["Confidence"])) / Decimal("100"), Decimal("0")),
                        Decimal("1"),
                    )
                )
            metadata_blocks.append({
                "id": block.get("Id"),
                "type": block_type,
                "page": page_number,
                "text": block.get("Text") or self._block_text(block, blocks_by_id),
                "confidence": confidence,
                "geometry": block.get("Geometry"),
            })
            if block_type == "LINE":
                text = str(block.get("Text", "")).strip()
                if text:
                    line_confidence = min(
                        max(Decimal(str(block.get("Confidence", 0))) / Decimal("100"), Decimal("0")),
                        Decimal("1"),
                    ).quantize(Decimal("0.0001"))
                    page_lines.setdefault(page_number, []).append((text, line_confidence))
            elif block_type == "KEY_VALUE_SET":
                entities = {str(item).upper() for item in block.get("EntityTypes", [])}
                if "KEY" not in entities:
                    continue
                key_text = self._block_text(block, blocks_by_id)
                value_text = ""
                for relationship in block.get("Relationships", []):
                    if relationship.get("Type") != "VALUE":
                        continue
                    for value_id in relationship.get("Ids", []):
                        value_text = self._block_text(blocks_by_id.get(value_id, {}), blocks_by_id)
                        if value_text:
                            break
                if key_text and value_text:
                    page_extras.setdefault(page_number, []).append(
                        f"\u8868\u55ae\u6b04\u4f4d\uff1a{key_text}\uff1a{value_text}"
                    )

        table_by_cell: dict[str, str] = {}
        for block in all_blocks:
            if block.get("BlockType") != "TABLE":
                continue
            for relationship in block.get("Relationships", []):
                if relationship.get("Type") == "CHILD":
                    for cell_id in relationship.get("Ids", []):
                        table_by_cell[str(cell_id)] = str(block.get("Id", ""))
        for block in all_blocks:
            if block.get("BlockType") != "CELL":
                continue
            text = self._block_text(block, blocks_by_id)
            if not text:
                continue
            page_number = max(int(block.get("Page", 1)), 1)
            row = block.get("RowIndex", "?")
            col = block.get("ColumnIndex", "?")
            page_extras.setdefault(page_number, []).append(
                f"\u8868\u683c{table_by_cell.get(str(block.get('Id', '')), '')} \u7b2c{row}\u5217\u7b2c{col}\u6b04\uff1a{text}"
            )

        pages: list[str] = []
        page_metadata: list[dict[str, Any]] = []
        for page in range(1, page_count + 1):
            lines = [text for text, _confidence in page_lines.get(page, [])]
            extras = list(dict.fromkeys(page_extras.get(page, [])))
            page_text = "\n".join([f"[\u7b2c {page} \u9801]", *lines, *extras]).strip()
            pages.append(page_text)
            page_metadata.append({
                "page": page,
                "text": page_text,
                "lines": [
                    {"text": text, "confidence": str(confidence)}
                    for text, confidence in page_lines.get(page, [])
                ],
            })
        return ExtractionResult(
            text="\n\n".join(text for text in pages if text),
            page_count=page_count,
            candidates=_candidate_values(pages, page_lines=page_lines),
            provider=self.provider_name,
            metadata={
                "provider": "TEXTRACT",
                "analysis_mode": "FORMS_TABLES_LAYOUT",
                "feature_types": ["FORMS", "TABLES", "LAYOUT"],
                "pages": page_metadata,
                "blocks": metadata_blocks,
            },
        )


class AutoPdfExtractionProvider(DocumentExtractionProvider):
    provider_name = "LOCAL_PDF"

    def __init__(
        self,
        local_provider: DocumentExtractionProvider | None = None,
        local_ocr_provider: DocumentExtractionProvider | None = None,
        textract_provider: DocumentExtractionProvider | None = None,
    ) -> None:
        self.local_provider = local_provider or LocalPdfExtractionProvider()
        self.local_ocr_provider = local_ocr_provider
        self.textract_provider = textract_provider

    async def extract(self, content: bytes) -> ExtractionResult:
        # When AWS is configured, Textract is the canonical first pass because
        # it preserves forms, tables, page coordinates, and confidence.
        # Local PDF/OCR remains a deterministic fallback for outages or blank
        # Textract results.
        if self.textract_provider is not None:
            textract_result = await self.textract_provider.extract(content)
            if textract_result.text.strip():
                return textract_result

        local_result = await self.local_provider.extract(content)
        if local_result.text.strip():
            return local_result
        if self.local_ocr_provider is not None:
            return await self.local_ocr_provider.extract(content)
        if self.textract_provider is not None:
            return textract_result
        return local_result


def build_document_extraction_provider(
    settings: Settings,
) -> DocumentExtractionProvider:
    local_provider = LocalPdfExtractionProvider()
    if settings.document_extraction_provider == "local_pdf":
        return local_provider

    local_ocr_provider = LocalOcrPdfExtractionProvider(settings)
    if settings.document_extraction_provider == "local_ocr":
        return local_ocr_provider

    textract_provider: DocumentExtractionProvider | None = None
    if settings.textract_region and settings.textract_s3_bucket:
        textract_provider = TextractPdfExtractionProvider(settings)
    elif settings.document_extraction_provider == "textract":
        raise AppError(
            "TEXTRACT_NOT_CONFIGURED",
            "Textract 尚未設定 AWS Region 與 S3 工作 bucket",
            503,
        )

    if settings.document_extraction_provider == "textract":
        return textract_provider
    return AutoPdfExtractionProvider(
        local_provider,
        local_ocr_provider,
        textract_provider,
    )
