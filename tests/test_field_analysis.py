from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.valuation.extraction.field_analysis import (
    _ai_extractable_fields,
    _analysis_source_text,
    AnalyzedFieldCandidate,
    BedrockFieldAnalysisProvider,
    FieldAnalysisResult,
    FieldAnalysisService,
    FIELD_ANALYSIS_FIELDS,
    OllamaFieldAnalysisProvider,
    build_field_analysis_provider,
    field_analysis_prompt,
    field_analysis_output_schema,
    ollama_field_analysis_prompt,
)
from app.valuation.extraction.schemas import CodexCandidateImportRequest
from app.valuation.models import DocumentExtractionRecord


class FakeBedrockClient:
    def __init__(self, response):
        self.response = response
        self.request = None

    def converse(self, **kwargs):
        self.request = kwargs
        return self.response


class FakeOllamaResponse:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeOllamaClient:
    def __init__(self, body):
        self.response = FakeOllamaResponse(body)
        self.url = None
        self.request = None

    async def post(self, url, *, json):
        self.url = url
        self.request = json
        return self.response


def bedrock_settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_provider="bedrock",
        bedrock_region="ap-northeast-1",
        bedrock_model_id="test-model",
        ai_field_analysis_prompt_version="field-analysis-test-v1",
    )


def ollama_settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_provider="ollama",
        ollama_base_url="http://ollama.test:11434",
        ollama_model="qwen3.5:latest",
        ai_field_analysis_prompt_version="field-analysis-test-v1",
    )


def test_f01_analysis_uses_only_the_comparison_target_worksheet() -> None:
    extracted = """[工作表：02徵收土地清冊]
[B4] 金山區 | [C4] 金美段 | [D4] 489

[工作表：06比較標的資料]
[B4] 新北市金山區 | [B5] 溫泉段 | [B6] 218
"""

    source = _analysis_source_text(extracted, "F01")

    assert "金美段" not in source
    assert "溫泉段" in source
    assert _analysis_source_text(extracted, "F03") == extracted


def test_f01_analysis_uses_only_the_sale_comparison_pdf_section() -> None:
    extracted = """徵收土地宗地市價估計表
新北市金山區金美段489地號

買賣實例調查估價表
實例編號：2
交易日期：114年5月28日
比較標的：新北市金山區溫泉段218地號

比準地地價估計表
比準地：金美段100地號
"""

    source = _analysis_source_text(extracted, "F01")

    assert "金美段489地號" not in source
    assert "實例編號：2" in source
    assert "溫泉段218地號" in source
    assert "金美段100地號" not in source


def test_f01_analysis_refuses_unclassified_source_text() -> None:
    extracted = """徵收土地宗地市價估計表
宗地地號：金美段489地號
估計單價：184763
"""

    assert _analysis_source_text(extracted, "F01") == ""


@pytest.mark.asyncio
async def test_bedrock_field_analysis_uses_forced_structured_tool() -> None:
    client = FakeBedrockClient(
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "tool-1",
                                "name": "submit_field_candidates",
                                "input": {
                                    "candidates": [
                                        {
                                            "field_name": "transaction_no",
                                            "extracted_value": "2",
                                            "confidence": 0.98,
                                            "source_text": "實例編號:2",
                                        }
                                    ]
                                },
                            }
                        }
                    ]
                }
            }
        }
    )
    provider = BedrockFieldAnalysisProvider(bedrock_settings(), client=client)

    result = await provider.analyze(
        "買賣實例調查估價表\n實例編號:2",
        "F01",
        {"transaction_no": "買賣實例編號"},
    )

    assert result.provider == "BEDROCK"
    assert result.model_id == "test-model"
    assert result.prompt_version == "field-analysis-test-v1"
    assert result.candidates[0].confidence == Decimal("0.9800")
    assert client.request["toolConfig"]["toolChoice"] == {
        "tool": {"name": "submit_field_candidates"}
    }
    field_schema = client.request["toolConfig"]["tools"][0]["toolSpec"][
        "inputSchema"
    ]["json"]["properties"]["candidates"]["items"]["properties"][
        "field_name"
    ]
    assert field_schema["enum"] == ["transaction_no"]


