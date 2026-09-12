import json
from datetime import date
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.background import BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.core.exceptions import AppError
from app.storage.dependencies import Storage
from app.valuation.rule_packs.schemas import (
    ExistingKnowledgeRulePackCreateRequest,
    ExistingRulePackSourceLinkRequest,
    KnowledgeSourceOptionResponse,
    LandUseType,
    RuleCoverageMatrixResponse,
    RuleCoverageResponse,
    RulePackEffectiveDateUpdate,
    RulePackAIConfirmRequest,
    RulePackAIExtractionRequest,
    RulePackAIExtractionResponse,
    RulePackImportRequest,
    RulePackImportResponse,
    RulePackAuditResponse,
    RulePackManifest,
    RulePackPublishRequest,
    RulePackResponse,
    RulePackSourceManifest,
    RulePackSourceResponse,
)
from app.valuation.rule_packs.coverage_service import RuleCoverageService
from app.valuation.rule_packs.repository import RulePackRepository
from app.valuation.rule_packs.service import RulePackService

router = APIRouter()

RuleReader = Annotated[User, Depends(require_permissions("knowledge.read"))]
RuleEditor = Annotated[
    User,
    Depends(require_permissions("knowledge.read", "document.upload", "valuation.update")),
]
RuleDownloader = Annotated[
    User,
    Depends(require_permissions("knowledge.read", "document.download")),
]


