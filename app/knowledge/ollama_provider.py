from __future__ import annotations

import json
from typing import Iterable

import httpx

from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.ai_contract import (
    AiAnswer,
    answer_output_schema,
    answer_prompt,
    build_source_packet,
    parse_answer,
    source_grounding_instructions,
)
from app.knowledge.service import RetrievedKnowledge


class OllamaKnowledgeProvider:
    """Source-grounded Knowledge provider backed by the local Ollama runtime."""

    provider_name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def model_id(self) -> str | None:
        return self.settings.ollama_model

    def configured(self) -> bool:
        return bool(self.settings.ollama_base_url and self.settings.ollama_model)

    async def answer(
        self,
        *,
        question: str,
        candidates: Iterable[RetrievedKnowledge],
    ) -> AiAnswer:
        packet = build_source_packet(
            candidates,
            self.settings.knowledge_ai_max_source_characters,
        )
        if not packet:
            return AiAnswer(
                answer="目前找不到足以回答這個問題的可核對資料。",
                cited_chunk_ids=[],
                evidence=[],
                needs_clarification=True,
                clarification_question="請確認相關法規、規則或手冊已加入知識庫。",
            )

        request_body = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": source_grounding_instructions()},
                {"role": "user", "content": answer_prompt(question, packet)},
            ],
            "stream": False,
            "format": answer_output_schema(),
            "options": {"temperature": 0},
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.ollama_timeout_seconds
            ) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/chat",
                    json=request_body,
                )
        except httpx.RequestError as exc:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "智能助理目前無法連線到本機 AI 服務，請稍後再試。",
                503,
            ) from exc

        if response.status_code == 404:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "目前設定的本機 AI 模型尚未準備完成，請聯絡系統管理者。",
                503,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "智能助理目前無法完成回答，請稍後再試。",
                503,
            ) from exc

        try:
            payload = response.json()
            output = str(payload["message"]["content"]).strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "智能助理這次沒有產生可採用的回答，請重新提問。",
                502,
            ) from exc

        if output.startswith("```"):
            output = output.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        # Some models occasionally JSON-encode the object one extra time.
        if output.startswith('"'):
            try:
                decoded = json.loads(output)
                if isinstance(decoded, str):
                    output = decoded
            except json.JSONDecodeError:
                pass
        return parse_answer(output, packet)