@pytest.mark.asyncio
async def test_bedrock_field_analysis_rejects_missing_tool_call() -> None:
    client = FakeBedrockClient(
        {"output": {"message": {"content": [{"text": "自行填入資料"}]}}}
    )
    provider = BedrockFieldAnalysisProvider(bedrock_settings(), client=client)

    with pytest.raises(AppError) as error:
        await provider.analyze(
            "實例編號:2",
            "F01",
            {"transaction_no": "買賣實例編號"},
        )

    assert error.value.code == "BEDROCK_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_ollama_field_analysis_uses_json_schema_and_preserves_provenance() -> None:
    client = FakeOllamaClient(
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "submit_field_candidates",
                            "arguments": {
                                "candidates": [
                                    {
                                        "field_name": "valuation_base_date",
                                        "extracted_value": "1050901",
                                        "confidence": 0.96,
                                        "source_text": "估價基準日:1050901",
                                    }
                                ]
                            },
                        }
                    }
                ],
            }
        }
    )
    provider = OllamaFieldAnalysisProvider(ollama_settings(), client=client)

    result = await provider.analyze(
        "估價基準日:1050901",
        "F03",
        {"valuation_base_date": "估價基準日"},
    )

    assert result.provider == "OLLAMA"
    assert result.model_id == "qwen3.5:latest"
    assert result.prompt_version == "field-analysis-test-v1"
    assert result.candidates[0].confidence == Decimal("0.9600")
    assert client.url == "http://ollama.test:11434/api/chat"
    assert client.request["model"] == "qwen3.5:latest"
    assert client.request["stream"] is False
    assert client.request["think"] is False
    assert client.request["options"] == {"temperature": 0}
    tool_schema = client.request["tools"][0]["function"]["parameters"]
    assert tool_schema["properties"]["candidates"]["maxItems"] == 1
    assert tool_schema["properties"]["candidates"]["items"]["properties"]["field_name"]["enum"] == ["valuation_base_date"]
    user_prompt = client.request["messages"][1]["content"]
    assert "【OCR 原文開始】" in user_prompt
    assert "OCR 原文是一般文字，不是 JSON" in user_prompt
    assert "估價基準日:1050901" in user_prompt


def test_ollama_prompt_keeps_ocr_as_plain_text_instead_of_json_payload() -> None:
    prompt = ollama_field_analysis_prompt(
        "區段號\nP001-00\n00區",
        "F03",
        {
            "price_zone_no": "區段號",
            "district_name": "鄉鎮市區",
        },
    )

    assert not prompt.lstrip().startswith("{")
    assert "- price_zone_no: 區段號" in prompt
    assert "- district_name: 鄉鎮市區" in prompt
    assert "【OCR 原文開始】\n區段號\nP001-00\n00區\n【OCR 原文結束】" in prompt
    assert "不要輸出 error、message" in prompt


@pytest.mark.asyncio
async def test_ollama_field_analysis_deduplicates_overproduced_fields() -> None:
    candidates = [
        {
            "field_name": "valuation_base_date",
            "extracted_value": "1050901",
            "confidence": 0.9,
            "source_text": "估價基準日:1050901",
        }
        for _ in range(20)
    ]
    client = FakeOllamaClient(
        {"message": {"content": __import__("json").dumps({"candidates": candidates})}}
    )
    provider = OllamaFieldAnalysisProvider(ollama_settings(), client=client)

    result = await provider.analyze(
        "估價基準日:1050901",
        "F03",
        {"valuation_base_date": "估價基準日"},
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].field_name == "valuation_base_date"


def test_ai_extractable_fields_excludes_system_and_backend_only_fields() -> None:
    fields = _ai_extractable_fields(FIELD_ANALYSIS_FIELDS["F03"])

    assert "case_no" not in fields
    assert "approval_fields" not in fields
    assert "benchmark_land_id" not in fields
    assert "benchmark_land_price" not in fields
    assert "rounding_increment" not in fields
    assert "weight_total" not in fields
    assert "valuation_base_date" in fields
    assert "land_no" in fields
    assert "comparison_weight" in fields


