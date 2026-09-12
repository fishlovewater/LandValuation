from typing import Annotated

from uuid import UUID

from fastapi import APIRouter, Depends

from app.ai_assistant.chat_service import answer_general_chat, answer_structured_case_chat
from app.ai_assistant.routing import AssistantAnswerRoute, route_assistant_question
from app.auth.dependencies import CurrentUser, DbSession, require_permissions
from app.auth.models import User
from app.auth.service import permission_codes
from app.core.config import get_settings
from app.core.exceptions import AppError, PermissionDeniedError, ResourceNotFoundError, StorageError
from app.knowledge.answer_service import (
    _retrieval_candidates,
    answer_knowledge_question,
)
from app.knowledge.context_service import load_authorized_case_context
from app.knowledge.provider_factory import create_provider
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.runtime_extraction import virtual_document_from_object
from app.knowledge.schemas import (
    CaseAssistantContextResponse,
    KnowledgeAnswerResponse,
    KnowledgeConversationCreate,
    KnowledgeConversationMessageResponse,
    KnowledgeConversationResponse,
    KnowledgeProviderStatusResponse,
    KnowledgeSourceDownloadResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.knowledge.service import KnowledgeSafetyService
from app.storage.client import get_minio_client
from app.storage.service import StorageService

router = APIRouter()

KnowledgeReader = Annotated[User, Depends(require_permissions("knowledge.read"))]
AssistantConversationUser = Annotated[User, Depends(require_permissions("assistant.use"))]

_ASSISTANT_WORKSPACES = frozenset({"valuation", "review"})


def get_storage_service() -> StorageService:
    return StorageService(get_minio_client())


KnowledgeStorage = Annotated[StorageService, Depends(get_storage_service)]


def _reject_case_context(case_id) -> None:
    if case_id is not None:
        raise AppError(
            "CASE_CONTEXT_INTEGRATION_PENDING",
            "目前無法使用案件資料篩選這項搜尋，請改用一般知識搜尋。",
            422,
        )


async def _source_document(document_id: UUID, repository: KnowledgeRepository, storage: StorageService):
    document = await repository.knowledge_document(document_id)
    if document is not None:
        return document
    settings = get_settings()
    for object_info in await storage.list_objects(
        "knowledge/", limit=settings.knowledge_runtime_max_objects
    ):
        if object_info.object_name.endswith("/"):
            continue
        virtual_document = virtual_document_from_object(settings.minio_bucket, object_info)
        if virtual_document.document_id == document_id:
            return virtual_document
    return None


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search(
    payload: KnowledgeSearchRequest,
    session: DbSession,
    _user: KnowledgeReader,
    storage: KnowledgeStorage,
) -> KnowledgeSearchResponse:
    _reject_case_context(payload.case_id)
    candidates, unreadable_sources = await _retrieval_candidates(
        session=session,
        storage=storage,
        payload=payload,
    )
    return KnowledgeSafetyService().search_response(payload, candidates, unreadable_sources)


@router.post("/ask", response_model=KnowledgeAnswerResponse)
async def ask(
    payload: KnowledgeSearchRequest,
    session: DbSession,
    user: KnowledgeReader,
    storage: KnowledgeStorage,
) -> KnowledgeAnswerResponse:
    return await answer_knowledge_question(
        session=session,
        storage=storage,
        user=user,
        request=payload,
    )


def _conversation_response(record) -> KnowledgeConversationResponse:
    return KnowledgeConversationResponse(
        conversation_id=record.conversation_id,
        case_id=record.case_id,
        review_id=record.review_id,
        finding_id=record.finding_id,
        workspace=record.workspace,
        title=record.title,
        provider=record.provider,
        model_id=record.model_id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _require_knowledge_access(user: User) -> None:
    if "knowledge.read" not in permission_codes(user):
        raise PermissionDeniedError("沒有查看法規知識的權限")


def _normalize_workspace(workspace: str | None) -> str | None:
    normalized = (workspace or "").strip().lower() or None
    if normalized is not None and normalized not in _ASSISTANT_WORKSPACES:
        raise AppError(
            "ASSISTANT_CONTEXT_INVALID",
            "AI 助手工作區僅支援估價或審查情境。",
            422,
        )
    return normalized


def _assert_conversation_context_matches(record, payload: KnowledgeSearchRequest) -> None:
    for field in ("case_id", "review_id", "finding_id"):
        requested = getattr(payload, field)
        if requested is not None and requested != getattr(record, field):
            raise AppError(
                "ASSISTANT_CONTEXT_CONFLICT",
                "目前對話綁定的案件情境與這次要求不一致，請開啟新的對話。",
                409,
            )
    requested_workspace = _normalize_workspace(payload.workspace)
    if requested_workspace is not None and requested_workspace != _normalize_workspace(record.workspace):
        raise AppError(
            "ASSISTANT_CONTEXT_CONFLICT",
            "目前對話綁定的工作區與這次要求不一致，請開啟新的對話。",
            409,
        )


def _validate_case_subcontext(
    context: CaseAssistantContextResponse,
    *,
    review_id: UUID | None,
    finding_id: UUID | None,
) -> None:
    if review_id is None and finding_id is None:
        return
    if not context.review_access:
        raise PermissionDeniedError("目前帳號沒有查看審查資料的權限")
    review = context.latest_review
    if review is None:
        raise ResourceNotFoundError("審查資料")
    if review_id is not None and review.review_id != review_id:
        raise ResourceNotFoundError("審查案件")
    if finding_id is not None and all(item.finding_id != finding_id for item in review.findings):
        raise ResourceNotFoundError("審查疑點")


def _previous_answer_route(records) -> AssistantAnswerRoute | None:
    for record in reversed(records):
        if record.role != "ASSISTANT" or not isinstance(record.response_payload, dict):
            continue
        raw = record.response_payload.get("answer_route")
        try:
            return AssistantAnswerRoute(raw)
        except (TypeError, ValueError):
            continue
    return None


def _conversation_message_response(record) -> KnowledgeConversationMessageResponse:
    answer = None
    if record.role == "ASSISTANT" and record.response_payload:
        answer = KnowledgeAnswerResponse.model_validate(record.response_payload)
    return KnowledgeConversationMessageResponse(
        message_id=record.message_id,
        message_no=record.message_no,
        role=record.role,
        content=record.content,
        answer=answer,
        created_at=record.created_at,
    )


@router.post("/conversations", response_model=KnowledgeConversationResponse, status_code=201)
async def create_conversation(
    payload: KnowledgeConversationCreate,
    session: DbSession,
    user: AssistantConversationUser,
) -> KnowledgeConversationResponse:
    if (payload.review_id is not None or payload.finding_id is not None) and payload.case_id is None:
        raise AppError(
            "ASSISTANT_CONTEXT_INVALID",
            "審查或疑點情境必須同時包含案件識別資料。",
            422,
        )
    if payload.case_id is not None:
        context = await load_authorized_case_context(session, user, payload.case_id)
        _validate_case_subcontext(
            context,
            review_id=payload.review_id,
            finding_id=payload.finding_id,
        )
    settings = get_settings()
    provider_name = settings.knowledge_answer_provider.lower()
    model_id = None
    if provider_name != "evidence_only":
        model_id = create_provider(settings).model_id
    record = await KnowledgeRepository(session).create_conversation(
        user_id=user.user_id,
        provider=provider_name,
        model_id=model_id,
        title=(payload.title or "新對話").strip() or "新對話",
        case_id=payload.case_id,
        review_id=payload.review_id,
        finding_id=payload.finding_id,
        workspace=_normalize_workspace(payload.workspace),
    )
    return _conversation_response(record)


@router.get("/conversations", response_model=list[KnowledgeConversationResponse])
async def list_conversations(
    session: DbSession,
    user: AssistantConversationUser,
) -> list[KnowledgeConversationResponse]:
    records = await KnowledgeRepository(session).list_conversations(user.user_id)
    return [_conversation_response(record) for record in records]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[KnowledgeConversationMessageResponse],
)
async def conversation_messages(
    conversation_id: UUID,
    session: DbSession,
    user: AssistantConversationUser,
) -> list[KnowledgeConversationMessageResponse]:
    repository = KnowledgeRepository(session)
    conversation = await repository.get_conversation(conversation_id, user.user_id)
    if conversation is None:
        raise ResourceNotFoundError("AI 助手對話")
    records = await repository.list_conversation_messages(conversation_id)
    return [_conversation_message_response(record) for record in records]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=KnowledgeAnswerResponse,
)
async def ask_conversation(
    conversation_id: UUID,
    payload: KnowledgeSearchRequest,
    session: DbSession,
    user: AssistantConversationUser,
    storage: KnowledgeStorage,
) -> KnowledgeAnswerResponse:
    repository = KnowledgeRepository(session)
    conversation = await repository.get_conversation(conversation_id, user.user_id)
    if conversation is None:
        raise ResourceNotFoundError("AI 助手對話")

    _assert_conversation_context_matches(conversation, payload)
    case_id = conversation.case_id
    review_id = conversation.review_id
    finding_id = conversation.finding_id
    workspace = _normalize_workspace(conversation.workspace)
    if (review_id is not None or finding_id is not None) and case_id is None:
        raise AppError(
            "ASSISTANT_CONTEXT_INVALID",
            "審查或疑點情境必須同時包含案件識別資料。",
            422,
        )

    case_context = None
    if case_id is not None:
        case_context = await load_authorized_case_context(session, user, case_id)
        _validate_case_subcontext(
            case_context,
            review_id=review_id,
            finding_id=finding_id,
        )
    existing = await repository.list_conversation_messages(conversation_id, limit=20)
    history = [
        {
            "role": "user" if item.role == "USER" else "assistant",
            "content": item.content,
        }
        for item in existing
        if item.role in {"USER", "ASSISTANT"}
    ]
    await repository.add_conversation_message(
        conversation,
        role="USER",
        content=payload.question,
    )
    await repository.rename_conversation_if_new(conversation, payload.question)
    route = route_assistant_question(
        payload.question,
        has_case_context=case_id is not None,
        previous_route=_previous_answer_route(existing),
    )
    if route == AssistantAnswerRoute.CHAT:
        answer, model_id = await answer_general_chat(
            payload.question,
            conversation_history=history,
        )
        result = KnowledgeAnswerResponse(
            answer_status="SUPPORTED",
            answer=answer,
            answer_route=route.value,
            generation_mode="CHAT",
            next_action="CONTINUE_CONVERSATION",
            model_id=model_id,
        )
    elif route == AssistantAnswerRoute.CASE:
        if case_context is None:
            raise AppError(
                "CASE_CONTEXT_NOT_AVAILABLE",
                "目前頁面沒有可供查詢的案件資料。",
                422,
            )
        answer, model_id = await answer_structured_case_chat(
            payload.question,
            case_context=case_context.model_dump(mode="json"),
            review_id=str(review_id) if review_id else None,
            finding_id=str(finding_id) if finding_id else None,
            conversation_history=history,
        )
        result = KnowledgeAnswerResponse(
            answer_status="SUPPORTED",
            answer=answer,
            answer_route=route.value,
            generation_mode="STRUCTURED_CASE_DATA",
            next_action="CONTINUE_CONVERSATION",
            model_id=model_id,
            case_context=case_context,
        )
    elif route == AssistantAnswerRoute.KNOWLEDGE:
        _require_knowledge_access(user)
        result = (
            await answer_knowledge_question(
                session=session,
                storage=storage,
                user=user,
                request=payload.model_copy(
                    update={
                        "case_id": None,
                        "review_id": None,
                        "finding_id": None,
                    }
                ),
                conversation_history=history,
            )
        ).model_copy(update={"answer_route": route.value})
    else:
        _require_knowledge_access(user)
        if case_context is None:
            raise AppError(
                "CASE_CONTEXT_NOT_AVAILABLE",
                "目前頁面沒有可供查詢的案件資料。",
                422,
            )
        case_answer, case_model_id = await answer_structured_case_chat(
            payload.question,
            case_context=case_context.model_dump(mode="json"),
            review_id=str(review_id) if review_id else None,
            finding_id=str(finding_id) if finding_id else None,
            conversation_history=history,
        )
        knowledge_result = await answer_knowledge_question(
            session=session,
            storage=storage,
            user=user,
            request=payload.model_copy(update={"case_id": case_id}),
            conversation_history=history,
        )
        if knowledge_result.answer_status.value == "SUPPORTED":
            result = knowledge_result.model_copy(
                update={
                    "answer": f"{case_answer}\n\n{knowledge_result.answer}",
                    "answer_route": route.value,
                    "case_context": case_context,
                    "model_id": knowledge_result.model_id or case_model_id,
                }
            )
        else:
            result = knowledge_result.model_copy(
                update={
                    "answer_route": route.value,
                    "case_context": case_context,
                }
            )
    await repository.add_conversation_message(
        conversation,
        role="ASSISTANT",
        content=result.answer,
        response_payload=result.model_dump(mode="json"),
    )
    return result