@router.post(
    "/rule-packs/sources",
    response_model=RulePackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_rule_pack_source(
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
    manifest_json: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> RulePackResponse:
    try:
        manifest = RulePackManifest.model_validate(json.loads(manifest_json))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AppError("RULE_MANIFEST_INVALID", f"規則 manifest 格式錯誤：{exc}", 422) from exc
    return await RulePackService(session, storage).upload_source(manifest, file, user)


@router.post(
    "/rule-packs/from-knowledge-source",
    response_model=RulePackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_pack_from_existing_knowledge_source(
    payload: ExistingKnowledgeRulePackCreateRequest,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
) -> RulePackResponse:
    return await RulePackService(session, storage).create_from_existing_source(
        payload, user
    )


@router.post(
    "/rule-packs/{rule_version_id}/sources",
    response_model=RulePackSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_rule_pack_source(
    rule_version_id: UUID,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
    source_manifest_json: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> RulePackSourceResponse:
    try:
        manifest = RulePackSourceManifest.model_validate(
            json.loads(source_manifest_json)
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AppError(
            "RULE_SOURCE_MANIFEST_INVALID",
            f"規則來源 manifest 格式錯誤：{exc}",
            422,
        ) from exc
    return await RulePackService(session, storage).add_source(
        rule_version_id, manifest, file, user
    )


@router.get(
    "/rule-packs/{rule_version_id}/sources",
    response_model=list[RulePackSourceResponse],
)
async def list_rule_pack_sources(
    rule_version_id: UUID,
    session: DbSession,
    storage: Storage,
    user: RuleReader,
) -> list[RulePackSourceResponse]:
    del user
    return await RulePackService(session, storage).list_source_documents(
        rule_version_id
    )


@router.post(
    "/rule-packs/{rule_version_id}/source-links",
    response_model=RulePackSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_existing_rule_pack_source(
    rule_version_id: UUID,
    payload: ExistingRulePackSourceLinkRequest,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
) -> RulePackSourceResponse:
    return await RulePackService(session, storage).link_existing_source(
        rule_version_id, payload, user
    )


@router.patch(
    "/rule-packs/{rule_version_id}/effective-date",
    response_model=RulePackResponse,
)
async def confirm_rule_pack_effective_date(
    rule_version_id: UUID,
    payload: RulePackEffectiveDateUpdate,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
) -> RulePackResponse:
    del user
    return await RulePackService(session, storage).confirm_effective_date(
        rule_version_id, payload
    )


@router.get("/rule-packs", response_model=list[RulePackResponse])
async def list_rule_packs(
    session: DbSession, storage: Storage, user: RuleReader
) -> list[RulePackResponse]:
    del user
    return await RulePackService(session, storage).list()


@router.get(
    "/rule-packs/knowledge-sources",
    response_model=list[KnowledgeSourceOptionResponse],
)
async def list_available_rule_pack_knowledge_sources(
    session: DbSession,
    storage: Storage,
    user: RuleReader,
) -> list[KnowledgeSourceOptionResponse]:
    del user
    return await RulePackService(session, storage).list_available_knowledge_sources()


@router.get(
    "/rule-packs/coverage/check",
    response_model=RuleCoverageResponse,
)
async def check_rule_pack_coverage(
    district_code: str,
    land_use_type: LandUseType,
    valuation_date: date,
    session: DbSession,
    user: RuleReader,
) -> RuleCoverageResponse:
    del user
    return await RuleCoverageService(RulePackRepository(session)).check(
        district_code=district_code,
        land_use_type=land_use_type,
        valuation_date=valuation_date,
    )


@router.get(
    "/rule-packs/coverage/matrix",
    response_model=RuleCoverageMatrixResponse,
)
async def get_rule_pack_coverage_matrix(
    valuation_date: date,
    session: DbSession,
    user: RuleReader,
) -> RuleCoverageMatrixResponse:
    del user
    return await RuleCoverageService(RulePackRepository(session)).matrix(
        valuation_date
    )


@router.get("/rule-packs/{rule_version_id}", response_model=RulePackResponse)
async def get_rule_pack(
    rule_version_id: UUID,
    session: DbSession,
    storage: Storage,
    user: RuleReader,
) -> RulePackResponse:
    del user
    return await RulePackService(session, storage).get(rule_version_id)


@router.get(
    "/rule-packs/{rule_version_id}/formal-audit",
    response_model=RulePackAuditResponse,
    summary="稽核規則版本是否可供正式比較法計算",
)
async def audit_rule_pack(
    rule_version_id: UUID,
    session: DbSession,
    storage: Storage,
    user: RuleReader,
) -> RulePackAuditResponse:
    del user
    return await RulePackService(session, storage).formal_audit(rule_version_id)


@router.post(
    "/rule-packs/{rule_version_id}/import",
    response_model=RulePackImportResponse,
)
async def import_rule_pack(
    rule_version_id: UUID,
    payload: RulePackImportRequest,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
) -> RulePackImportResponse:
    del user
    return await RulePackService(session, storage).import_rules(rule_version_id, payload)


@router.post(
    "/rule-packs/{rule_version_id}/ai-extraction",
    response_model=RulePackAIExtractionResponse,
    summary="將規則來源轉成待人工確認的因素與級距候選",
)
async def extract_rule_pack_with_ai(
    rule_version_id: UUID,
    payload: RulePackAIExtractionRequest,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
) -> RulePackAIExtractionResponse:
    del user
    return await RulePackService(session, storage).ai_extract_rules(
        rule_version_id, payload
    )


@router.get(
    "/rule-packs/{rule_version_id}/ai-extraction",
    response_model=RulePackAIExtractionResponse,
    summary="取得尚待確認或已確認的 AI 規則候選",
)
async def get_rule_pack_ai_extraction(
    rule_version_id: UUID,
    session: DbSession,
    storage: Storage,
    user: RuleReader,
) -> RulePackAIExtractionResponse:
    del user
    return await RulePackService(session, storage).get_ai_extraction(rule_version_id)


@router.post(
    "/rule-packs/{rule_version_id}/ai-extraction/confirm",
    response_model=RulePackImportResponse,
    summary="人工修正並確認 AI 規則候選後正式匯入",
)
async def confirm_rule_pack_ai_extraction(
    rule_version_id: UUID,
    payload: RulePackAIConfirmRequest,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
) -> RulePackImportResponse:
    del user
    return await RulePackService(session, storage).confirm_ai_extraction(
        rule_version_id, payload
    )


@router.post(
    "/rule-packs/{rule_version_id}/publish",
    response_model=RulePackResponse,
)
async def publish_rule_pack(
    rule_version_id: UUID,
    payload: RulePackPublishRequest,
    session: DbSession,
    storage: Storage,
    user: RuleEditor,
) -> RulePackResponse:
    return await RulePackService(session, storage).publish(
        rule_version_id, payload.confirm_publish, user
    )


@router.get("/rule-packs/{rule_version_id}/source/download")
async def download_rule_pack_source(
    rule_version_id: UUID,
    background_tasks: BackgroundTasks,
    session: DbSession,
    storage: Storage,
    user: RuleDownloader,
):
    del user
    source = await RulePackService(session, storage).source_document(rule_version_id)
    response = await storage.download(source.object_key)

    def close_response() -> None:
        response.close()
        response.release_conn()

    background_tasks.add_task(close_response)
    encoded = quote(source.original_filename)
    return StreamingResponse(
        response.stream(64 * 1024),
        media_type=source.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        background=background_tasks,
    )


@router.get(
    "/rule-packs/{rule_version_id}/sources/{rule_version_source_id}/download"
)
async def download_rule_pack_source_by_id(
    rule_version_id: UUID,
    rule_version_source_id: UUID,
    background_tasks: BackgroundTasks,
    session: DbSession,
    storage: Storage,
    user: RuleDownloader,
):
    del user
    source = await RulePackService(session, storage).rule_source_document(
        rule_version_id, rule_version_source_id
    )
    response = await storage.download(source.object_key)

    def close_response() -> None:
        response.close()
        response.release_conn()

    background_tasks.add_task(close_response)
    encoded = quote(source.original_filename)
    return StreamingResponse(
        response.stream(64 * 1024),
        media_type=source.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        background=background_tasks,
    )
