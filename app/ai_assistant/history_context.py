from __future__ import annotations

from typing import Any

from app.history.schemas import HistorySearchParams
from app.history.service import HistoryService


def history_search_params_for_question(question: str) -> HistorySearchParams:
    normalized = " ".join(question.strip().split()).lower()
    result = "CORRECTION" if "補正" in normalized else None
    return HistorySearchParams(
        result=result,
        sort="updated_at",
        order="desc",
        limit=100,
    )


async def load_authorized_history_collection_context(
    session,
    user,
    question: str,
) -> dict[str, Any]:
    params = history_search_params_for_question(question)
    page = await HistoryService(session).search(params, user)
    cases = [item.model_dump(mode="json") for item in page.items]
    return {
        "scope": "authorized_case_collection",
        "filter": {
            "result": params.result,
            "sort": params.sort,
            "order": params.order,
        },
        "total": page.total,
        "returned_count": len(cases),
        "truncated": page.total > len(cases),
        "cases": cases,
        "permissions": page.permissions.model_dump(mode="json"),
    }


__all__ = [
    "history_search_params_for_question",
    "load_authorized_history_collection_context",
]