from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.valuation.rule_packs.schemas import (
    FactorDefinitionInput,
    FactorLevelInput,
    RuleEvidenceInput,
)

GEMINI_MODEL_ID = "gemini-2.5-flash"


class RuleAIResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_definitions: list[FactorDefinitionInput] = Field(min_length=1)
    factor_levels: list[FactorLevelInput] = Field(min_length=1)
    evidence: list[RuleEvidenceInput] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _prompt(source_text: str, land_use_types: list[str]) -> str:
    return f"""你是臺灣土地估價規則表的資料轉換器。將來源內容轉成指定 JSON。
不得補造來源中不存在的因素、級距、修正率或數值。無法確定時放入 warnings。
每一個因素與級距都應提供可在來源全文中逐字找到的 evidence.source_text；頁碼未知可省略。
factor_code 使用簡短穩定英文代碼；suggested_rate 與 maximum_impact_rate 使用小數，例如 5% 寫 0.05。
土地用途只能使用：{', '.join(land_use_types)}。
輸出欄位為 factor_definitions、factor_levels、evidence、warnings，且不得輸出 Markdown。

來源全文：
{source_text}
"""


class GeminiRuleExtractor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def extract(self, source_text: str, land_use_types: list[str]) -> RuleAIResult:
        if not source_text.strip():
            raise AppError("RULE_SOURCE_TEXT_EMPTY", "規則來源無法擷取文字", 422)
        schema = RuleAIResult.model_json_schema()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL_ID}:generateContent"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": _prompt(source_text, land_use_types)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
                response = await client.post(
                    url,
                    headers={
                        "x-goog-api-key": self.settings.gemini_api_key.get_secret_value(),
                        "content-type": "application/json",
                    },
                    json=body,
                )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = RuleAIResult.model_validate(json.loads(text))
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as exc:
            raise AppError("GEMINI_RULE_EXTRACTION_FAILED", "Gemini 規則表轉換失敗", 503) from exc

        missing_evidence = [
            item.source_text for item in result.evidence if item.source_text not in source_text
        ]
        if missing_evidence:
            result.warnings.append(
                f"有 {len(missing_evidence)} 筆 AI 證據無法在擷取文字中核對，確認前請人工檢查"
            )
        return result


def build_rule_extractor(settings: Settings) -> GeminiRuleExtractor:
    if settings.ai_provider == "mock":
        raise AppError(
            "RULE_AI_NOT_CONFIGURED",
            "尚未設定 AI；暫用 Gemini 時請將 AI_PROVIDER 設為 gemini，"
            "並設定 GEMINI_API_KEY",
            503,
        )
    if settings.ai_provider != "gemini":
        raise AppError(
            "RULE_AI_PROVIDER_UNSUPPORTED",
            "規則表 AI 轉換目前支援 Gemini；原有 Bedrock 助理設定不受影響",
            503,
        )
    return GeminiRuleExtractor(settings)
