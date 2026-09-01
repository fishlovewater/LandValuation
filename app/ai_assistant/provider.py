from dataclasses import dataclass
from typing import Any, Protocol

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
    content: list[dict[str, Any]]
    text: str
    tool_calls: tuple[ProviderToolCall, ...]
    stop_reason: str


class AssistantProvider(Protocol):
    async def converse(self, messages: list[dict[str, Any]]) -> ProviderResponse: ...


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
                        "text": (
                            "你是 F03 製作助理。不得發明地號、日期、面積、價格、"
                            "文件或 ID。正式寫入只能呼叫工具，且需使用者明確確認。"
                        )
                    }
                ],
                toolConfig={"tools": self.tools},
                inferenceConfig={"temperature": 0, "maxTokens": 800},
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

