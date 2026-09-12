import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import httpx
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, ResourceNotFoundError
from app.storage.service import StorageService
from app.valuation.documents.repository import DocumentRepository
from app.valuation.extraction.field_catalog import (
    F01_FIELD_ANALYSIS_FIELDS,
    F02_FIELD_ANALYSIS_FIELDS,
    F02_RF_FIELD_ANALYSIS_FIELDS,
    F02_RF_SOURCE_ITEM_FIELD_MAP,
    F03_FIELD_ANALYSIS_FIELDS,
    F04_FIELD_ANALYSIS_FIELDS,
    S01_FIELD_ANALYSIS_FIELDS,
)
from app.valuation.extraction.repository import ExtractionRepository
from app.valuation.extraction.schemas import (
    CodexAnalysisPackageResponse,
    CodexCandidateImportRequest,
    FieldAnalysisRequest,
)
from app.valuation.models import DocumentExtractionRecord, ExtractedFieldRecord
from app.valuation.service import ValuationService


logger = logging.getLogger(__name__)


FIELD_ANALYSIS_FIELDS: dict[str, dict[str, str]] = {
    "F01": {
        "transaction_no": "買賣實例編號/交易案例編號/實例號 (包含：實例1、編號1、案例1等)",
        "transaction_date": "交易日期/成交日期/買賣日期 (包含：114年5月28日、114.05.28、114/5/28等原始日期)",
        "transaction_total_price": "買賣實例總價格/土地正常單價/成交總價/成交單價 (包含：數字與單位文字)",
    },
    "F02": {
        "benchmark_land_no": "比準地地號/比較標的地號/標的地號 (包含：段名與地號組合)",
        "price_zone_no": "地價區段號/地價區段編號/區段號/區段代碼",
        "valuation_base_date": "估價基準日/估價日期/查估日期/基準日期",
    },
    "F02-RF": {
        "urban_plan_status": "都市計畫（內、外）狀態或等級 (如：都市計畫內、都內、都市計畫外、都外、L1, L2)",
        "land_use_zone": "使用分區/土地使用分區/都市計畫分區 (如：商業區、第二種商業區、商二、住宅區、工業區、L1-L5)",
        "building_coverage_rate": "建蔽率/法定建蔽率 (如：70%、60%以上、建蔽率70%、L1-L5)",
        "floor_area_ratio": "容積率/法定容積率 (如：240%、240%以上、容積率240%、L1-L5)",
        "prohibited_building": "有無禁止建築/禁建狀況 (如：無、無禁止建築、有、L1, L2)",
        "restricted_building": "有無限制建築/限建狀況 (如：無、無限制建築、有、L1, L2)",
        "main_road_width": "主要道路名稱及寬度/面前道路寬度 (如：中山路18公尺、18M、主要道路18公尺、L1-L5)",
        "average_road_width": "區段內道路平均寬度/路寬 (如：12公尺、12M、平均路寬12公尺、L1-L5)",
        "mass_transit_proximity": "接近大型車站/捷運站/客運站之程度 (如：國光客運金山站 距離300公尺、300M、L1-L5)",
        "station_proximity": "公車站牌/公車亭之接近程度或密集程度 (如：金山區公所站、站牌密集、本區段內、L1-L5)",
        "interchange_proximity": "交流道之有無及接近程度 (如：無、無交流道、有交流道、L1-L5)",
        "road_plan": "區段內道路規劃及開闢程度 (如：已完全開發、開闢完成、規劃良好、L1-L5)",
        "drainage": "排水之良否/排水狀況 (如：有排水系統、不易淹水、排水良好、一般、L1-L5)",
        "terrain": "地勢狀況/地形/高程 (如：平坦、平地、地形平整、緩坡、低窪、L1-L5)",
        "market_proximity": "接近傳統市場/公有市場之程度 (如：金山市場 92公尺、鄰近市場、L1-L5)",
        "park_proximity": "接近公園/廣場之程度 (如：中山溫泉公園 200公尺、鄰近公園、L1-L5)",
        "tourist_facility_proximity": "接近觀光遊憩設施/老街/景點之程度 (如：金包里老街 本區段內、老街商圈、L1-L5)",
        "parking_convenience": "停車場地/停車便利程度 (如：金包里老街停車場 距離120公尺、可路邊停車、不可路邊停車、L1-L5)",
        "power_gas_facility": "電業設施/變電所/高壓鐵塔/氣體燃料設施 (如：金山變電所 距離700公尺、無、L1-L5)",
        "funeral_facility": "殮葬設施/墓地/殯儀館/火葬場/納骨塔之有無及距離 (如：金山第一公墓 距離80公尺、無、L1-L5)",
        "waste_facility": "廢棄物處理設施/垃圾場之有無及距離 (如：無、未發現顯著設施、有、L1-L5)",
        "environmental_pollution": "水、噪音、廢氣及廢棄物污染狀況 (如：未發現顯著污染、無污染、L1-L5)",
        "department_store": "百貨公司/商場之有無及接近程度 (如：無、鄰近無百貨公司、L1-L5)",
        "financial_institution": "金融機構/銀行/郵局之有無及數量 (如：鄰近範圍內有金融服務設施、有、L1-L5)",
        "entertainment_facility": "娛樂設施之有無及數量 (如：數量較少、無、L1-L5)",
        "exhibition_hotel": "大型展示中心或觀光飯店之接近程度 (如：非區段主要價格因素、無、L1-L5)",
        "pedestrian_flow": "顧客通行量/人流量 (如：老街及中山路沿線人流較多、人流多、L1-L5)",
        "vacancy_rate": "店舖之歇業/毗連狀態 (如：店舖連續程度高、歇業少、L1-L5)",
        "other": "其他影響因素等級 (L1-L5)",
    },
    "F03": {
        "benchmark_land_no": "比準地地號/比準地/比較標的地號 (包含：段名與地號，如「金山區金美段489地號」、「BM-100號」、「金美段489地號」)",
        "valuation_base_date": "估價基準日/估價日期/查估日期/基準日期 (包含：114年9月1日、114.09.01、2025-09-01等原始日期文字)",
    },
    "F04": {
        "valuation_base_date": "估價基準日/估價日期/查估日期/基準日期",
        "price_zone_no": "地價區段號/地價區段編號/區段代碼",
    },
}

