from types import SimpleNamespace

import boto3
import pytest

from app.ai_assistant.provider import BedrockConverseProvider


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
