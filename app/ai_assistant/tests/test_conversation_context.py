from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.knowledge.router import _assert_conversation_context_matches, _normalize_workspace
from app.knowledge.schemas import KnowledgeSearchRequest


def test_workspace_is_normalized_and_limited_to_known_assistant_workspaces():
    assert _normalize_workspace(None) is None
    assert _normalize_workspace(" Review ") == "review"
    assert _normalize_workspace("VALUATION") == "valuation"
    assert _normalize_workspace("History") == "history"

    with pytest.raises(AppError) as raised:
        _normalize_workspace("admin")

    assert raised.value.code == "ASSISTANT_CONTEXT_INVALID"
    assert raised.value.status_code == 422


def test_conversation_context_accepts_same_case_and_optional_null_subcontext():
    case_id = uuid4()
    record = SimpleNamespace(
        case_id=case_id,
        review_id=None,
        finding_id=None,
        workspace="valuation",
    )
    payload = KnowledgeSearchRequest(
        question="目前案件狀態",
        case_id=case_id,
        review_id=None,
        finding_id=None,
        workspace="valuation",
    )

    _assert_conversation_context_matches(record, payload)


def test_conversation_context_rejects_rebinding_to_another_case():
    record = SimpleNamespace(
        case_id=uuid4(),
        review_id=None,
        finding_id=None,
        workspace="valuation",
    )
    payload = KnowledgeSearchRequest(
        question="目前案件狀態",
        case_id=uuid4(),
        workspace="valuation",
    )

    with pytest.raises(AppError) as raised:
        _assert_conversation_context_matches(record, payload)

    assert raised.value.code == "ASSISTANT_CONTEXT_CONFLICT"
    assert raised.value.status_code == 409


def test_conversation_context_rejects_workspace_rebinding():
    case_id = uuid4()
    record = SimpleNamespace(
        case_id=case_id,
        review_id=None,
        finding_id=None,
        workspace="valuation",
    )
    payload = KnowledgeSearchRequest(
        question="目前案件狀態",
        case_id=case_id,
        workspace="review",
    )

    with pytest.raises(AppError) as raised:
        _assert_conversation_context_matches(record, payload)

    assert raised.value.code == "ASSISTANT_CONTEXT_CONFLICT"
    assert raised.value.status_code == 409
