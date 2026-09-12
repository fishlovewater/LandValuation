from types import SimpleNamespace

import pytest

from app.ai_assistant.routing import (
    AssistantAnswerRoute,
    _parse_semantic_route,
    analyze_assistant_question,
    route_assistant_question,
)


def test_deterministic_router_covers_chat_case_knowledge_and_hybrid() -> None:
    assert route_assistant_question("你好", has_case_context=True) == AssistantAnswerRoute.CHAT
    assert route_assistant_question(
        "我這筆現在能送審了嗎？",
        has_case_context=True,
    ) == AssistantAnswerRoute.CASE
    assert route_assistant_question(
        "土地徵收補償市價查估的法規依據是什麼？",
        has_case_context=False,
    ) == AssistantAnswerRoute.KNOWLEDGE
    assert route_assistant_question(
        "本案調整率是否符合規定？",
        has_case_context=True,
    ) == AssistantAnswerRoute.HYBRID


def test_semantic_route_cannot_create_case_context_that_does_not_exist() -> None:
    assert _parse_semantic_route(
        '{"route":"CASE"}',
        has_case_context=False,
    ) == AssistantAnswerRoute.CHAT
    assert _parse_semantic_route(
        '{"route":"HYBRID"}',
        has_case_context=False,
    ) == AssistantAnswerRoute.KNOWLEDGE


@pytest.mark.asyncio
async def test_semantic_router_uses_safe_fallback_when_ai_provider_is_mock(monkeypatch) -> None:
    import app.core.config as config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(ai_provider="mock"))
    assert await analyze_assistant_question(
        "我這筆現在能送審了嗎？",
        has_case_context=True,
        workspace="history",
    ) == AssistantAnswerRoute.CASE


@pytest.mark.asyncio
async def test_semantic_router_uses_the_same_model_router_for_history(monkeypatch) -> None:
    import app.ai_assistant.provider as provider_module
    import app.core.config as config

    class FakeProvider:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def converse(self, _messages):
            return SimpleNamespace(text='{"route":"HYBRID"}')

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(ai_provider="ollama"))
    monkeypatch.setattr(provider_module, "OllamaChatProvider", FakeProvider)

    assert await analyze_assistant_question(
        "這筆作法符合規定嗎？",
        has_case_context=True,
        workspace="history",
    ) == AssistantAnswerRoute.HYBRID


@pytest.mark.asyncio
async def test_hybrid_answer_uses_one_final_synthesis_call(monkeypatch) -> None:
    import app.ai_assistant.chat_service as chat_service

    captured_messages = []

    class FakeProvider:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def converse(self, messages):
            captured_messages.extend(messages)
            return SimpleNamespace(text="本案目前資料與規範綜合判斷如下。【來源1】")

    monkeypatch.setattr(
        chat_service,
        "get_settings",
        lambda: SimpleNamespace(ai_provider="ollama", ollama_model="test-model"),
    )
    monkeypatch.setattr(chat_service, "OllamaChatProvider", FakeProvider)

    answer, model_id = await chat_service.answer_hybrid_chat(
        "這筆作法符合規定嗎？",
        case_context={"case": {"case_status": "PROCESSING"}},
        case_summary="本案目前調整率為 -12%。",
        knowledge_result={
            "answer_status": "SUPPORTED",
            "answer": "正式來源要求調整應具備理由。【來源1】",
            "citations": [{"chunk_id": "source-1", "quoted_text": "調整應具備理由"}],
        },
    )

    assert answer == "本案目前資料與規範綜合判斷如下。【來源1】"
    assert model_id == "test-model"
    assert len(captured_messages) == 1
    prompt = captured_messages[0]["content"]
    assert "本案目前調整率為 -12%" in prompt
    assert "正式來源要求調整應具備理由" in prompt
