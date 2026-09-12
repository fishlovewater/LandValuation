from __future__ import annotations

import json
import logging
import re
from enum import StrEnum
from typing import Any


logger = logging.getLogger(__name__)


class AssistantAnswerRoute(StrEnum):
    CHAT = "CHAT"
    CASE = "CASE"
    KNOWLEDGE = "KNOWLEDGE"
    HYBRID = "HYBRID"


SEMANTIC_ROUTER_SYSTEM_PROMPT = """你是土地估價系統 AI 助手的內部分流器。你的工作不是回答問題，而是判斷回答問題最低限度需要哪些已授權資料。

只回傳 JSON，不要 Markdown，也不要解釋推理：
{"route":"CHAT|CASE|KNOWLEDGE|HYBRID"}

判斷規則：
- CHAT：一般聊天、改寫、說明或不需要目前案件資料與正式知識來源即可回答的問題。
- CASE：必須讀取目前已連結案件／審查／案件歷程的結構化資料，但不需要法規、手冊或正式知識來源。
- KNOWLEDGE：必須查詢法規、手冊、正式依據、定義或土地估價知識，但不需要目前案件資料。
- HYBRID：同時需要目前案件資料與正式知識來源，例如判斷本案作法、數值、文件或審查結果是否符合規定。

「這筆、這案、目前、它、剛剛那個」等自然指涉，在 HAS_CASE_CONTEXT=true 且對話內容合理指向目前案件時，應視為案件情境，不要求使用者一定說出「案件」兩字。
只有真正承接上一輪問題的追問才沿用 PREVIOUS_ROUTE。工作區 valuation、review、history 都使用相同判斷規則；history 只是唯讀情境，不代表不能讀案件資料。
你只負責選資料路徑，不負責授權。不可因為某路徑可能沒有權限就改判其他路徑。"""


_SMALLTALK_PATTERN = re.compile(
    r"^(?:嗨|哈囉|哈啰|hello|hi|hey|你好|您好|早安|午安|晚安|"
    r"謝謝|感謝|多謝|掰掰|再見|辛苦了|你是誰|你能做什麼|可以做什麼)[！!。\.？?\s]*$",
    re.IGNORECASE,
)

_FOLLOW_UP_PATTERN = re.compile(
    r"(?:剛剛|剛才|前面|上述|前述|那個|這個|它|再說一次|再解釋|"
    r"講簡單|說簡單|簡單一點|詳細一點|為什麼|所以呢|那呢|然後呢)",
    re.IGNORECASE,
)

_CASE_TERMS = (
    "本案",
    "這個案件",
    "這筆案件",
    "目前案件",
    "案件目前",
    "案件狀態",
    "審查狀態",
    "目前狀態",
    "目前進度",
    "下一步",
    "缺件",
    "缺少",
    "待補",
    "疑點",
    "風險",
    "辨識結果",
    "ocr",
    "擷取欄位",
    "這個欄位",
    "這筆欄位",
    "這個疑點",
    "這筆疑點",
    "這份文件",
    "目前文件",
    "來源文件",
    "目前有哪些資料",
    "目前有哪些文件",
)

_KNOWLEDGE_TERMS = (
    "法規",
    "法條",
    "條文",
    "規定",
    "規範",
    "規則",
    "依據",
    "手冊",
    "作業手冊",
    "合法",
    "違反",
    "是否符合",
    "應如何",
    "查估",
    "土地徵收",
    "市價查估",
    "土地估價",
    "估價",
    "徵收補償",
    "地價",
    "比準地",
    "比較標的",
    "調整率",
    "一般因素",
    "區域因素",
    "個別因素",
    "宗地",
    "路線價",
    "評價基準",
    "查估書表",
    "f01",
    "f02",
    "f03",
    "估價規則",
)