def extraction_record(text: str) -> DocumentExtractionRecord:
    return DocumentExtractionRecord(
        extraction_id=uuid4(),
        case_id=uuid4(),
        document_id=uuid4(),
        provider="LOCAL_OCR",
        extraction_status="COMPLETED",
        extracted_text=text,
        page_count=1,
        created_by_user_id=uuid4(),
    )


def test_candidate_requires_exact_ocr_evidence_and_keeps_provenance() -> None:
    extraction = extraction_record("實例編號:2\n交易日期103年05月26日")
    result = FieldAnalysisResult(
        candidates=(
            AnalyzedFieldCandidate(
                field_name="transaction_no",
                extracted_value="2",
                confidence=Decimal("0.9700"),
                source_text="實例編號:2",
            ),
        ),
        provider="BEDROCK",
        model_id="test-model",
        prompt_version="field-analysis-test-v1",
    )

    records = FieldAnalysisService._candidate_records(
        extraction,
        "F01",
        result,
        {"transaction_no": "買賣實例編號"},
    )

    assert records[0].extracted_value == "2"
    assert records[0].source_page == 1
    assert records[0].analysis_provider == "BEDROCK"
    assert records[0].model_id == "test-model"
    assert records[0].prompt_version == "field-analysis-test-v1"
    assert records[0].field_status == "NEEDS_CONFIRMATION"


def test_candidate_without_verbatim_source_is_rejected() -> None:
    extraction = extraction_record("實例編號:2")
    result = FieldAnalysisResult(
        candidates=(
            AnalyzedFieldCandidate(
                field_name="transaction_no",
                extracted_value="99",
                confidence=Decimal("0.9000"),
                source_text="實例編號:99",
            ),
        ),
        provider="BEDROCK",
        model_id="test-model",
        prompt_version="field-analysis-test-v1",
    )

    with pytest.raises(AppError) as error:
        FieldAnalysisService._candidate_records(
            extraction,
            "F01",
            result,
            {"transaction_no": "買賣實例編號"},
        )

    assert error.value.code == "BEDROCK_FIELD_EVIDENCE_INVALID"


def test_ollama_candidate_without_verbatim_source_can_be_dropped_safely() -> None:
    extraction = extraction_record("估價基準日:1050901")
    result = FieldAnalysisResult(
        candidates=(
            AnalyzedFieldCandidate(
                field_name="land_no",
                extracted_value="不存在地號",
                confidence=Decimal("0.9000"),
                source_text="不存在的 OCR 證據",
            ),
        ),
        provider="OLLAMA",
        model_id="qwen3.5:latest",
        prompt_version="field-analysis-test-v1",
    )

    records = FieldAnalysisService._candidate_records(
        extraction,
        "F03",
        result,
        {"land_no": "地號"},
        drop_invalid_evidence=True,
    )

    assert records == []


def test_ollama_candidate_with_wrong_f03_surface_shape_is_dropped() -> None:
    extraction = extraction_record("區段號\nP001-00\n00區")
    result = FieldAnalysisResult(
        candidates=(
            AnalyzedFieldCandidate(
                field_name="price_zone_no",
                extracted_value="00區",
                confidence=Decimal("0.9500"),
                source_text="00區",
            ),
        ),
        provider="OLLAMA",
        model_id="qwen3.5:latest",
        prompt_version="field-analysis-test-v1",
    )

    records = FieldAnalysisService._candidate_records(
        extraction,
        "F03",
        result,
        {"price_zone_no": "區段號"},
        drop_invalid_evidence=True,
    )

    assert records == []


def test_ollama_batches_are_small_but_default_batches_remain_configured_size() -> None:
    service = FieldAnalysisService(
        None,
        settings=Settings(_env_file=None, ai_field_analysis_max_candidates=30),
    )
    fields = {f"f{index}": str(index) for index in range(5)}

    assert [len(batch) for batch in service._field_batches(fields, size=2)] == [2, 2, 1]
    assert [len(batch) for batch in service._field_batches(fields)] == [5]