# The S01 and commercial F02-RF field allowlists are imported from the
# user-supplied workbook specifications.  Keeping their source catalogues in
# the application means every AI/Codex run uses the same required field names,
# definitions, units, and validation context as the operational forms.
FIELD_ANALYSIS_FIELDS["F01"] = F01_FIELD_ANALYSIS_FIELDS
FIELD_ANALYSIS_FIELDS["F02"] = F02_FIELD_ANALYSIS_FIELDS
FIELD_ANALYSIS_FIELDS["F03"] = F03_FIELD_ANALYSIS_FIELDS
FIELD_ANALYSIS_FIELDS["F04"] = F04_FIELD_ANALYSIS_FIELDS
FIELD_ANALYSIS_FIELDS["S01"] = S01_FIELD_ANALYSIS_FIELDS
FIELD_ANALYSIS_FIELDS["F02-RF"] = F02_RF_FIELD_ANALYSIS_FIELDS
FIELD_ANALYSIS_FORM_CODES: tuple[str, ...] = (
    "F01",
    "F02",
    "F02-RF",
    "F03",
    "F04",
    "S01",
)
_WORKSHEET_HEADER = re.compile("(?m)^\\[\u5de5\u4f5c\u8868\uff1a(?P<title>[^\\]]+)\\]$")
_FORM_SECTION_HEADER = re.compile(
    r"(?m)^(?P<title>.*(?:買賣實例調查估價表|比較法調查估價表|影響地價區域因素分析明細表|比準地地價估計表|徵收土地宗地市價估計表|地價區段勘查表).*)$"
)
_FORM_SECTION_MARKERS: dict[str, tuple[str, ...]] = {
    "F01": ("買賣實例調查估價表",),
    "F02": ("比較法調查估價表",),
    "F02-RF": ("影響地價區域因素分析明細表",),
    "F03": ("比準地地價估計表",),
    "F04": ("徵收土地宗地市價估計表",),
    "S01": ("地價區段勘查表",),
}
_FORM_WORKSHEET_MARKERS: dict[str, tuple[str, ...]] = {
    "F02": ("F02", "比較法"),
    "F02-RF": ("F02-RF", "區域因素", "影響地價"),
    "F03": ("F03", "比準地"),
    "F04": ("F04", "徵收", "宗地市價"),
    "S01": ("S01", "地價區段", "區段勘查"),
}
_F01_SOURCE_WORKSHEET_MARKERS = ("F01", "買賣實例", "比較標的", "比較實例")
_F01_SOURCE_ROLE_MARKERS = (
    "買賣實例調查估價表",
    "比較標的",
    "比較實例",
)
_FIELD_RULES_PATH = Path(__file__).with_name("field_rules.md")
_NON_EXTRACTABLE_DESCRIPTION_MARKERS = (
    "後端計算",
    "後端判定",
    "後端格式化",
    "系統產生",
    "系統記錄",
    "系統結構",
    "系統關聯",
    "流程產生",
    "分頁結果",
    "輸出引擎",
)
_NON_EXTRACTABLE_FIELD_NAMES = {
    "approval_fields",
    "case_no",
}


@lru_cache(maxsize=1)
def _read_field_rules_markdown() -> str:
    try:
        return _FIELD_RULES_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"估價表單 AI 欄位規則文件不存在或無法讀取：{_FIELD_RULES_PATH}"
        ) from exc


def _field_rules_markdown_for_form(form_code: str) -> str:
    """Return the shared rules plus only the requested form's rule section."""
    markdown = _read_field_rules_markdown()
    section = re.search(
        rf"(?ms)^##\s+{re.escape(form_code)}\s*\n.*?(?=^##\s+|\Z)",
        markdown,
    )
    if section is None:
        raise RuntimeError(f"估價表單 AI 欄位規則文件缺少 {form_code} 章節")

    section_text = section.group(0).strip()
    _validate_field_rules_section(form_code, section_text)

    first_form = re.search(r"(?m)^##\s+F01\s*$", markdown)
    shared_rules = markdown[: first_form.start()] if first_form else markdown
    return f"{shared_rules.rstrip()}\n\n{section_text}"


def _validate_field_rules_section(form_code: str, section: str) -> None:
    """Fail closed when the human-maintained MD and runtime catalog diverge."""

    if form_code == "F02-RF":
        pairs = re.findall(
            r"(?m)^\|\s*\d+\s*\|\s*`?(?P<source>C\d+_\d+)`?\s*\|\s*`(?P<field>[A-Za-z0-9_]+)`\s*\|",
            section,
        )
        expected = list(F02_RF_SOURCE_ITEM_FIELD_MAP.items())
        if pairs != expected:
            raise RuntimeError(
                "field_rules.md 的 F02-RF 來源項目與 canonical field_name 不一致"
            )
        return

    names = set(
        re.findall(r"(?m)^\|\s*`(?P<field>[A-Za-z0-9_]+)`\s*\|", section)
    )
    expected = set(FIELD_ANALYSIS_FIELDS[form_code])
    if names != expected:
        missing = sorted(expected - names)
        extra = sorted(names - expected)
        raise RuntimeError(
            f"field_rules.md 的 {form_code} field_name 與欄位目錄不一致；"
            f"missing={missing}, extra={extra}"
        )


@lru_cache(maxsize=1)
def _cross_form_candidate_routes() -> dict[tuple[str, str], frozenset[str]]:
    """Load the explicit source-role matrix from ``field_rules.md``.

    A route does not authorize arbitrary form-to-form copying.  It names the
    only target fields which may use an upstream form's direct document
    evidence.  Keep this data in the MD so AI prompts and runtime validation
    have one human-reviewable source of truth.
    """

    markdown = _read_field_rules_markdown()
    section = re.search(
        r"(?ms)^##\s+跨表單候選欄位路由\s*\n.*?(?=^##\s+|\Z)",
        markdown,
    )
    if section is None:
        raise RuntimeError("field_rules.md 缺少跨表單候選欄位路由章節")

    routes: dict[tuple[str, str], frozenset[str]] = {}
    for line in section.group(0).splitlines():
        match = re.match(
            r"^\|\s*`(?P<source>F\d+(?:-RF)?|S\d+)`\s*\|\s*"
            r"`(?P<target>F\d+(?:-RF)?|S\d+)`\s*\|\s*(?P<fields>.*?)\s*\|",
            line,
        )
        if match is None:
            continue
        source = match.group("source")
        target = match.group("target")
        if source not in FIELD_ANALYSIS_FIELDS or target not in FIELD_ANALYSIS_FIELDS:
            raise RuntimeError(
                f"field_rules.md 的跨表單路由包含未知表單：{source} -> {target}"
            )
        fields = frozenset(re.findall(r"`([A-Za-z0-9_]+)`", match.group("fields")))
        if not fields:
            raise RuntimeError(
                f"field_rules.md 的跨表單路由未提供欄位：{source} -> {target}"
            )
        unknown_fields = fields - set(FIELD_ANALYSIS_FIELDS[target])
        if unknown_fields:
            raise RuntimeError(
                f"field_rules.md 的跨表單路由欄位不屬於 {target}：{sorted(unknown_fields)}"
            )
        key = (source, target)
        if key in routes:
            raise RuntimeError(
                f"field_rules.md 的跨表單路由重複定義：{source} -> {target}"
            )
        routes[key] = fields
    return routes


