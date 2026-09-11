from typing import Annotated

from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, DbSession, require_permissions
from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError, ResourceNotFoundError, StorageError
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
def get_storage_service() -> StorageService:
    return StorageService(get_minio_client())


KnowledgeStorage = Annotated[StorageService, Depends(get_storage_service)]


def _reject_case_context(case_id) -> None:
    if case_id is not None:
        raise AppError(
            "CASE_CONTEXT_INTEGRATION_PENDING",
            "案件情境檢索尚未完成權限與 Valuation 唯讀整合，暫不可傳入 case_id。",
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
        raise StorageError("知識文件的 bucket 設定不符合目前系統設定")
    if not document.object_key.startswith("knowledge/"):
        raise StorageError("知識文件不在允許的 MinIO 前綴下")
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
