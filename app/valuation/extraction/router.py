from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.storage.dependencies import Storage
from app.valuation.extraction.field_analysis import FieldAnalysisService
from app.valuation.extraction.schemas import (
    CodexAnalysisPackageResponse,
    CodexCandidateImportRequest,
    ExtractedFieldResponse,
    ExtractionConfirmRequest,
    ExtractionResponse,
    FieldAnalysisRequest,
)
from app.valuation.extraction.service import ExtractionService

router = APIRouter()

ExtractionReader = Annotated[User, Depends(require_permissions("valuation.read"))]
ExtractionEditor = Annotated[User, Depends(require_permissions("valuation.update"))]


def response_model(record, candidates) -> ExtractionResponse:
    result = ExtractionResponse.model_validate(record)
    result.candidates = [
        ExtractedFieldResponse.model_validate(candidate) for candidate in candidates
    ]
    return result


@router.post(
    "/cases/{case_id}/documents/{document_id}/extract",
    response_model=ExtractionResponse,
)
async def start_document_extraction(
    case_id: UUID,
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user: ExtractionEditor,
) -> ExtractionResponse:
    record, candidates = await ExtractionService(session, storage).start(
        case_id, document_id, user
    )
    return response_model(record, candidates)


@router.get(
    "/cases/{case_id}/documents/{document_id}/extraction",
    response_model=ExtractionResponse,
)
async def get_document_extraction(
    case_id: UUID,
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user: ExtractionReader,
) -> ExtractionResponse:
    record, candidates = await ExtractionService(session, storage).get_latest(
        case_id, document_id, user
    )
    return response_model(record, candidates)


@router.post(
    "/cases/{case_id}/documents/{document_id}/extraction/analyze-fields",
    response_model=ExtractionResponse,
)
async def analyze_document_fields(
    case_id: UUID,
    document_id: UUID,
    payload: FieldAnalysisRequest,
    session: DbSession,
    user: ExtractionEditor,
) -> ExtractionResponse:
    record, candidates = await FieldAnalysisService(session).analyze(
        case_id,
        document_id,
        payload,
        user,
    )
    return response_model(record, candidates)


@router.post(
    "/cases/{case_id}/documents/{document_id}/extraction/codex-package",
    response_model=CodexAnalysisPackageResponse,
)
async def prepare_codex_analysis_package(
    case_id: UUID,
    document_id: UUID,
    payload: FieldAnalysisRequest,
    session: DbSession,
    user: ExtractionEditor,
) -> CodexAnalysisPackageResponse:
    return await FieldAnalysisService(session).prepare_codex_package(
        case_id,
        document_id,
        payload,
        user,
    )


@router.post(
    "/cases/{case_id}/documents/{document_id}/extraction/import-codex-candidates",
    response_model=ExtractionResponse,
)
async def import_codex_analysis_candidates(
    case_id: UUID,
    document_id: UUID,
    payload: CodexCandidateImportRequest,
    session: DbSession,
    user: ExtractionEditor,
) -> ExtractionResponse:
    record, candidates = await FieldAnalysisService(session).import_codex_candidates(
        case_id,
        document_id,
        payload,
        user,
    )
    return response_model(record, candidates)


@router.post(
    "/cases/{case_id}/documents/{document_id}/extraction/confirm",
    response_model=ExtractionResponse,
)
async def confirm_document_extraction(
    case_id: UUID,
    document_id: UUID,
    payload: ExtractionConfirmRequest,
    session: DbSession,
    storage: Storage,
    user: ExtractionEditor,
) -> ExtractionResponse:
    record, candidates = await ExtractionService(session, storage).confirm(
        case_id, document_id, payload, user
    )
    return response_model(record, candidates)