def route_assistant_question(
    question: str,
    *,
    has_case_context: bool,
    previous_route: AssistantAnswerRoute | str | None = None,
) -> AssistantAnswerRoute:
    """Choose the minimum authorized data path needed for a question."""

    normalized = " ".join(question.strip().split()).lower()
    if not normalized or _SMALLTALK_PATTERN.fullmatch(normalized):
        return AssistantAnswerRoute.CHAT

    asks_case = has_case_context and any(term in normalized for term in _CASE_TERMS)
    asks_knowledge = any(term in normalized for term in _KNOWLEDGE_TERMS)

    if asks_case and asks_knowledge:
        return AssistantAnswerRoute.HYBRID
    if asks_case:
        return AssistantAnswerRoute.CASE
    if asks_knowledge:
        return AssistantAnswerRoute.KNOWLEDGE

    if _FOLLOW_UP_PATTERN.search(normalized) and previous_route:
        try:
            prior = AssistantAnswerRoute(previous_route)
        except ValueError:
            prior = AssistantAnswerRoute.CHAT
        if not has_case_context and prior in {AssistantAnswerRoute.CASE, AssistantAnswerRoute.HYBRID}:
            return AssistantAnswerRoute.CHAT
        return prior

    # Free-form non-domain requests do not need RAG. Even when a case is open,
    # case data is read only when the question explicitly refers to the case.
    return AssistantAnswerRoute.CHAT


def _semantic_router_payload(
    question: str,
    *,
    has_case_context: bool,
    workspace: str | None,
    previous_route: AssistantAnswerRoute | str | None,
    conversation_history: list[dict[str, str]] | None,
) -> str:
    recent = [
        {
            "role": item.get("role"),
            "content": str(item.get("content") or "")[:1200],
        }
        for item in (conversation_history or [])[-4:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    payload = {
        "question": question,
        "has_case_context": has_case_context,
        "workspace": workspace,
        "previous_route": str(previous_route) if previous_route else None,
        "recent_conversation": recent,
    }
    return json.dumps(payload, ensure_ascii=False)


def _parse_semantic_route(output: str, *, has_case_context: bool) -> AssistantAnswerRoute:
    cleaned = output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    parsed: Any = json.loads(cleaned)
    raw_route = parsed.get("route") if isinstance(parsed, dict) else None
    route = AssistantAnswerRoute(str(raw_route).strip().upper())
    if has_case_context:
        return route
    if route == AssistantAnswerRoute.CASE:
        return AssistantAnswerRoute.CHAT
    if route == AssistantAnswerRoute.HYBRID:
        return AssistantAnswerRoute.KNOWLEDGE
    return route


async def analyze_assistant_question(
    question: str,
    *,
    has_case_context: bool,
    workspace: str | None = None,
    previous_route: AssistantAnswerRoute | str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> AssistantAnswerRoute:
    """Semantically classify one Assistant turn, with deterministic fallback.

    The classifier chooses only a data path. Authorization is enforced later by
    the concrete CASE/KNOWLEDGE/HYBRID handlers, so a model can never grant
    itself access to additional data.
    """

    fallback = route_assistant_question(
        question,
        has_case_context=has_case_context,
        previous_route=previous_route,
    )
    if not question.strip() or _SMALLTALK_PATTERN.fullmatch(question.strip()):
        return fallback

    try:
        from app.ai_assistant.provider import BedrockConverseProvider, OllamaChatProvider
        from app.core.config import get_settings

        settings = get_settings()
        provider_name = settings.ai_provider.upper()
        router_input = _semantic_router_payload(
            question,
            has_case_context=has_case_context,
            workspace=workspace,
            previous_route=previous_route,
            conversation_history=conversation_history,
        )
        if provider_name == "OLLAMA":
            provider = OllamaChatProvider(
                settings,
                [],
                system_prompt=SEMANTIC_ROUTER_SYSTEM_PROMPT,
            )
            response = await provider.converse([{"role": "user", "content": router_input}])
        elif provider_name == "BEDROCK":
            provider = BedrockConverseProvider(
                settings,
                [],
                system_prompt=SEMANTIC_ROUTER_SYSTEM_PROMPT,
            )
            response = await provider.converse(
                [{"role": "user", "content": [{"text": router_input}]}]
            )
        else:
            return fallback
        return _parse_semantic_route(response.text, has_case_context=has_case_context)
    except Exception as exc:  # semantic routing must never make chat unavailable
        logger.warning(
            "Assistant semantic routing failed; using deterministic fallback: %s",
            type(exc).__name__,
        )
        return fallback


__all__ = [
    "AssistantAnswerRoute",
    "analyze_assistant_question",
    "route_assistant_question",
]
