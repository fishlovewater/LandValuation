from __future__ import annotations

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.knowledge.context_service import load_authorized_case_context
from app.knowledge.provider_factory import create_provider
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.runtime_extraction import (
    RuntimeKnowledgeExtractor,
    virtual_document_from_object,
)
from app.knowledge.schemas import KnowledgeAnswerResponse, KnowledgeSearchRequest
from app.knowledge.service import KnowledgeSafetyService, RetrievedKnowledge
from app.knowledge.source_policy import is_demo_reference
from app.storage.service import StorageService

logger = logging.getLogger(__name__)

_CONTEXT_REFERENCE_PATTERN = re.compile(
    r"(?:它|那一(?:條|項|段|個|份)|這一(?:條|項|段|個|份)|上述|前述|"
    r"前面(?:提到|說到|那個)|剛才|剛剛|前一(?:條|項|段)|"
    r"該(?:條|項|規定|文件|來源|內容)|這個|那個)"
)


async def _retrieval_candidates(
    *,
    session: AsyncSession,
    storage: StorageService,
    payload: KnowledgeSearchRequest,
) -> tuple[list[RetrievedKnowledge], list[object]]:
    repository = KnowledgeRepository(session)
    settings = get_settings()
    object_infos = await storage.list_objects(
        "knowledge/", limit=settings.knowledge_runtime_max_objects
    )
    metadata_by_key = await repository.documents_by_object_key()
    inventory = {
        object_info.object_name: metadata_by_key.get(object_info.object_name)
        or virtual_document_from_object(storage.bucket, object_info)
        for object_info in object_infos
        if not object_info.object_name.endswith("/")
    }
    persisted = await repository.retrieval_candidates(
        as_of_date=payload.as_of_date,
        document_types=payload.document_types,
    )
    persisted = [item for item in persisted if item.document.object_key in inventory]
    persisted_document_ids = {item.document.document_id for item in persisted}
    runtime_documents = [
        document
        for document in inventory.values()
        if document.document_id not in persisted_document_ids
        and _matches_request(document, payload)
    ]
    runtime_result = await RuntimeKnowledgeExtractor(storage).extract(runtime_documents)
    return [*persisted, *runtime_result.candidates], runtime_result.unreadable_sources


def _matches_request(document: object, payload: KnowledgeSearchRequest) -> bool:
    if payload.document_types and document.document_type not in payload.document_types:
        return False
    if payload.as_of_date:
        effective_from = getattr(document, "effective_from", None)
        effective_to = getattr(document, "effective_to", None)
        if effective_from is not None and effective_from > payload.as_of_date:
            return False
        if effective_to is not None and effective_to < payload.as_of_date:
            return False
    return True


def _contextual_question(
    question: str, conversation_history: list[dict[str, str]] | None
) -> str:
    if not conversation_history:
        return question
    # Conversation history is only a pronoun/reference resolver.  Appending it
    # to every standalone question pollutes lexical ranking with terms from old
    # answers (for example "文件／檢核／流程"), which can promote unrelated
    # source pages.  Keep complete questions self-contained and bring history
    # in only when the current wording actually points back to prior context.
    if not _CONTEXT_REFERENCE_PATTERN.search(question):
        return question
    recent = conversation_history[-8:]
    lines = [
        "以下是最近對話，只用來理解『它／那一條／前面提到的』等指涉；不得把舊回答當成事實來源："
    ]
    for item in recent:
        role = "使用者" if item.get("role") == "user" else "助理"
        content = " ".join(str(item.get("content") or "").split())[:1200]
        if content:
            lines.append(f"{role}：{content}")
    lines.append(f"目前問題：{question}")
    return "\n".join(lines)


async def answer_knowledge_question(
    *,
    session: AsyncSession,
    storage: StorageService,
    user: User,
    request: KnowledgeSearchRequest,
    conversation_history: list[dict[str, str]] | None = None,
) -> KnowledgeAnswerResponse:
    """Answer a knowledge question using only authorized, cited sources."""

    try:
        case_context = (
            await load_authorized_case_context(
                session,
                user,
                request.case_id,
                workspace=request.workspace,
            )
            if request.case_id is not None
            else None
        )
        candidates, unreadable_sources = await _retrieval_candidates(
            session=session,
            storage=storage,
            payload=request,
        )
        # Development fixtures may be useful when explaining the seeded demo
        # case, but they must never appear to be official law in a context-free
        # legal/knowledge question.
        if request.case_id is None:
            candidates = [
                item for item in candidates if not is_demo_reference(item.document)
            ]
        settings = get_settings()
        safety = KnowledgeSafetyService()
        if not candidates and unreadable_sources:
            return safety.unreadable_answer(unreadable_sources).model_copy(
                update={"case_context": case_context}
            )
        # /search is intentionally a broad candidate view. /ask keeps a wider
        # backend candidate pool so the provider can compare primary law/regulation
        # against manuals, then the provider itself narrows that pool before Qwen
        # sees it. This preserves source breadth without recreating the old prompt
        # overload problem.
        # For follow-up questions, recent conversation text is used only to resolve
        # references such as "that article"; it is never treated as evidence.
        contextual_question = _contextual_question(
            request.question, conversation_history
        )
        ranking_request = request.model_copy(
            update={"question": contextual_question}
        )
        ranked_candidates = safety.rank(
            ranking_request,
            candidates,
            limit=max(request.limit * 4, 20),
        )
        if not ranked_candidates:
            return safety.evidence_only_answer(
                request, [], unreadable_sources
            ).model_copy(update={"case_context": case_context})
        if settings.knowledge_answer_provider.lower() == "evidence_only":
            return safety.evidence_only_answer(
                request, ranked_candidates, unreadable_sources
            ).model_copy(update={"case_context": case_context})
        provider = create_provider(settings)
        try:
            answer = await provider.answer(
                question=contextual_question,
                candidates=ranked_candidates,
            )
            return safety.ai_answer_response(
                answer,
                ranked_candidates,
                provider_name=provider.provider_name,
                model_id=provider.model_id,
                unreadable_sources=unreadable_sources,
            ).model_copy(update={"case_context": case_context})
        except AppError as exc:
            # Local models are allowed to fail closed into deterministic source
            # review when their generated JSON/citation contract is invalid.
            # The invalid model output is never returned or persisted.  Real
            # provider availability failures (503), authorization failures, and
            # every non-Ollama provider error remain visible to the caller.
            if provider.provider_name == "ollama" and exc.code == "AI_PROVIDER_INVALID_RESPONSE":
                logger.warning(
                    "Ollama knowledge answer failed source contract; falling back to evidence-only: %s",
                    exc.details,
                    extra={"error_code": exc.code},
                )
                return safety.evidence_only_answer(
                    request,
                    ranked_candidates,
                    unreadable_sources,
                ).model_copy(update={"case_context": case_context})
            raise
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Knowledge AI /ask failed", exc_info=exc)
        # This handler is intentionally local to the development-only knowledge
        # endpoint. It turns unknown provider/extraction exceptions into a
        # diagnosable API failure without weakening global production errors.
        details = None
        settings = get_settings()
        if settings.app_env.lower() in {"development", "test"}:
            details = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }
        raise AppError(
            "KNOWLEDGE_ASK_PROCESSING_ERROR",
            "智能助理目前無法完成這次查詢，請稍後再試。",
            502,
            details=details,
        ) from exc


__all__ = ["answer_knowledge_question"]