def _permitted_source_form_codes(target_form_code: str) -> tuple[str, ...]:
    routes = _cross_form_candidate_routes()
    upstream = tuple(
        source
        for source, target in routes
        if target == target_form_code and source != target_form_code
    )
    return (target_form_code, *upstream)


def _detected_source_form_codes(extracted_text: str) -> frozenset[str]:
    """Classify formal source sections without relying on a file name."""

    headers = list(_FORM_SECTION_HEADER.finditer(extracted_text))
    if headers:
        return frozenset(
            form_code
            for form_code, markers in _FORM_SECTION_MARKERS.items()
            if any(
                any(marker in header.group("title") for marker in markers)
                for header in headers
            )
        )

    worksheets = list(_WORKSHEET_HEADER.finditer(extracted_text))
    if worksheets:
        detected: set[str] = set()
        if any(
            any(marker in header.group("title") for marker in _F01_SOURCE_WORKSHEET_MARKERS)
            for header in worksheets
        ):
            detected.add("F01")
        for form_code, markers in _FORM_WORKSHEET_MARKERS.items():
            if any(
                any(marker in header.group("title") for marker in markers)
                for header in worksheets
            ):
                detected.add(form_code)
        return frozenset(detected)

    if any(marker in extracted_text for marker in _F01_SOURCE_ROLE_MARKERS):
        return frozenset({"F01"})
    return frozenset()


def _allowed_fields_for_detected_sources(
    form_code: str,
    fields: dict[str, str],
    detected_source_forms: frozenset[str],
) -> dict[str, str]:
    """Restrict a target when its own form is absent from a classified file."""

    if not detected_source_forms or form_code in detected_source_forms:
        return fields
    routes = _cross_form_candidate_routes()
    allowed_names = set().union(
        *(routes.get((source_form, form_code), frozenset())
          for source_form in detected_source_forms)
    )
    return {name: description for name, description in fields.items() if name in allowed_names}


def _analysis_source_text(extracted_text: str, form_code: str) -> str:
    """Return the source section belonging to the requested form.

    A single uploaded file may contain a complete packet of forms. When form
    headings are present, only the target form and the explicit upstream roles
    listed in ``field_rules.md`` are eligible. This prevents an F01 sale
    example from leaking into F03 or S01 while still allowing F02 to cite its
    permitted F01 comparison inputs. If a standalone source has no
    recognizable heading, retain the full text for backward compatibility and
    let the evidence checks decide.
    """
    if form_code != "F01":
        form_headers = list(_FORM_SECTION_HEADER.finditer(extracted_text))
        if not form_headers:
            worksheet_headers = list(_WORKSHEET_HEADER.finditer(extracted_text))
            if not worksheet_headers:
                return extracted_text
            sections: list[str] = []
            for source_form_code in _permitted_source_form_codes(form_code):
                worksheet_markers = (
                    _F01_SOURCE_WORKSHEET_MARKERS
                    if source_form_code == "F01"
                    else _FORM_WORKSHEET_MARKERS.get(source_form_code, ())
                )
                sections.extend(
                    extracted_text[header.start(): (
                        worksheet_headers[index + 1].start()
                        if index + 1 < len(worksheet_headers)
                        else len(extracted_text)
                    )].strip()
                    for index, header in enumerate(worksheet_headers)
                    if any(marker in header.group("title") for marker in worksheet_markers)
                )
            return "\n\n".join(section for section in sections if section)
        source_form_codes = _permitted_source_form_codes(form_code)
        sections: list[str] = []
        for index, header in enumerate(form_headers):
            if not any(
                any(marker in header.group("title") for marker in _FORM_SECTION_MARKERS.get(source_form_code, ()))
                for source_form_code in source_form_codes
            ):
                continue
            end = (
                form_headers[index + 1].start()
                if index + 1 < len(form_headers)
                else len(extracted_text)
            )
            sections.append(extracted_text[header.start():end].strip())
        return "\n\n".join(section for section in sections if section)
    headers = list(_WORKSHEET_HEADER.finditer(extracted_text))
    for index, header in enumerate(headers):
        if "\u6bd4\u8f03\u6a19\u7684" not in header.group("title"):
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(extracted_text)
        return extracted_text[header.start():end].strip()

    # PDF/DOCX/OCR text has no worksheet boundary. Use a recognised form
    # heading as a boundary, so subject-land or expropriation values cannot be
    # treated as sale-comparison instances.
    form_headers = list(_FORM_SECTION_HEADER.finditer(extracted_text))
    for index, header in enumerate(form_headers):
        if "買賣實例調查估價表" not in header.group("title"):
            continue
        end = (
            form_headers[index + 1].start()
            if index + 1 < len(form_headers)
            else len(extracted_text)
        )
        return extracted_text[header.start():end].strip()

    # A standalone comparison-instance extract may lack the form title. It is
    # still safe only when it explicitly identifies its role.
    if any(marker in extracted_text for marker in _F01_SOURCE_ROLE_MARKERS):
        return extracted_text
    return ""


