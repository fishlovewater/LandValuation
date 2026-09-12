from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi.concurrency import run_in_threadpool
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError, StorageError
from app.core.spreadsheet_preview import (
    XLS_MIME_TYPE,
    XLSX_MIME_TYPE,
    SpreadsheetPreview,
    SpreadsheetPreviewTooLargeError,
    build_spreadsheet_preview,
)
from app.storage.service import StorageService
from app.valuation.documents.schemas import DocumentCategory
from app.valuation.documents.service import DocumentService
from app.valuation.rule_packs.coverage import NEW_TAIPEI_DISTRICTS
from app.valuation.schemas import (
    ParcelBatchImportRequest,
    ParcelBatchImportResponse,
    ParcelCreate,
    ParcelImportCandidateResponse,
    ParcelImportPreviewResponse,
    ParcelResponse,
)
from app.valuation.service import ValuationService

_SPREADSHEET_MIME_TYPES = {XLS_MIME_TYPE, XLSX_MIME_TYPE}
_DISTRICT_BY_NAME = {name: code for code, name in NEW_TAIPEI_DISTRICTS.items()}

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "serial": ("宗地流水號", "流水號"),
    "district": ("鄉鎮市區", "行政區", "鄉鎮區"),
    "section": ("段小段名稱", "段小段", "地段", "段名", "段"),
    "subsection": ("小段名稱", "小段名", "小段"),
    "land_no": ("地號",),
    "land_no_parent": ("地號母號", "母號"),
    "land_no_child": ("地號子號", "子號"),
    "owner": ("土地所有權人或管理人姓名", "所有權人或管理人姓名", "所有權人姓名"),
    "area": ("土地面積", "登記面積", "面積"),
    "land_use_zone": ("使用分區或編定用地", "土地使用分區", "使用分區"),
    "designated_use": ("編定使用種類", "編定用地", "編定用途"),
    "ownership_numerator": ("權利範圍分子", "持分分子"),
    "ownership_denominator": ("權利範圍分母", "持分分母"),
    "ownership": ("權利範圍", "持分"),
}


def _normalized_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"[\s\n\r\t:：()（）\[\]【】/／._-]+", "", text).lower()


def _display_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return unicodedata.normalize("NFKC", str(value)).strip()


def _matches_alias(value: object, aliases: tuple[str, ...]) -> bool:
    normalized = _normalized_text(value)
    if not normalized:
        return False
    return any(_normalized_text(alias) in normalized for alias in aliases)


def _field_for_header(value: object) -> str | None:
    normalized = _normalized_text(value)
    if not normalized:
        return None
    # Prefer the more specific labels before generic aliases such as 「段」 or 「持分」.
    fields = sorted(
        _FIELD_ALIASES,
        key=lambda key: max(len(_normalized_text(alias)) for alias in _FIELD_ALIASES[key]),
        reverse=True,
    )
    for field in fields:
        if any(_normalized_text(alias) == normalized for alias in _FIELD_ALIASES[field]):
            return field
    for field in fields:
        if any(
            len(_normalized_text(alias)) > 1
            and _normalized_text(alias) in normalized
            for alias in _FIELD_ALIASES[field]
        ):
            return field
    return None


def _decimal_value(value: object) -> Decimal | None:
    if value is None:
        return None
    raw = _display_text(value)
    if not raw:
        return None
    raw = raw.replace(",", "").replace("，", "")
    raw = re.sub(r"(?:平方公尺|平方公分|m2|m²|㎡)$", "", raw, flags=re.IGNORECASE).strip()
    try:
        result = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return result if result > 0 else None


def _ownership_values(
    numerator: object,
    denominator: object,
    combined: object,
) -> tuple[Decimal | None, Decimal | None]:
    num = _decimal_value(numerator)
    den = _decimal_value(denominator)
    if num is not None or den is not None:
        return num, den
    raw = _display_text(combined)
    if not raw:
        return None, None
    match = re.fullmatch(r"\s*([0-9.]+)\s*[/／]\s*([0-9.]+)\s*", raw)
    if not match:
        return None, None
    try:
        return Decimal(match.group(1)), Decimal(match.group(2))
    except InvalidOperation:
        return None, None


def _split_section(value: object, explicit_subsection: object = None) -> tuple[str | None, str]:
    raw = _display_text(value).replace(" ", "")
    subsection = _display_text(explicit_subsection).replace(" ", "")
    if not raw:
        return None, subsection
    if subsection:
        return raw, subsection
    match = re.fullmatch(r"(.+?段)(.+?小段)", raw)
    if match:
        return match.group(1), match.group(2)
    return raw, ""


