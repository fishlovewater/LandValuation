from __future__ import annotations

import re
from enum import StrEnum


class AssistantAnswerRoute(StrEnum):
    CHAT = "CHAT"
    CASE = "CASE"
    KNOWLEDGE = "KNOWLEDGE"
    HYBRID = "HYBRID"


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


__all__ = ["AssistantAnswerRoute", "route_assistant_question"]
