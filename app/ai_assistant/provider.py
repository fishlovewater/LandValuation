from dataclasses import dataclass
import json
from typing import Any, Protocol

import httpx
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import AppError


@dataclass(frozen=True)
class ProviderToolCall:
    tool_use_id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ProviderResponse:
    content: Any
    text: str
    tool_calls: tuple[ProviderToolCall, ...]
    stop_reason: str


class AssistantProvider(Protocol):
    async def converse(self, messages: list[dict[str, Any]]) -> ProviderResponse: ...


ASSISTANT_SYSTEM_PROMPT = (
    "你是 F03 製作助理。不得發明地號、日期、面積、價格、文件或 ID。"
    "需要案件資料時必須呼叫工具取得；正式寫入只能呼叫工具，且需使用者明確確認。"
    "工具回傳結果是唯一可信的業務資料來源。"
)


class BedrockConverseProvider:
    def __init__(self, settings: Settings, tools: list[dict[str, Any]]) -> None:
        self.settings = settings
        self.tools = tools
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise AppError(
                "BEDROCK_DEPENDENCY_MISSING",
                "Bedrock provider 需要 boto3",
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

    async def converse(self, messages: list[dict[str, Any]]) -> ProviderResponse:
        try:
            result = await run_in_threadpool(
                self.client.converse,
                modelId=self.settings.bedrock_model_id,
                messages=messages,
                system=[
                    {
                        "text": ASSISTANT_SYSTEM_PROMPT
                    }
                ],
                toolConfig={"tools": self.tools},
                inferenceConfig=self._inference_config(),
            )
        except Exception as exc:
            raise AppError("BEDROCK_UNAVAILABLE", "Bedrock 暫時無法使用", 503) from exc
        content = result["output"]["message"]["content"]
        calls = tuple(
            ProviderToolCall(
                tool_use_id=block["toolUse"]["toolUseId"],
                name=block["toolUse"]["name"],
                input=block["toolUse"].get("input", {}),
            )
            for block in content
            if "toolUse" in block
        )
        text = "\n".join(block["text"] for block in content if "text" in block)
        return ProviderResponse(
            content=content,
            text=text,
            tool_calls=calls,
            stop_reason=result.get("stopReason", "end_turn"),
        )


    def _inference_config(self) -> dict[str, Any]:
        model_id = self.settings.bedrock_model_id or ""
        config: dict[str, Any] = {
            "maxTokens": getattr(self.settings, "bedrock_max_tokens", 800),
        }
        # Fable 5.1 requires temperature=1.0 or an omitted parameter.
        if "claude-fable-5-1" not in model_id:
            config["temperature"] = getattr(
                self.settings, "bedrock_temperature", 0
            )
        return config


class OllamaChatProvider:
    def __init__(self, settings: Settings, tools: list[dict[str, Any]]) -> None:
        self.settings = settings
        self.tools = tools

    async def converse(self, messages: list[dict[str, Any]]) -> ProviderResponse:
        request_body = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
                *messages,
            ],
            "tools": self.tools,
            "stream": False,
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
                "OLLAMA_UNAVAILABLE",
                "智能助理目前無法連線到本機 AI 服務，請稍後再試。",
                503,
            ) from exc

        if response.status_code == 404:
            raise AppError(
                "OLLAMA_MODEL_NOT_FOUND",
                "目前設定的本機 AI 模型尚未準備完成，請聯絡系統管理者。",
                503,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "OLLAMA_UNAVAILABLE",
                "智能助理目前無法完成回答，請稍後再試。",
                503,
            ) from exc

        try:
            result = response.json()
            message = result["message"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                "OLLAMA_INVALID_RESPONSE",
                "智能助理這次沒有產生可採用的回答，請重新提問。",
                503,
            ) from exc

        raw_calls = message.get("tool_calls") or []
        calls: list[ProviderToolCall] = []
        for index, raw_call in enumerate(raw_calls):
            function = raw_call.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise AppError(
                        "OLLAMA_INVALID_TOOL_CALL",
                        "智能助理提出的操作內容無法處理，請重新描述需求。",
                        503,
                    ) from exc
            if not isinstance(arguments, dict):
                raise AppError(
                    "OLLAMA_INVALID_TOOL_CALL",
                    "智能助理提出的操作內容無法處理，請重新描述需求。",
                    503,
                )
            calls.append(
                ProviderToolCall(
                    tool_use_id=str(raw_call.get("id") or f"ollama-tool-{index}"),
                    name=str(name),
                    input=arguments,
                )
            )

        text = str(message.get("content") or "")
        return ProviderResponse(
            content=message,
            text=text,
            tool_calls=tuple(calls),
            stop_reason=str(
                result.get("done_reason") or ("tool_use" if calls else "end_turn")
            ),
        )