@router.get("/provider-status", response_model=KnowledgeProviderStatusResponse)
async def provider_status(_user: KnowledgeReader) -> KnowledgeProviderStatusResponse:
    settings = get_settings()
    provider = settings.knowledge_answer_provider.lower()
    if provider == "evidence_only":
        return KnowledgeProviderStatusResponse(
            provider=provider,
            configured=True,
            runtime_available=True,
            note="目前只顯示可核對來源，不會由 AI 整理答案。",
        )
    selected = create_provider(settings)
    if provider == "ollama":
        configured = selected.configured()
        return KnowledgeProviderStatusResponse(
            provider=provider,
            configured=configured,
            runtime_available=configured,
            model_id=selected.model_id,
            note=(
                "本機 AI 問答已設定完成。"
                if configured
                else "本機 AI 問答尚未完成設定。"
            ),
        )
    if provider == "bedrock":
        configured = selected.configured()
        return KnowledgeProviderStatusResponse(
            provider=provider,
            configured=configured,
            runtime_available=configured,
            model_id=selected.model_id,
            note=(
                "Bedrock 設定已提供；實際呼叫仍需執行主機具備 AWS 憑證與 bedrock:InvokeModel 權限。"
                if configured
                else "請設定 BEDROCK_REGION 與 BEDROCK_MODEL_ID。"
            ),
        )
    runtime_available = selected.executable_found()
    return KnowledgeProviderStatusResponse(
        provider=selected.provider_name,
        configured=True,
        runtime_available=runtime_available,
        model_id=selected.model_id,
        note=(
            "已找到 Codex CLI；實際問答仍需 API 執行主機具有網路與有效登入。"
            if runtime_available
            else "找不到 Codex CLI；Docker 容器需另行安裝，或改在 Windows 主機執行 API。"
        ),
    )