def test_field_analysis_does_not_pretend_mock_is_bedrock() -> None:
    settings = Settings(_env_file=None, ai_provider="mock")

    with pytest.raises(AppError) as error:
        build_field_analysis_provider(settings)

    assert error.value.code == "FIELD_ANALYSIS_PROVIDER_NOT_CONFIGURED"


def test_field_analysis_builds_ollama_provider() -> None:
    provider = build_field_analysis_provider(ollama_settings())

    assert isinstance(provider, OllamaFieldAnalysisProvider)
    assert provider.model_id == "qwen3.5:latest"


def test_codex_schema_is_limited_to_remaining_fields() -> None:
    schema = field_analysis_output_schema(
        ("transaction_no", "transaction_date"),
        2,
    )

    candidates = schema["properties"]["candidates"]
    assert candidates["maxItems"] == 2
    assert candidates["items"]["properties"]["field_name"]["enum"] == [
        "transaction_no",
        "transaction_date",
    ]
    assert candidates["items"]["additionalProperties"] is False


def test_codex_prompt_requires_verbatim_value_and_source_text() -> None:
    prompt = field_analysis_prompt(
        "交易日期103年05月26日",
        "F01",
        {"transaction_date": "交易日期"},
    )

    assert "語意泛化與同義詞識別" in prompt
    assert "source_text" in prompt
    assert "extracted_value" in prompt
    assert "零虛構原則" in prompt
    assert "不可使用徵收宗地" in prompt


def test_field_analysis_prompt_includes_shared_markdown_and_selected_form_rules() -> None:
    prompt = field_analysis_prompt(
        "交易日期：114年5月28日",
        "F01",
        {"transaction_date": "交易日期"},
    )

    assert "field_rules_markdown" in prompt
    assert "field-rules-md-v1" in prompt
    assert "| `land_area` |" in prompt
    assert "## F01" in prompt
    assert "\n## F02\n" not in prompt


def test_codex_import_keeps_codex_provenance() -> None:
    extraction = extraction_record("實例編號:2")
    payload = CodexCandidateImportRequest(
        form_code="F01",
        model_id="gpt-5.6-sol",
        candidates=[
            {
                "field_name": "transaction_no",
                "extracted_value": "2",
                "confidence": "0.91",
                "source_text": "實例編號:2",
            }
        ],
    )
    result = FieldAnalysisResult(
        candidates=tuple(
            AnalyzedFieldCandidate(
                field_name=item.field_name,
                extracted_value=item.extracted_value,
                confidence=item.confidence,
                source_text=item.source_text,
            )
            for item in payload.candidates
        ),
        provider="CODEX",
        model_id=payload.model_id,
        prompt_version="codex-field-analysis-v1",
    )

    records = FieldAnalysisService._candidate_records(
        extraction,
        "F01",
        result,
        {"transaction_no": "買賣實例編號"},
        error_prefix="CODEX",
        source_label="Codex",
        error_status=422,
    )

    assert records[0].analysis_provider == "CODEX"
    assert records[0].model_id == "gpt-5.6-sol"
    assert records[0].prompt_version == "codex-field-analysis-v1"
    assert records[0].field_status == "NEEDS_CONFIRMATION"


def test_codex_import_rejects_untraceable_value() -> None:
    extraction = extraction_record("實例編號:2")
    result = FieldAnalysisResult(
        candidates=(
            AnalyzedFieldCandidate(
                field_name="transaction_no",
                extracted_value="99",
                confidence=Decimal("0.9000"),
                source_text="實例編號:2",
            ),
        ),
        provider="CODEX",
        model_id="gpt-5.6-sol",
        prompt_version="codex-field-analysis-v1",
    )

    with pytest.raises(AppError) as error:
        FieldAnalysisService._candidate_records(
            extraction,
            "F01",
            result,
            {"transaction_no": "買賣實例編號"},
            error_prefix="CODEX",
            source_label="Codex",
            error_status=422,
        )

    assert error.value.code == "CODEX_FIELD_EVIDENCE_INVALID"
    assert error.value.status_code == 422