def _land_number(direct: object, parent: object = None, child: object = None) -> str | None:
    raw = _display_text(direct)
    if raw:
        return raw.removesuffix("地號").strip()
    mother = _display_text(parent)
    sub = _display_text(child)
    if not mother:
        return None
    if not sub or sub in {"0", "00"}:
        return mother
    return f"{mother}-{sub}"


def _resolve_district(value: object, case_district_code: str) -> tuple[str | None, str | None, list[str]]:
    raw = _display_text(value).replace("臺", "台")
    warnings: list[str] = []
    if not raw:
        code = case_district_code if case_district_code in NEW_TAIPEI_DISTRICTS else None
        if code:
            warnings.append("清冊未填行政區，已帶入案件行政區")
            return code, NEW_TAIPEI_DISTRICTS[code], warnings
        return None, None, warnings

    compact = re.sub(r"\s+", "", raw).replace("新北市", "")
    if raw in NEW_TAIPEI_DISTRICTS:
        code = raw
    else:
        code = _DISTRICT_BY_NAME.get(compact)
        if code is None:
            code = next(
                (candidate for name, candidate in _DISTRICT_BY_NAME.items() if name in compact),
                None,
            )
    return code, NEW_TAIPEI_DISTRICTS.get(code) if code else None, warnings


def _identity(
    district_code: str | None,
    section_name: str | None,
    subsection_name: str,
    land_no: str | None,
) -> tuple[str, str, str, str] | None:
    if not district_code or not section_name or not land_no:
        return None
    normalize = lambda value: re.sub(r"\s+", "", value or "").lower()
    return (
        district_code,
        normalize(section_name),
        normalize(subsection_name),
        normalize(land_no),
    )


def _candidate(
    *,
    source_location: str,
    case_district_code: str,
    values: dict[str, object],
    existing: dict[tuple[str, str, str, str], UUID],
) -> ParcelImportCandidateResponse:
    district_code, district_name, warnings = _resolve_district(
        values.get("district"), case_district_code
    )
    section_name, subsection_name = _split_section(
        values.get("section"), values.get("subsection")
    )
    land_no = _land_number(
        values.get("land_no"), values.get("land_no_parent"), values.get("land_no_child")
    )
    area = _decimal_value(values.get("area"))
    ownership_numerator, ownership_denominator = _ownership_values(
        values.get("ownership_numerator"),
        values.get("ownership_denominator"),
        values.get("ownership"),
    )

    errors: list[str] = []
    if district_code is None:
        errors.append("行政區無法辨識")
    elif district_code != case_district_code:
        expected = NEW_TAIPEI_DISTRICTS.get(case_district_code, case_district_code)
        errors.append(f"行政區與案件不一致；本案為{expected}")
    if not section_name:
        errors.append("缺少段小段名稱")
    if not land_no:
        errors.append("缺少地號")
    if area is None:
        errors.append("面積無法辨識或不是正數")
    if (ownership_numerator is None) != (ownership_denominator is None):
        errors.append("權利範圍分子與分母需同時提供")
    if (
        ownership_numerator is not None
        and ownership_denominator is not None
        and ownership_numerator > ownership_denominator
    ):
        errors.append("權利範圍分子不可大於分母")

    key = _identity(district_code, section_name, subsection_name, land_no)
    existing_parcel_id = existing.get(key) if key else None
    if existing_parcel_id is not None:
        status = "DUPLICATE"
    elif errors:
        status = "NEEDS_CONFIRMATION"
    else:
        status = "READY"

    return ParcelImportCandidateResponse(
        source_location=source_location,
        source_serial=_display_text(values.get("serial")) or None,
        source_owner_name=_display_text(values.get("owner")) or None,
        district_code=district_code,
        district_name=district_name,
        section_name=section_name,
        subsection_name=subsection_name,
        land_no=land_no,
        area_sqm=area,
        land_use_zone=_display_text(values.get("land_use_zone")) or None,
        designated_use=_display_text(values.get("designated_use")) or None,
        ownership_numerator=ownership_numerator,
        ownership_denominator=ownership_denominator,
        status=status,
        errors=errors,
        warnings=warnings,
        existing_parcel_id=existing_parcel_id,
    )


def _transposed_field_rows(rows: list[list[object]]) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for row_index, row in enumerate(rows):
        # The official MOI Table 7 is transposed: each row has one descriptor
        # on the left and parcel values begin to its right. Use only the first
        # recognizable descriptor in a row. A later parcel value such as
        # "??????" can itself contain words like ???? and must not be
        # reclassified as another header, otherwise the data-start column moves
        # right and the first parcel is silently skipped.
        for column_index, value in enumerate(row[:8]):
            field = _field_for_header(value)
            if field is None:
                continue
            if field not in found:
                found[field] = (row_index, column_index)
            break
    return found