def field_analysis_prompt(
    extracted_text: str,
    form_code: str,
    allowed_fields: dict[str, str],
) -> str:
    cross_form_routes = {
        source: sorted(fields)
        for (source, target), fields in _cross_form_candidate_routes().items()
        if target == form_code
    }
    return json.dumps(
        {
            "task": "從各種格式的估價原始文件、對照表、登記謄本、勘查紀錄或試算表 OCR 中，精準泛化對應並識別目標表單欄位",
            "form_code": form_code,
            "allowed_fields": allowed_fields,
            "field_rules_markdown": _field_rules_markdown_for_form(form_code),
            "field_rules_instruction": "以 field_rules_markdown 的通用規則及目前表單章節為唯一辨識依據；不可使用其他表單章節的欄位或資料角色。field_name 必須逐字從 allowed_fields 的 key 選取，不得回傳中文標籤、來源項目代碼、舊欄位名或自行翻譯名稱。",
            "cross_form_candidate_routes": cross_form_routes,
            "source_scope_instruction": "同一份上傳文件可以同時包含六種表單；本次處理 form_code 對應區段，以及 field_rules.md 跨表單資料角色明確允許的上游來源區段。若沒有允許的來源區段或沒有可由原文直接證明的欄位，候選必須回傳空陣列，這是正常結果，不得從不相關表單搬值。",
            "instructions": [
                "1. 語意泛化與同義詞識別：文件格式與標題可能與標準表單不同（例如欄位名稱為簡稱、同義字、非標準標頭、表格欄位或段落敘述），請依據 allowed_fields 的語意進行靈活對應與理解。",
                "2. 證據出處 (source_text)：必須是 ocr_text 中真實存在的連續或近乎連續之原始文字段落（保留該行或該句的原始標點與換行），絕不可自創不存在的段落。",
                "3. 擷取數值 (extracted_value)：",
                "   - 一般欄位（如日期、地號、區段號、單價、面積等）：擷取 source_text 中所包含的核心數值或原始文字（如 '114年9月1日'、'金美段489地號'、'P002-00'）。",
                "   - 區域因素欄位（F02-RF）：可回傳文件中的自然語言描述（如 '都市計畫內'、'第二種商業區'、'平坦'、'70%'、'無'）或標準等級代碼（'L1'~'L7'）。若 field_rules_markdown 的住宅計分規則適用範圍已由案件或原文確認，且原文可無歧義落入指定級距，得依規則計算後回傳 L 等級；此時 source_text 仍必須保留實際觀察原文。若用途、行政區、單位、距離或級距不明，必須回傳原文觀察值，不可猜測等級。",
                "   - extracted_value 必須是 source_text 中可直接找到的連續原文片段，不可自行改寫，也不可合併不同儲存格或不連續位置的文字。若完整資訊分散在多個儲存格，請選擇最能代表該欄位且連續存在的單一原文片段。",
                "4. 零虛構原則：若文件內容完全未提及該欄位（例如未包含任何廢棄物設施資訊），請勿回傳該欄位；絕不可自創資料、UUID 或非憑據數據。",
                "5. 僅回傳 allowed_fields 白名單內定義的 field_name，並再次對照 field_rules_markdown 的欄位代碼表。",
                "5b. 同一次文件辨識中，每個 field_name 最多回傳一筆候選；若同欄位有多處文字，選擇證據最完整、最直接的一處，不得重複輸出同一 field_name。",
                "5c. candidates 數量不得超過 allowed_fields 的欄位數，也不得超過輸出 schema 的 maxItems；若沒有可由 OCR 原文直接證明的欄位，回傳空陣列。",
                "5a. F01 僅可使用明確屬於「買賣實例調查估價表」、「比較標的」或「比較實例」的來源段落；不可使用徵收宗地、比準地、區域因素或其他表單資料。",
                "6. 僅回傳合法 JSON，不要使用 Markdown 程式碼區塊或加入說明文字。",
                "7. 最外層格式必須為 {\"candidates\": [...]}。",
                "8. 每個候選欄位必須包含：",
                "- field_name",
                "- extracted_value",
                "- confidence（0 到 1）",
                "- source_text",
            ],
            "ocr_text": extracted_text,
        },
        ensure_ascii=False,
    )


def _ai_extractable_fields(fields: dict[str, str]) -> dict[str, str]:
    """Remove workflow/computed fields that must never be invented from OCR.

    The form catalog is intentionally broader than the AI extraction surface:
    it also documents backend-computed values, system relations, provenance
    versions, and workflow-only fields.  Supplying those to an LLM encourages
    it to fabricate values for fields that are not literal document evidence.
    """
    return {
        name: description
        for name, description in fields.items()
        if name not in _NON_EXTRACTABLE_FIELD_NAMES
        and not any(marker in description for marker in _NON_EXTRACTABLE_DESCRIPTION_MARKERS)
    }



def field_analysis_output_schema(
    allowed_fields: tuple[str, ...],
    max_candidates: int,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "maxItems": max_candidates,
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name": {
                            "type": "string",
                            "enum": list(allowed_fields),
                        },
                        "extracted_value": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 500,
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "source_text": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 2000,
                        },
                    },
                    "required": [
                        "field_name",
                        "extracted_value",
                        "confidence",
                        "source_text",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidates"],
        "additionalProperties": False,
    }


class _CandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    extracted_value: str = Field(min_length=1, max_length=500)
    confidence: Decimal = Field(ge=0, le=1)
    source_text: str = Field(min_length=1, max_length=2000)


class _ToolPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[_CandidatePayload]


@dataclass(frozen=True)
class AnalyzedFieldCandidate:
    field_name: str
    extracted_value: str
    confidence: Decimal
    source_text: str


@dataclass(frozen=True)
class FieldAnalysisResult:
    candidates: tuple[AnalyzedFieldCandidate, ...]
    provider: str
    model_id: str
    prompt_version: str


class FieldAnalysisProvider(Protocol):
    provider_name: str
    model_id: str
    prompt_version: str

    async def analyze(
        self,
        extracted_text: str,
        form_code: str,
        allowed_fields: dict[str, str],
        *,
        document_bytes: bytes | None = None,
        document_name: str | None = None,
        document_mime_type: str | None = None,
    ) -> FieldAnalysisResult: ...