def test_f02_rf_preserves_natural_language_until_formal_rule_is_selected() -> None:
    extraction = extraction_record("區段勘查表\n地勢：平坦\n使用分區：商業區")
    result = FieldAnalysisResult(
        candidates=(
            AnalyzedFieldCandidate(
                field_name="terrain",
                extracted_value="平坦",
                confidence=Decimal("0.9500"),
                source_text="地勢：平坦",
            ),
            AnalyzedFieldCandidate(
                field_name="land_use_zone",
                extracted_value="L1",
                confidence=Decimal("0.9200"),
                source_text="使用分區：商業區",
            ),
        ),
        provider="BEDROCK",
        model_id="test-model",
        prompt_version="field-analysis-test-v1",
    )

    records = FieldAnalysisService._candidate_records(
        extraction,
        "F02-RF",
        result,
        {
            "terrain": "地勢等級",
            "land_use_zone": "使用分區",
        },
    )

    assert len(records) == 2
    assert records[0].field_name == "terrain"
    assert records[0].extracted_value == "平坦"
    assert records[0].source_text == "地勢：平坦"
    assert records[1].field_name == "land_use_zone"
    assert records[1].extracted_value == "L1"
    assert records[1].source_text == "使用分區：商業區"


def test_bedrock_rejects_ungrounded_candidate() -> None:
    extraction = extraction_record("比準地地號：100號")
    result = FieldAnalysisResult(
        candidates=(
            AnalyzedFieldCandidate(
                field_name="benchmark_land_no",
                extracted_value="100號",
                confidence=Decimal("0.9800"),
                source_text="比準地地號：100號",
            ),
            AnalyzedFieldCandidate(
                field_name="valuation_base_date",
                extracted_value="113年05月20日",
                confidence=Decimal("0.9000"),
                source_text="估價日期：113年05月20日",  # Not in OCR text
            ),
        ),
        provider="BEDROCK",
        model_id="test-model",
        prompt_version="field-analysis-test-v1",
    )

    with pytest.raises(AppError) as error:
        FieldAnalysisService._candidate_records(
            extraction,
            "F03",
            result,
            {
                "benchmark_land_no": "比準地地號",
                "valuation_base_date": "估價基準日",
            },
        )

    assert error.value.code == "BEDROCK_FIELD_EVIDENCE_INVALID"



def test_s01_analysis_fields_are_imported_from_the_workbook_catalog() -> None:
    fields = FIELD_ANALYSIS_FIELDS["S01"]

    assert len(fields) == 77
    assert set(
        {
            "price_zone_no",
            "zone_boundary_description",
            "main_road_width_m",
            "survey_date",
            "commercial_facility_distance_m",
        }
    ).issubset(fields)
    assert "區段內主要道路名稱" in fields["main_road_name"]


def test_f02_rf_commercial_analysis_fields_are_linked_to_source_item_codes() -> None:
    fields = FIELD_ANALYSIS_FIELDS["F02-RF"]

    assert len(fields) == 29
    assert "commercial source item C1_01" in fields["urban_plan_status"]
    assert "commercial source item C8_01" in fields["other"]


def test_s01_schema_only_allows_imported_workbook_field_codes() -> None:
    fields = FIELD_ANALYSIS_FIELDS["S01"]
    schema = field_analysis_output_schema(tuple(fields), 100)
    allowed = schema["properties"]["candidates"]["items"]["properties"]["field_name"]["enum"]

    assert allowed == list(fields)
    assert "not_a_workbook_field" not in allowed

def test_s01_analysis_catalog_is_batched_to_the_configured_ai_limit() -> None:
    service = FieldAnalysisService(
        None,
        settings=Settings(_env_file=None, ai_field_analysis_max_candidates=30),
    )

    batches = service._field_batches(FIELD_ANALYSIS_FIELDS["S01"])

    assert [len(batch) for batch in batches] == [30, 30, 17]
    assert list(batches[0])[0] == "administrative_area"
    assert "survey_date" in batches[-1]
