from __future__ import annotations

import asyncio
import json
from typing import Iterable

from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.ai_contract import (
    AiAnswer,
    answer_prompt,
    build_source_packet,
    parse_answer,
    source_grounding_instructions,
)
from app.knowledge.service import RetrievedKnowledge


class BedrockKnowledgeProvider:
    """Amazon Bedrock Converse adapter. It intentionally supplies no web or tool access."""

    provider_name = "bedrock"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def model_id(self) -> str | None:
        return self.settings.bedrock_model_id

    def configured(self) -> bool:
        return bool(self.settings.bedrock_region and self.settings.bedrock_model_id)

    async def answer(
        self,
        *,
        question: str,
        candidates: Iterable[RetrievedKnowledge],
    ) -> AiAnswer:
        if not self.configured():
            raise AppError(
                "AI_PROVIDER_CONFIGURATION_ERROR",
                "Bedrock 需要設定 BEDROCK_REGION 與 BEDROCK_MODEL_ID。",
                503,
            )
        packet = build_source_packet(candidates, self.settings.knowledge_ai_max_source_characters)
        if not packet:
            return AiAnswer(
                answer="目前沒有可提供給 AI 分析的已發布且已擷取來源。",
                cited_chunk_ids=[],
                evidence=[],
                needs_clarification=True,
                clarification_question="請先確認相關法規、規則或手冊已完成擷取並發布。",
            )
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "未安裝 boto3，無法使用 Bedrock provider。",
                503,
            ) from exc

        def invoke() -> dict:
            client = boto3.client(
                "bedrock-runtime",
                region_name=self.settings.bedrock_region,
                config=Config(
                    connect_timeout=5,
                    read_timeout=self.settings.bedrock_timeout_seconds,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
            return client.converse(
                modelId=self.settings.bedrock_model_id,
                system=[
                    {
                        "text": (
                            source_grounding_instructions()
                        )
                    }
                ],
                messages=[{"role": "user", "content": [{"text": answer_prompt(question, packet)}]}],
                inferenceConfig={
                    "maxTokens": self.settings.bedrock_max_tokens,
                    "temperature": self.settings.bedrock_temperature,
                },
            )

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(invoke), timeout=self.settings.bedrock_timeout_seconds
            )
        except TimeoutError as exc:
            raise AppError("AI_PROVIDER_TIMEOUT", "Bedrock 分析逾時，請稍後再試。", 504) from exc
        except Exception as exc:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "Bedrock 無法完成分析；請確認 AWS IAM、Region、模型存取權與網路。",
                503,
            ) from exc
        text_blocks = [
            block["text"]
            for block in response.get("output", {}).get("message", {}).get("content", [])
            if "text" in block
        ]
        output = "".join(text_blocks).strip()
        if output.startswith("```"):
            output = output.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return parse_answer(output, packet)