class BedrockFieldAnalysisProvider:
    provider_name = "BEDROCK"

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        *,
        model_id: str | None = None,
    ) -> None:
        if not settings.bedrock_region or not settings.bedrock_model_id:
            raise AppError(
                "BEDROCK_FIELD_ANALYSIS_NOT_CONFIGURED",
                "Bedrock 欄位辨識需要設定 Region 與 Model ID",
                503,
            )
        self.settings = settings
        self.model_id = model_id or settings.bedrock_model_id
        self.prompt_version = settings.ai_field_analysis_prompt_version
        if client is not None:
            self.client = client
            return
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise AppError(
                "BEDROCK_DEPENDENCY_MISSING",
                "Bedrock 欄位辨識需要 boto3",
                503,
            ) from exc
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.bedrock_region,
            config=Config(
                read_timeout=settings.ai_timeout_seconds,
                connect_timeout=5,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    async def analyze(
        self,
        extracted_text: str,
        form_code: str,
        allowed_fields: dict[str, str],
        *,
        document_bytes: bytes | None = None,
        document_name: str | None = None,
        document_mime_type: str | None = None,
    ) -> FieldAnalysisResult:
        tool_name = "submit_field_candidates"
        tool = self._tool_spec(
            tool_name,
            tuple(allowed_fields),
            self.settings.ai_field_analysis_max_candidates,
        )
        prompt = field_analysis_prompt(extracted_text, form_code, allowed_fields)
        content: list[dict[str, Any]] = []
        if document_bytes:
            content.append(
                {
                    "document": {
                        "format": _bedrock_document_format(document_mime_type, document_name),
                        "name": _bedrock_document_name(document_name),
                        "source": {"bytes": document_bytes},
                    }
                }
            )
        content.append({"text": prompt})
        try:
            result = await run_in_threadpool(
                self.client.converse,
                modelId=self.model_id,
                messages=[{"role": "user", "content": content}],
                system=[
                    {
                        "text": (
                            "你是土地估價文件欄位辨識器。只可提交有原始文件或 OCR 原文證據的"
                            "候選值，不得補值、推算、改寫日期或執行正式資料寫入。"
                        )
                    }
                ],
                toolConfig={
                    "tools": [tool],
                    "toolChoice": {"tool": {"name": tool_name}},
                },
                inferenceConfig=self._inference_config(),
            )
        except Exception as exc:
            detail = str(exc)
            if "aws-marketplace:" in detail:
                raise AppError(
                    "BEDROCK_MODEL_ACCESS_REQUIRES_MARKETPLACE",
                    "AWS 尚未授權此 Anthropic 模型的 Marketplace 使用權；請先授予 ViewSubscriptions 與 Subscribe 後重試",
                    503,
                ) from exc
            logger.exception("Bedrock field analysis request failed")
            raise AppError(
                "BEDROCK_UNAVAILABLE",
                "Bedrock 欄位辨識暫時無法使用",
                503,
            ) from exc

        try:
            content = result["output"]["message"]["content"]
            inputs = [
                block["toolUse"]["input"]
                for block in content
                if block.get("toolUse", {}).get("name") == tool_name
            ]
            if len(inputs) != 1:
                raise ValueError("expected exactly one field-analysis tool call")
            payload = _ToolPayload.model_validate(inputs[0])
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise AppError(
                "BEDROCK_INVALID_RESPONSE",
                "Bedrock 欄位辨識回應不符合受控格式",
                502,
            ) from exc
        if len(payload.candidates) > self.settings.ai_field_analysis_max_candidates:
            raise AppError(
                "BEDROCK_CANDIDATE_LIMIT",
                "Bedrock 回傳的候選欄位數超過系統限制",
                502,
            )
        candidates = tuple(
            AnalyzedFieldCandidate(
                field_name=item.field_name,
                extracted_value=item.extracted_value,
                confidence=item.confidence.quantize(Decimal("0.0001")),
                source_text=item.source_text,
            )
            for item in payload.candidates
        )
        return FieldAnalysisResult(
            candidates=candidates,
            provider=self.provider_name,
            model_id=self.model_id,
            prompt_version=self.prompt_version,
        )

    def _inference_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "maxTokens": self.settings.bedrock_max_tokens,
        }
        # Claude Fable 5.1 requires temperature=1.0 or an omitted sampling
        # parameter.  Omitting it also lets the model use its adaptive thinking
        # defaults.  Older/test models retain the configured deterministic
        # temperature.
        if "claude-fable-5-1" not in self.model_id:
            config["temperature"] = self.settings.bedrock_temperature
        return config

    @staticmethod
    def _tool_spec(
        name: str,
        allowed_fields: tuple[str, ...],
        max_candidates: int,
    ) -> dict[str, Any]:
        return {
            "toolSpec": {
                "name": name,
                "description": "提交有 OCR 原文證據的表單候選欄位",
                "inputSchema": {
                    "json": field_analysis_output_schema(
                        allowed_fields,
                        max_candidates,
                    )
                },
            }
        }


class BedrockFieldAnalysisRouter:
    """Run Fable as the primary model and route uncertain fields to Opus."""

    provider_name = "BEDROCK"

    def __init__(
        self,
        settings: Settings,
        primary: BedrockFieldAnalysisProvider | None = None,
        fallback: BedrockFieldAnalysisProvider | None = None,
    ) -> None:
        self.settings = settings
        self.primary = primary or BedrockFieldAnalysisProvider(settings)
        fallback_model_id = settings.bedrock_fallback_model_id
        self.fallback = fallback or (
            BedrockFieldAnalysisProvider(
                settings,
                model_id=fallback_model_id,
            )
            if fallback_model_id
            else None
        )
        self.model_id = self.primary.model_id
        self.prompt_version = self.primary.prompt_version

    async def analyze(
        self,
        extracted_text: str,
        form_code: str,
        allowed_fields: dict[str, str],
        *,
        document_bytes: bytes | None = None,
        document_name: str | None = None,
        document_mime_type: str | None = None,
    ) -> FieldAnalysisResult:
        routed = await self.analyze_with_routing(
            extracted_text,
            form_code,
            allowed_fields,
            document_bytes=document_bytes,
            document_name=document_name,
            document_mime_type=document_mime_type,
        )
        candidates = tuple(
            candidate
            for result, _fields in routed
            for candidate in result.candidates
        )
        return FieldAnalysisResult(
            candidates=candidates,
            provider=self.provider_name,
            model_id=self.model_id,
            prompt_version=self.prompt_version,
        )

    async def analyze_with_routing(
        self,
        extracted_text: str,
        form_code: str,
        allowed_fields: dict[str, str],
        *,
        document_bytes: bytes | None = None,
        document_name: str | None = None,
        document_mime_type: str | None = None,
    ) -> tuple[tuple[FieldAnalysisResult, dict[str, str]], ...]:
        document_kwargs = (
            {
                "document_bytes": document_bytes,
                "document_name": document_name,
                "document_mime_type": document_mime_type,
            }
            if document_bytes is not None
            else {}
        )
        primary_result = await self.primary.analyze(
            extracted_text,
            form_code,
            allowed_fields,
            **document_kwargs,
        )
        fallback_fields = self._fallback_fields(
            form_code,
            allowed_fields,
            primary_result,
        )
        if self.fallback is None or not fallback_fields:
            return ((primary_result, allowed_fields),)

        primary_fields = {
            name: description
            for name, description in allowed_fields.items()
            if name not in fallback_fields
        }
        routed: list[tuple[FieldAnalysisResult, dict[str, str]]] = []
        if primary_fields:
            routed.append((primary_result, primary_fields))
        fallback_result = await self.fallback.analyze(
            extracted_text,
            form_code,
            fallback_fields,
            **document_kwargs,
        )
        routed.append((fallback_result, fallback_fields))
        return tuple(routed)

    def _fallback_fields(
        self,
        form_code: str,
        allowed_fields: dict[str, str],
        result: FieldAnalysisResult,
    ) -> dict[str, str]:
        by_field = {candidate.field_name: candidate for candidate in result.candidates}
        threshold = Decimal(str(self.settings.bedrock_fallback_confidence_threshold))
        selected: dict[str, str] = {}
        for field_name, description in allowed_fields.items():
            candidate = by_field.get(field_name)
            if candidate is None:
                selected[field_name] = description
                continue
            if candidate.confidence < threshold or _candidate_rule_conflict(
                form_code,
                field_name,
                description,
                candidate.extracted_value,
            ):
                selected[field_name] = description
        return selected


