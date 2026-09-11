from types import SimpleNamespace

import boto3
import pytest

from app.ai_assistant.provider import BedrockConverseProvider, OllamaChatProvider


class FakeBedrockRuntimeClient:
    def __init__(self) -> None:
        self.request = None

    def converse(self, **kwargs):
        self.request = kwargs
        return {
            "output": {
                "message": {
                    "content": [
                        {"text": "我先讀取 F03 缺件。"},
                        {
                            "toolUse": {
                                "toolUseId": "tool-1",
                                "name": "get_missing_items",
                                "input": {},
                            }
                        },
                    ]
                }
            },
            "stopReason": "tool_use",
        }


class FakeOllamaResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "message": {
                "role": "assistant",
                "content": "我先檢查缺件。",
                "tool_calls": [
                    {
                        "function": {
                            "index": 0,
                            "name": "get_missing_items",
                            "arguments": {},
                        }
                    }
                ],
            },
            "done": True,
            "done_reason": "stop",
        }


class FakeAsyncClient:
    request = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        FakeAsyncClient.request = {"url": url, "json": json, "kwargs": self.kwargs}
        return FakeOllamaResponse()


@pytest.mark.asyncio
async def test_bedrock_converse_parses_text_and_controlled_tool_call(
    monkeypatch,
) -> None:
    client = FakeBedrockRuntimeClient()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    settings = SimpleNamespace(
        bedrock_region="ap-northeast-1",
        bedrock_model_id="test-model",
        ai_timeout_seconds=30,
    )
    tools = [
        {
            "toolSpec": {
                "name": "get_missing_items",
                "description": "取得缺件",
                "inputSchema": {"json": {"type": "object"}},
            }
        }
    ]
    provider = BedrockConverseProvider(settings, tools)

    response = await provider.converse(
        [{"role": "user", "content": [{"text": "目前還缺什麼？"}]}]
    )

    assert response.text == "我先讀取 F03 缺件。"
    assert response.stop_reason == "tool_use"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].tool_use_id == "tool-1"
    assert response.tool_calls[0].name == "get_missing_items"
    assert response.tool_calls[0].input == {}
    assert client.request["modelId"] == "test-model"
    assert client.request["inferenceConfig"]["temperature"] == 0
    assert client.request["toolConfig"] == {"tools": tools}


@pytest.mark.asyncio
async def test_ollama_converse_uses_native_chat_api_and_parses_tool_call(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.ai_assistant.provider.httpx.AsyncClient",
        FakeAsyncClient,
    )
    settings = SimpleNamespace(
        ollama_base_url="http://localhost:11434",
        ollama_model="qwen3.5:latest",
        ollama_timeout_seconds=120,
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_missing_items",
                "description": "取得缺件",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    provider = OllamaChatProvider(settings, tools)

    response = await provider.converse(
        [{"role": "user", "content": "目前還缺什麼？"}]
    )

    assert response.text == "我先檢查缺件。"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "get_missing_items"
    assert response.tool_calls[0].input == {}
    assert FakeAsyncClient.request["url"] == "http://localhost:11434/api/chat"
    body = FakeAsyncClient.request["json"]
    assert body["model"] == "qwen3.5:latest"
    assert body["stream"] is False
    assert body["tools"] == tools
    assert body["options"]["temperature"] == 0
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1] == {
        "role": "user",
        "content": "目前還缺什麼？",
    }
