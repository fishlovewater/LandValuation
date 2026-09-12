from __future__ import annotations

import json
from typing import Any

from app.ai_assistant.provider import BedrockConverseProvider, OllamaChatProvider
from app.core.config import get_settings


GENERAL_ASSISTANT_SYSTEM_PROMPT = (
    "你是土地估價系統內的 AI 助手。請使用繁體中文、簡潔且專業地回答。"
    "這個路徑只用於一般對話，不會提供案件資料或知識庫來源。"
    "若使用者要求目前案件的事實、法規條文、正式依據或文件內容，"
    "不要猜測，請提醒系統需要改走資料查詢流程。"
)

CASE_ASSISTANT_SYSTEM_PROMPT = (
    "你是土地估價系統內的 AI 助手。請使用繁體中文、簡潔且專業地回答。"
    "你只能根據系統提供的結構化案件資料回答，不得補充未提供的案件事實。"
    "若資料不足，直接說明缺少哪些資訊。不得把案件資料描述成法規或正式規範。"
)


def _mock_reply(question: str) -> str:
    normalized = question.strip().lower()
    if any(word in normalized for word in ("你好", "您好", "嗨", "哈囉", "hello", "hi")):
        return "你好。可以直接輸入問題；需要案件資料或正式依據時，系統會自動查詢可用來源。"
    if any(word in normalized for word in ("謝謝", "感謝", "多謝")):
        return "不客氣。"
    if "你能做什麼" in normalized or "可以做什麼" in normalized:
        return "我可以協助一般問答，並在問題涉及目前案件或正式知識來源時自動查詢相關資料。"
    return "我可以協助處理這個問題；若內容涉及案件事實或正式規範，系統會改用可核對的資料來源回答。"


async def answer_general_chat(
    question: str,
    *,
    conversation_history: list[dict[str, str]] | None = None,
) -> tuple[str, str | None]:
    settings = get_settings()
    provider_name = settings.ai_provider.upper()
    history = (conversation_history or [])[-8:]

    if provider_name == "OLLAMA":
        provider = OllamaChatProvider(
            settings,
            [],
            system_prompt=GENERAL_ASSISTANT_SYSTEM_PROMPT,
        )
        messages: list[dict[str, Any]] = [
            {"role": item["role"], "content": item["content"]}
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        messages.append({"role": "user", "content": question})
        response = await provider.converse(messages)
        return response.text.strip() or _mock_reply(question), settings.ollama_model

    if provider_name == "BEDROCK":
        provider = BedrockConverseProvider(
            settings,
            [],
            system_prompt=GENERAL_ASSISTANT_SYSTEM_PROMPT,
        )
        messages = [
            {
                "role": item["role"],
                "content": [{"text": item["content"]}],
            }
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        messages.append({"role": "user", "content": [{"text": question}]})
        response = await provider.converse(messages)
        return response.text.strip() or _mock_reply(question), settings.bedrock_model_id

    return _mock_reply(question), "mock-assistant-router-v1"


def _case_fallback_reply(question: str, context: dict[str, Any]) -> str:
    case = context.get("case") if isinstance(context.get("case"), dict) else {}
    review = context.get("latest_review") if isinstance(context.get("latest_review"), dict) else {}
    selected = context.get("selected_finding") if isinstance(context.get("selected_finding"), dict) else {}
    normalized = question.strip().lower()

    if selected:
        title = str(selected.get("title") or "目前疑點")
        severity = str(selected.get("severity") or "風險等級未提供")
        status = str(selected.get("status") or "狀態未提供")
        description = str(selected.get("description") or "目前沒有更多說明。")
        return f"目前選取的疑點「{title}」風險等級為 {severity}，狀態為 {status}。{description}"

    missing_items = review.get("missing_items") if isinstance(review.get("missing_items"), list) else []
    if any(term in normalized for term in ("缺件", "缺少", "待補", "還缺")):
        open_items = [
            str(item.get("item_name") or item.get("item_code") or "未命名缺件")
            for item in missing_items
            if isinstance(item, dict) and str(item.get("status") or "OPEN") == "OPEN"
        ]
        return (
            "目前案件仍待補：" + "、".join(open_items) + "。"
            if open_items
            else "目前可讀的案件資料中沒有尚未完成的缺件。"
        )

    findings = review.get("findings") if isinstance(review.get("findings"), list) else []
    if any(term in normalized for term in ("風險", "疑點", "問題", "最高")) and findings:
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        highest = max(
            (item for item in findings if isinstance(item, dict)),
            key=lambda item: severity_order.get(str(item.get("severity") or "").upper(), 0),
            default=None,
        )
        if highest:
            return (
                f"目前最高風險疑點為「{highest.get('title') or highest.get('finding_code') or '未命名疑點'}」，"
                f"風險等級為 {highest.get('severity') or '未提供'}。"
                f"{highest.get('description') or ''}"
            )

    case_no = str(case.get("case_no") or "目前案件")
    case_title = str(case.get("case_title") or "")
    case_status = str(case.get("case_status") or "狀態未提供")
    review_status = str(review.get("review_status") or "")
    risk = str(review.get("overall_risk_level") or "")
    parts = [f"案件 {case_no}{f'（{case_title}）' if case_title else ''}目前狀態為 {case_status}。"]
    if review_status:
        parts.append(f"最新審查狀態為 {review_status}。")
    if risk:
        parts.append(f"整體風險等級為 {risk}。")
    return "".join(parts)


async def answer_structured_case_chat(
    question: str,
    *,
    case_context: dict[str, Any],
    review_id: str | None = None,
    finding_id: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> tuple[str, str | None]:
    """Explain permission-checked structured case data without treating it as law."""

    scoped_context = dict(case_context)
    latest_review = scoped_context.get("latest_review")
    if isinstance(latest_review, dict):
        if review_id and str(latest_review.get("review_id") or "") != review_id:
            scoped_context["latest_review"] = None
        elif finding_id:
            findings = latest_review.get("findings") if isinstance(latest_review.get("findings"), list) else []
            selected = next(
                (
                    item
                    for item in findings
                    if isinstance(item, dict) and str(item.get("finding_id") or "") == finding_id
                ),
                None,
            )
            scoped_context["selected_finding"] = selected

    fallback = _case_fallback_reply(question, scoped_context)
    settings = get_settings()
    provider_name = settings.ai_provider.upper()
    history = (conversation_history or [])[-6:]
    context_json = json.dumps(scoped_context, ensure_ascii=False, default=str)
    prompt = f"系統案件資料：\n{context_json}\n\n使用者問題：{question}"

    if provider_name == "OLLAMA":
        provider = OllamaChatProvider(settings, [], system_prompt=CASE_ASSISTANT_SYSTEM_PROMPT)
        messages: list[dict[str, Any]] = [
            {"role": item["role"], "content": item["content"]}
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        messages.append({"role": "user", "content": prompt})
        response = await provider.converse(messages)
        return response.text.strip() or fallback, settings.ollama_model

    if provider_name == "BEDROCK":
        provider = BedrockConverseProvider(settings, [], system_prompt=CASE_ASSISTANT_SYSTEM_PROMPT)
        messages = [
            {"role": item["role"], "content": [{"text": item["content"]}]}
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        messages.append({"role": "user", "content": [{"text": prompt}]})
        response = await provider.converse(messages)
        return response.text.strip() or fallback, settings.bedrock_model_id

    return fallback, "mock-assistant-router-v1"


__all__ = ["answer_general_chat", "answer_structured_case_chat"]