def _parse_transposed_sheet(
    sheet,
    *,
    case_district_code: str,
    existing: dict[tuple[str, str, str, str], UUID],
) -> list[ParcelImportCandidateResponse]:
    fields = _transposed_field_rows(sheet.rows)
    if "land_no" not in fields or "area" not in fields:
        return []
    if not ({"serial", "district", "section"} & set(fields)):
        return []

    descriptor_columns = [column for _, column in fields.values()]
    start_column = max(descriptor_columns) + 1
    max_columns = max((len(row) for row in sheet.rows), default=0)
    candidates: list[ParcelImportCandidateResponse] = []
    for column_index in range(start_column, max_columns):
        values: dict[str, object] = {}
        for field, (row_index, _label_column) in fields.items():
            row = sheet.rows[row_index]
            values[field] = row[column_index] if column_index < len(row) else None
        if not any(_display_text(values.get(key)) for key in ("serial", "land_no", "area")):
            continue
        candidates.append(
            _candidate(
                source_location=f"{sheet.name}!{get_column_letter(column_index + 1)}欄",
                case_district_code=case_district_code,
                values=values,
                existing=existing,
            )
        )
    return candidates


def _row_header_map(row: list[object]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for column_index, value in enumerate(row):
        field = _field_for_header(value)
        if field is not None and field not in mapping:
            mapping[field] = column_index
    return mapping


def _parse_row_sheet(
    sheet,
    *,
    case_district_code: str,
    existing: dict[tuple[str, str, str, str], UUID],
) -> list[ParcelImportCandidateResponse]:
    header_index: int | None = None
    header: dict[str, int] = {}
    best_score = 0
    for row_index, row in enumerate(sheet.rows[:40]):
        mapping = _row_header_map(row)
        has_land_number = "land_no" in mapping or "land_no_parent" in mapping
        score = sum(
            field in mapping
            for field in ("district", "section", "land_no", "land_no_parent", "area")
        )
        if has_land_number and "area" in mapping and score > best_score:
            header_index = row_index
            header = mapping
            best_score = score
    if header_index is None:
        return []

    candidates: list[ParcelImportCandidateResponse] = []
    carry: dict[str, object] = {}
    for row_index in range(header_index + 1, len(sheet.rows)):
        row = sheet.rows[row_index]
        values: dict[str, object] = {}
        for field, column_index in header.items():
            values[field] = row[column_index] if column_index < len(row) else None
        for field in ("district", "section", "subsection"):
            if _display_text(values.get(field)):
                carry[field] = values[field]
            elif field in carry:
                values[field] = carry[field]
        if not any(
            _display_text(values.get(key))
            for key in ("serial", "land_no", "land_no_parent", "area")
        ):
            continue
        candidates.append(
            _candidate(
                source_location=f"{sheet.name}!第 {row_index + 1} 列",
                case_district_code=case_district_code,
                values=values,
                existing=existing,
            )
        )
    return candidates


def parse_parcel_import_preview(
    preview: SpreadsheetPreview,
    *,
    case_district_code: str,
    existing_parcels: list,
    document_id: UUID,
    filename: str,
) -> ParcelImportPreviewResponse:
    existing = {
        key: parcel.parcel_id
        for parcel in existing_parcels
        if (
            key := _identity(
                parcel.district_code,
                parcel.section_name,
                parcel.subsection_name,
                parcel.land_no,
            )
        )
    }

    transposed_candidates: list[ParcelImportCandidateResponse] = []
    for sheet in preview.sheets:
        transposed_candidates.extend(
            _parse_transposed_sheet(
                sheet,
                case_district_code=case_district_code,
                existing=existing,
            )
        )
    if transposed_candidates:
        candidates = transposed_candidates
        layout = "OFFICIAL_TRANSPOSED"
    else:
        candidates = []
        for sheet in preview.sheets:
            candidates.extend(
                _parse_row_sheet(
                    sheet,
                    case_district_code=case_district_code,
                    existing=existing,
                )
            )
        layout = "ROW_TABLE"

    if not candidates:
        raise AppError(
            "PARCEL_IMPORT_LAYOUT_UNRECOGNIZED",
            "找不到宗地清冊的地號與面積欄位；請確認使用內政部宗地個別因素清冊或欄位名稱未被修改",
            422,
        )

    return ParcelImportPreviewResponse(
        document_id=document_id,
        filename=filename,
        layout=layout,
        candidates=candidates,
        ready_count=sum(item.status == "READY" for item in candidates),
        needs_confirmation_count=sum(item.status == "NEEDS_CONFIRMATION" for item in candidates),
        duplicate_count=sum(item.status == "DUPLICATE" for item in candidates),
    )


class ParcelImportService:
    def __init__(self, session: AsyncSession, storage: StorageService) -> None:
        self.session = session
        self.storage = storage
        self.documents = DocumentService(session, storage)
        self.valuation = ValuationService(session)

    async def _source_document(self, case_id: UUID, document_id: UUID, user: User):
        document = await self.documents.get_document(case_id, document_id, user)
        if document.document_type != DocumentCategory.PARCEL_FACTOR_LIST.value:
            raise AppError(
                "PARCEL_IMPORT_DOCUMENT_TYPE_REQUIRED",
                "只有分類為「宗地個別因素清冊」的文件可以批次匯入宗地",
                422,
            )
        if document.mime_type.lower() not in _SPREADSHEET_MIME_TYPES:
            raise AppError(
                "PARCEL_IMPORT_FORMAT_UNSUPPORTED",
                "宗地清冊批次匯入目前支援 XLS 或 XLSX",
                415,
            )
        return document

    async def preview(
        self, case_id: UUID, document_id: UUID, user: User
    ) -> ParcelImportPreviewResponse:
        case = await self.valuation.get_case(case_id, user)
        document = await self._source_document(case_id, document_id, user)
        max_bytes = get_settings().document_preview_max_bytes
        if document.file_size_bytes > max_bytes:
            raise AppError("PARCEL_IMPORT_TOO_LARGE", "宗地清冊檔案過大，無法進行批次匯入", 413)
        response = await self.storage.download(document.object_key)
        try:
            content = await run_in_threadpool(response.read, max_bytes + 1)
        except StorageError as exc:
            raise AppError("DOCUMENT_OBJECT_MISSING", "文件資料存在，但目前無法取得原始檔", 404) from exc
        finally:
            response.close()
            response.release_conn()
        if len(content) > max_bytes:
            raise AppError("PARCEL_IMPORT_TOO_LARGE", "宗地清冊檔案過大，無法進行批次匯入", 413)
        try:
            preview = await run_in_threadpool(
                build_spreadsheet_preview,
                content,
                mime_type=document.mime_type.lower(),
                max_sheets=8,
                max_rows=3000,
                max_columns=256,
            )
        except SpreadsheetPreviewTooLargeError as exc:
            raise AppError("PARCEL_IMPORT_TOO_LARGE", "宗地清冊檔案過大，無法進行批次匯入", 413) from exc
        except Exception as exc:
            raise AppError("PARCEL_IMPORT_SOURCE_INVALID", "宗地清冊 Excel 無法讀取", 422) from exc

        existing_parcels = await self.valuation.list_parcels(case_id, user)
        return parse_parcel_import_preview(
            preview,
            case_district_code=case.district_code,
            existing_parcels=existing_parcels,
            document_id=document.document_id,
            filename=document.original_filename,
        )

    async def import_rows(
        self,
        case_id: UUID,
        document_id: UUID,
        payload: ParcelBatchImportRequest,
        user: User,
    ) -> ParcelBatchImportResponse:
        case = await self.valuation._owned_editable_case(case_id, user)
        document = await self._source_document(case_id, document_id, user)
        existing_parcels = await self.valuation.list_parcels(case_id, user)
        existing_keys = {
            key
            for parcel in existing_parcels
            if (
                key := _identity(
                    parcel.district_code,
                    parcel.section_name,
                    parcel.subsection_name,
                    parcel.land_no,
                )
            )
        }
        created = []
        skipped_locations: list[str] = []
        for row in payload.rows:
            if row.district_code != case.district_code:
                raise AppError(
                    "PARCEL_IMPORT_DISTRICT_MISMATCH",
                    "匯入宗地的行政區必須與案件行政區一致",
                    422,
                )
            key = _identity(
                row.district_code,
                row.section_name,
                row.subsection_name,
                row.land_no,
            )
            if key is None:
                raise AppError("PARCEL_IMPORT_ROW_INVALID", "匯入宗地缺少必要識別欄位", 422)
            if key in existing_keys:
                skipped_locations.append(row.source_location)
                continue
            record = await self.valuation.create_parcel(
                case_id,
                ParcelCreate(
                    district_code=row.district_code,
                    section_name=row.section_name,
                    subsection_name=row.subsection_name,
                    land_no=row.land_no,
                    area_sqm=row.area_sqm,
                    land_use_zone=row.land_use_zone,
                    designated_use=row.designated_use,
                    ownership_numerator=row.ownership_numerator,
                    ownership_denominator=row.ownership_denominator,
                    source_document_id=document.document_id,
                ),
                user,
            )
            existing_keys.add(key)
            created.append(ParcelResponse.model_validate(record))

        return ParcelBatchImportResponse(
            created=created,
            skipped_duplicate_count=len(skipped_locations),
            skipped_duplicate_locations=skipped_locations,
        )