def _candidate_rule_conflict(
    form_code: str,
    field_name: str,
    description: str,
    value: str,
) -> bool:
    """Find obvious conflicts before formal Python validation.

    This is only a routing signal.  The authoritative field schema and
    published rule-pack calculation still run after user confirmation.
    """
    normalized = value.strip().upper()
    if re.search(r"\bL(?:0|[89]|\d{2,})\b", normalized):
        return True
    if form_code == "F02-RF" and field_name == "other" and not normalized:
        return True

    numeric_hints = (
        "\u65e5\u671f",
        "\u9762\u7a4d",
        "\u5bec\u5ea6",
        "\u8ddd\u96e2",
        "\u6578\u91cf",
        "\u6bd4\u4f8b",
        "\u7387",
        "\u50f9\u683c",
        "\u91d1\u984d",
    )
    expects_number = any(hint in description for hint in numeric_hints)
    if expects_number and not re.search(r"\d", value) and not re.fullmatch(r"L[1-7]", normalized):
        return True
    return False


class OllamaFieldAnalysisProvider:
    provider_name = "OLLAMA"

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.model_id = settings.ollama_model
        self.prompt_version = settings.ai_field_analysis_prompt_version
        self.client = client

    async def analyze(
        self,
        extracted_text: str,
        form_code: str,
        allowed_fields: dict[str, str],
        *,
        document_bytes: bytes | None = None,
        document_name: str | None = None,
        document_mime_type: str | None = None,
    ) -> FieldAnalysisResult:
        del document_bytes, document_name, document_mime_type
        schema = field_analysis_output_schema(
            tuple(allowed_fields),
            self.settings.ai_field_analysis_max_candidates,
        )
        request_body = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是土地估價文件欄位辨識器。只可根據使用者提供的 OCR 原文"
                        "輸出候選欄位，不得補值、推算、改寫原始證據或執行正式資料寫入。"
                        "回覆必須完全符合指定 JSON schema。"
                    ),
                },
                {
                    "role": "user",
                    "content": field_analysis_prompt(
                        extracted_text,
                        form_code,
                        allowed_fields,
                    ),
                },
            ],
            "format": schema,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
        }
        try:
            if self.client is not None:
                response = await self.client.post(
                    f"{self.settings.ollama_base_url}/api/chat",
                    json=request_body,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self.settings.ollama_timeout_seconds
                ) as client:
                    response = await client.post(
                        f"{self.settings.ollama_base_url}/api/chat",
                        json=request_body,
                    )
        except httpx.RequestError as exc:
            raise AppError(
                "OLLAMA_FIELD_ANALYSIS_UNAVAILABLE",
                "無法連線到本機 Ollama，請確認 Ollama 已啟動且模型可用",
                503,
            ) from exc

        if response.status_code == 404:
            raise AppError(
                "OLLAMA_FIELD_ANALYSIS_MODEL_NOT_FOUND",
                f"Ollama 找不到模型 {self.model_id}，請先下載模型",
                503,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "OLLAMA_FIELD_ANALYSIS_UNAVAILABLE",
                "Ollama 欄位辨識暫時無法使用",
                503,
            ) from exc

        try:
            body = response.json()
            content = body["message"]["content"]
            if isinstance(content, str):
                payload_raw = json.loads(content)
            elif isinstance(content, dict):
                payload_raw = content
            else:
                raise TypeError("message.content must be JSON text or object")
            payload = _ToolPayload.model_validate(payload_raw)
        except (ValueError, KeyError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise AppError(
                "OLLAMA_FIELD_ANALYSIS_INVALID_RESPONSE",
                "Ollama 欄位辨識回應不符合受控格式",
                502,
            ) from exc

        unique_candidates: list[_CandidatePayload] = []
        seen_fields: set[str] = set()
        candidate_limit = min(
            self.settings.ai_field_analysis_max_candidates,
            len(allowed_fields),
        )
        for item in payload.candidates:
            if item.field_name in seen_fields:
                continue
            seen_fields.add(item.field_name)
            unique_candidates.append(item)
            if len(unique_candidates) >= candidate_limit:
                break

        return FieldAnalysisResult(
            candidates=tuple(
                AnalyzedFieldCandidate(
                    field_name=item.field_name,
                    extracted_value=item.extracted_value,
                    confidence=item.confidence.quantize(Decimal("0.0001")),
                    source_text=item.source_text,
                )
                for item in unique_candidates
            ),
            provider=self.provider_name,
            model_id=self.model_id,
            prompt_version=self.prompt_version,
        )


def build_field_analysis_provider(settings: Settings) -> FieldAnalysisProvider:
    if settings.ai_provider == "bedrock":
        primary = BedrockFieldAnalysisProvider(settings)
        if (
            settings.bedrock_fallback_model_id
            and settings.bedrock_fallback_model_id != primary.model_id
        ):
            return BedrockFieldAnalysisRouter(settings, primary=primary)
        return primary
    if settings.ai_provider == "ollama":
        return OllamaFieldAnalysisProvider(settings)
    raise AppError(
        "FIELD_ANALYSIS_PROVIDER_NOT_CONFIGURED",
        "文件 AI 欄位辨識目前僅支援 Ollama 或 Bedrock",
        503,
    )


def _source_page_for_candidate(
    extraction: DocumentExtractionRecord,
    source_text: str,
) -> int | None:
    metadata = getattr(extraction, "extraction_metadata", None) or {}
    normalized = _evidence_key(source_text)
    for item in metadata.get("pages", []):
        page_text = str(item.get("text", ""))
        if source_text in page_text or (
            normalized and normalized in _evidence_key(page_text)
        ):
            try:
                return max(int(item.get("page", 1)), 1)
            except (TypeError, ValueError):
                continue
    return 1 if extraction.page_count == 1 else None


def _evidence_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"[\s,，:：|\\\/\-_\(\)（）]", "", normalized)