@router.get(
    "/sources/{document_id}/download",
    response_model=KnowledgeSourceDownloadResponse,
)
async def source_download(
    document_id: UUID,
    session: DbSession,
    _user: KnowledgeReader,
    storage: KnowledgeStorage,
) -> KnowledgeSourceDownloadResponse:
    """Create a short-lived MinIO URL only after source authorization."""

    document = await _source_document(document_id, KnowledgeRepository(session), storage)
    if document is None:
        raise ResourceNotFoundError("知識文件")
    settings = get_settings()
    if document.bucket_name != settings.minio_bucket:
        raise StorageError("此知識文件目前無法下載，請聯絡系統管理者。")
    if not document.object_key.startswith("knowledge/"):
        raise StorageError("此知識文件目前無法下載，請聯絡系統管理者。")
    return KnowledgeSourceDownloadResponse(
        document_id=document.document_id,
        document_title=document.title,
        original_filename=document.original_filename,
        expires_in_seconds=settings.minio_presigned_expiry_seconds,
        download_url=await storage.presigned_download_url(document.object_key),
    )


@router.get(
    "/cases/{case_id}/context",
    response_model=CaseAssistantContextResponse,
)
async def case_context(
    case_id: UUID,
    session: DbSession,
    user: KnowledgeReader,
) -> CaseAssistantContextResponse:
    """Read-only contract for a front end that needs case and review context."""

    return await load_authorized_case_context(session, user, case_id)
