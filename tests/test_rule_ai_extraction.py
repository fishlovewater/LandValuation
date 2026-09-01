from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.valuation.rule_packs import ai_extraction
from app.valuation.rule_packs.ai_extraction import RuleAIResult, build_rule_extractor
from app.valuation.rule_packs.schemas import RulePackAIExtractionRequest


def test_rule_ai_candidate_requires_structured_definitions_and_levels():
    value = RuleAIResult.model_validate(
        {
            "factor_definitions": [
                {
                    "factor_code": "road_width",
                    "factor_name": "道路寬度",
                    "factor_category": "交通",
                    "data_type": "NUMBER",
                    "unit": "公尺",
                    "display_order": 1,
                }
            ],
            "factor_levels": [
                {
                    "factor_code": "road_width",
                    "land_use_type": "COMMERCIAL",
                    "level_code": "L1",
                    "level_name": "未滿八公尺",
                    "range_min": None,
                    "range_max": 8,
                    "qualitative_value": None,
                    "suggested_rate": "-0.05",
                    "maximum_impact_rate": "0.10",
                    "sort_order": 1,
                }
            ],
            "evidence": [
                {
                    "factor_code": "road_width",
                    "level_code": "L1",
                    "source_page": 2,
                    "source_text": "未滿八公尺：-5%",
                }
            ],
            "warnings": [],
        }
    )
    assert value.factor_levels[0].suggested_rate == Decimal("-0.05")
    assert value.evidence[0].source_page == 2


def test_mock_provider_does_not_fabricate_rule_candidates():
    with pytest.raises(AppError) as captured:
        build_rule_extractor(Settings(ai_provider="mock"))
    assert captured.value.code == "RULE_AI_NOT_CONFIGURED"


def test_ai_analysis_is_explicit_opt_in():
    payload = RulePackAIExtractionRequest()
    assert payload.confirm_ai_analysis is False


@pytest.mark.asyncio
async def test_gemini_rule_extractor_uses_dedicated_api_key(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"factor_definitions":[{"factor_code":"road_width",'
                                        '"factor_name":"道路寬度","factor_category":"交通",'
                                        '"data_type":"NUMBER","unit":"公尺","display_order":1}],'
                                        '"factor_levels":[{"factor_code":"road_width",'
                                        '"land_use_type":"COMMERCIAL","level_code":"L1",'
                                        '"level_name":"未滿八公尺","range_min":null,"range_max":8,'
                                        '"qualitative_value":null,"suggested_rate":"-0.05",'
                                        '"maximum_impact_rate":"0.10","sort_order":1}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    class Client:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, body=json)
            return Response()

    monkeypatch.setattr(ai_extraction.httpx, "AsyncClient", Client)
    extractor = build_rule_extractor(
        Settings(
            ai_provider="gemini",
            gemini_api_key="gemini-key",
            aws_access_key_id="wrong-aws-key",
        )
    )

    await extractor.extract("未滿八公尺：-5%", ["COMMERCIAL"])

    assert captured["headers"]["x-goog-api-key"] == "gemini-key"
    assert captured["url"].endswith("/gemini-2.5-flash:generateContent")