def _candidate_semantically_valid(form_code: str, field_name: str, value: str) -> bool:
    """Apply narrow format checks for fields with unambiguous surface syntax."""
    normalized = unicodedata.normalize("NFKC", value).strip()
    if form_code == "F03" and field_name == "price_zone_no":
        return bool(re.fullmatch(r"[A-Za-z]\d{3}-\d{2}", normalized))
    if form_code == "F03" and field_name == "district_name":
        return bool(re.fullmatch(r".{1,20}(?:區|鄉|鎮|市)", normalized))
    if form_code == "F03" and field_name == "section_subsection_name":
        return "段" in normalized
    return True

def _bedrock_document_format(mime_type: str | None, name: str | None) -> str:
    """Map uploaded document types to Converse document content formats."""
    formats = {
        "application/pdf": "pdf",
        "text/plain": "txt",
        "text/csv": "csv",
        "text/markdown": "md",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/msword": "doc",
        "application/vnd.ms-excel": "xls",
        "text/html": "html",
    }
    if mime_type and mime_type.lower() in formats:
        return formats[mime_type.lower()]
    suffix = Path(name or "source.pdf").suffix.lower().lstrip(".")
    return suffix if suffix in {"pdf", "txt", "csv", "md", "doc", "docx", "xls", "xlsx", "html"} else "pdf"


def _bedrock_document_name(name: str | None) -> str:
    """Return a safe document name accepted by Bedrock Converse."""
    stem = Path(name or "source-document").stem
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-_")
    return (safe or "source-document")[:80]


def _map_f02_rf_level(field_name: str, value: str, source_text: str) -> str | None:
    # Natural-language values are deliberately preserved here.  Their formal
    # level depends on the rule version selected for the report and is resolved
    # later against imported factor_levels.  Only an explicit AI-supplied level
    # may pass through at extraction time.
    del field_name, source_text
    norm_val = value.strip().upper()
    if re.fullmatch(r"L[1-7]", norm_val):
        return norm_val
    return None



class FieldAnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ExtractionRepository | None = None,
        provider: FieldAnalysisProvider | None = None,
        settings: Settings | None = None,
        storage: StorageService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or ExtractionRepository(session)
        self.provider = provider
        self.settings = settings or get_settings()
        self.storage = storage
        self.documents = DocumentRepository(session)
        self.valuation = ValuationService(session)

    async def analyze(
        self,
        case_id: UUID,
        document_id: UUID,
        payload: FieldAnalysisRequest,
        user: User,
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        form_code = payload.form_code.value
        (
            extraction,
            extracted_text,
            remaining_fields,
            document_bytes,
            document_name,
            document_mime_type,
        ) = await self._analysis_context(
            case_id,
            document_id,
            form_code,
            user,
        )
        document = await self.documents.get(case_id, document_id)
        document_kwargs = (
            {
                "document_bytes": document_bytes,
                "document_name": document_name,
                "document_mime_type": document_mime_type,
            }
            if document_bytes is not None
            else {}
        )
        if not remaining_fields:
            return extraction, await self.repository.list_candidates(
                extraction.extraction_id
            )

        provider = self.provider or build_field_analysis_provider(self.settings)
        records: list[ExtractedFieldRecord] = []
        for allowed_fields in self._field_batches(remaining_fields):
            if isinstance(provider, BedrockFieldAnalysisRouter):
                routed_results = await provider.analyze_with_routing(
                    extracted_text,
                    form_code,
                    allowed_fields,
                    **document_kwargs,
                )
            else:
                routed_results = (
                    (
                        await provider.analyze(
                            extracted_text,
                            form_code,
                            allowed_fields,
                            **document_kwargs,
                        ),
                        allowed_fields,
                    ),
                )
            for result, result_fields in routed_results:
                records.extend(
                    self._candidate_records(
                        extraction,
                        form_code,
                        result,
                        result_fields,
                        location_id=document.location_id,
                        evidence_text=extracted_text,
                        allow_visual_evidence=document_bytes is not None,
                        drop_invalid_evidence=result.provider == "OLLAMA",
                    )
                )
        if records:
            await self.repository.add_candidates(records)
        return extraction, await self.repository.list_candidates(
            extraction.extraction_id
        )

    def _field_batches(self, fields: dict[str, str]) -> tuple[dict[str, str], ...]:
        items = list(fields.items())
        size = self.settings.ai_field_analysis_max_candidates
        return tuple(dict(items[index:index + size]) for index in range(0, len(items), size))

    async def prepare_codex_package(
        self,
        case_id: UUID,
        document_id: UUID,
        payload: FieldAnalysisRequest,
        user: User,
    ) -> CodexAnalysisPackageResponse:
        form_code = payload.form_code.value
        _, extracted_text, remaining_fields, _, _, _ = await self._analysis_context(
            case_id,
            document_id,
            form_code,
            user,
        )
        return CodexAnalysisPackageResponse(
            form_code=payload.form_code,
            prompt_version=self.settings.ai_codex_import_prompt_version,
            prompt=field_analysis_prompt(
                extracted_text,
                form_code,
                remaining_fields,
            ),
            output_schema=field_analysis_output_schema(
                tuple(remaining_fields),
                self.settings.ai_field_analysis_max_candidates,
            ),
        )

    async def import_codex_candidates(
        self,
        case_id: UUID,
        document_id: UUID,
        payload: CodexCandidateImportRequest,
        user: User,
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        form_code = payload.form_code.value
        (
            extraction,
            analysis_text,
            remaining_fields,
            document_bytes,
            _,
            _,
        ) = await self._analysis_context(
            case_id,
            document_id,
            form_code,
            user,
        )
        if len(payload.candidates) > self.settings.ai_field_analysis_max_candidates:
            raise AppError(
                "CODEX_CANDIDATE_LIMIT",
                "Codex 回傳的候選欄位數超過系統限制",
                422,
            )
        result = FieldAnalysisResult(
            candidates=tuple(
                AnalyzedFieldCandidate(
                    field_name=item.field_name,
                    extracted_value=item.extracted_value,
                    confidence=item.confidence.quantize(Decimal("0.0001")),
                    source_text=item.source_text,
                )
                for item in payload.candidates
            ),
            provider="CODEX",
            model_id=payload.model_id,
            prompt_version=self.settings.ai_codex_import_prompt_version,
        )
        records = self._candidate_records(
            extraction,
            form_code,
            result,
            remaining_fields,
            location_id=(await self.documents.get(case_id, document_id)).location_id,
            error_prefix="CODEX",
            source_label="Codex",
            error_status=422,
            evidence_text=analysis_text,
            allow_visual_evidence=document_bytes is not None,
        )
        if records:
            await self.repository.add_candidates(records)
        return extraction, await self.repository.list_candidates(
            extraction.extraction_id
        )

    async def _analysis_context(
        self,
        case_id: UUID,
        document_id: UUID,
        form_code: str,
        user: User,
    ) -> tuple[
        DocumentExtractionRecord,
        str,
        dict[str, str],
        bytes | None,
        str | None,
        str | None,
    ]:
        await self.valuation._owned_editable_case(case_id, user)
        extraction = await self.repository.latest_for_document(case_id, document_id)
        if extraction is None or extraction.extraction_status != "COMPLETED":
            raise ResourceNotFoundError("已完成的文件文字擷取結果")
        extracted_text = (extraction.extracted_text or "").strip()
        if not extracted_text:
            raise AppError(
                "EXTRACTED_TEXT_REQUIRED",
                "文件沒有可供 AI 分析的擷取文字",
                422,
            )

        document_bytes: bytes | None = None
        document_name: str | None = None
        document_mime_type: str | None = None
        document = await self.documents.get(case_id, document_id)
        if self.storage is not None and document is not None and document.is_active:
            response = await self.storage.download(document.object_key)
            try:
                document_bytes = await run_in_threadpool(response.read)
            finally:
                response.close()
                response.release_conn()
            document_name = document.original_filename
            document_mime_type = document.mime_type

        visual_source_available = bool(document_bytes)
        analysis_text = _analysis_source_text(extracted_text, form_code)
        # Scanned forms often have unusable OCR headings.  When the original
        # document is attached, Bedrock can inspect the page itself, so use the
        # complete OCR as auxiliary context instead of rejecting the request.
        if not analysis_text and visual_source_available:
            analysis_text = extracted_text
        if form_code == "F01" and not analysis_text:
            raise AppError(
                "F01_SOURCE_SCOPE_NOT_FOUND",
                "找不到可確認為買賣實例或比較標的的來源段落；請上傳具明確表頭或標示的資料",
                422,
            )
        if len(analysis_text) > self.settings.ai_field_analysis_max_chars:
            raise AppError(
                "FIELD_ANALYSIS_TEXT_LIMIT",
                "擷取文字超過 AI 欄位辨識單次處理上限",
                422,
            )
        detected_source_forms = (
            frozenset()
            if visual_source_available
            else _detected_source_form_codes(extracted_text)
        )
        allowed_fields = _allowed_fields_for_detected_sources(
            form_code,
            _ai_extractable_fields(FIELD_ANALYSIS_FIELDS[form_code]),
            detected_source_forms,
        )
        if not analysis_text:
            return extraction, "", {}, document_bytes, document_name, document_mime_type
        existing_names = await self.repository.candidate_field_names(
            extraction.extraction_id, form_code
        )
        remaining_fields = {
            name: description
            for name, description in allowed_fields.items()
            if name not in existing_names
        }
        return (
            extraction,
            analysis_text,
            remaining_fields,
            document_bytes,
            document_name,
            document_mime_type,
        )
    @staticmethod
    def _candidate_records(
        extraction: DocumentExtractionRecord,
        form_code: str,
        result: FieldAnalysisResult,
        allowed_fields: dict[str, str],
        *,
        location_id: UUID | None = None,
        error_prefix: str = "BEDROCK",
        source_label: str = "Bedrock",
        error_status: int = 502,
        evidence_text: str | None = None,
        allow_visual_evidence: bool = False,
        drop_invalid_evidence: bool = False,
    ) -> list[ExtractedFieldRecord]:
        records: list[ExtractedFieldRecord] = []
        seen: set[str] = set()
        evidence_text = evidence_text if evidence_text is not None else extraction.extracted_text or ""
        norm_full_ocr = _evidence_key(evidence_text)

        for candidate in result.candidates:
            if candidate.field_name not in allowed_fields:
                if error_prefix != "BEDROCK":
                    raise AppError(
                        f"{error_prefix}_FIELD_NOT_ALLOWED",
                        f"{source_label} 回傳了表單白名單以外的欄位",
                        error_status,
                    )
                continue

            if candidate.field_name in seen:
                if error_prefix != "BEDROCK":
                    raise AppError(
                        f"{error_prefix}_DUPLICATE_FIELD",
                        f"{source_label} 重複回傳同一欄位",
                        error_status,
                    )
                continue

            source_text = candidate.source_text.strip()
            norm_source = _evidence_key(source_text)

            # Verification Phase 1: source_text must exist in full OCR text
            source_grounded = (source_text in evidence_text) or (
                bool(norm_source) and norm_source in norm_full_ocr
            ) or (allow_visual_evidence and bool(norm_source))

            # Verification Phase 2: extracted_value must be grounded in source_text
            extracted_val = candidate.extracted_value.strip()
            norm_val = _evidence_key(extracted_val)
            val_grounded = bool(norm_val) and norm_val in norm_source

            final_val = extracted_val

            if form_code == "F02-RF":
                mapped_level = _map_f02_rf_level(
                    candidate.field_name, extracted_val, source_text
                )
                if mapped_level is not None:
                    final_val = mapped_level
                    val_grounded = True

            semantic_valid = _candidate_semantically_valid(
                form_code,
                candidate.field_name,
                final_val,
            )
            if not source_grounded or not val_grounded or not semantic_valid:
                if drop_invalid_evidence:
                    continue
                raise AppError(
                    f"{error_prefix}_FIELD_EVIDENCE_INVALID",
                    f"{source_label} 候選值缺少可核對的 OCR 原文證據或欄位格式不符",
                    error_status,
                )


            seen.add(candidate.field_name)
            records.append(
                ExtractedFieldRecord(
                    case_id=extraction.case_id,
                    extraction_id=extraction.extraction_id,
                    location_id=location_id,
                    document_id=extraction.document_id,
                    form_code=form_code,
                    field_name=candidate.field_name,
                    extracted_value=final_val,
                    confidence=candidate.confidence,
                    source_page=_source_page_for_candidate(extraction, source_text),
                    source_text=source_text,
                    analysis_provider=result.provider,
                    model_id=result.model_id,
                    prompt_version=result.prompt_version,
                    field_status="NEEDS_CONFIRMATION",
                )
            )
        return records
