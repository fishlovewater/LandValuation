from __future__ import annotations

import logging

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
from app.storage.service import StorageService

logger = logging.getLogger(__name__)


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
        or virtual_document_from_object(settings.minio_bucket, object_info)
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


async def answer_knowledge_question(
    *,
    session: AsyncSession,
    storage: StorageService,
    user: User,
    request: KnowledgeSearchRequest,
) -> KnowledgeAnswerResponse:
    """Answer a knowledge question using only authorized, cited sources."""

    try:
        case_context = (
            await load_authorized_case_context(session, user, request.case_id)
            if request.case_id is not None
            else None
        )
        candidates, unreadable_sources = await _retrieval_candidates(
            session=session,
            storage=storage,
            payload=request,
        )
        settings = get_settings()
        safety = KnowledgeSafetyService()
        if not candidates and unreadable_sources:
            return safety.unreadable_answer(unreadable_sources).model_copy(
                update={"case_context": case_context}
            )
        # /search is intentionally a broad candidate view.  /ask must send the
        # provider only the most relevant candidates so an unrelated same-document
        # page cannot be selected merely because it shares common legal keywords.
        ranked_candidates = safety.rank(
            request,
            candidates,
            limit=max(request.limit * 4, 12),
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
        answer = await provider.answer(
            question=request.question,
            candidates=ranked_candidates,
        )
        return safety.ai_answer_response(
            answer,
            ranked_candidates,
            provider_name=provider.provider_name,
            model_id=provider.model_id,
            unreadable_sources=unreadable_sources,
        ).model_copy(update={"case_context": case_context})
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
            "知識 AI 處理問答時失敗，結果未被採用。",
            502,
            details=details,
        ) from exc


__all__ = ["answer_knowledge_question"]
