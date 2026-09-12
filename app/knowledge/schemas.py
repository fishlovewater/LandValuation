from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeAnswerStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    NO_RELEVANT_SOURCE = "NO_RELEVANT_SOURCE"
    CASE_CONTEXT_NOT_AVAILABLE = "CASE_CONTEXT_NOT_AVAILABLE"


class KnowledgeRetrievalStatus(StrEnum):
    """Status for /search only; it is not an AI answer-quality decision."""

    CANDIDATES_FOUND = "CANDIDATES_FOUND"
    NO_RELEVANT_SOURCE = "NO_RELEVANT_SOURCE"


class KnowledgeSearchRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    case_id: UUID | None = None
    review_id: UUID | None = None
    finding_id: UUID | None = None
    workspace: str | None = Field(default=None, max_length=30)
    as_of_date: date | None = None
    document_types: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=5, ge=1, le=10)


class KnowledgeCitation(BaseModel):
    document_id: UUID
    document_title: str
    document_code: str
    version_no: int
    effective_from: date | None
    effective_to: date | None
    chunk_id: UUID
    page_start: int | None
    page_end: int | None
    section_title: str | None
    article_no: str | None
    quoted_text: str
    supporting_quote: str | None = None
    supported_claim: str | None = None


class KnowledgeUnreadableSource(BaseModel):
    document_id: UUID
    document_title: str
    original_filename: str
    reason: str


class KnowledgeSourceResponse(BaseModel):
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    unreadable_sources: list[KnowledgeUnreadableSource] = Field(default_factory=list)


class KnowledgeSearchResponse(KnowledgeSourceResponse):
    """Candidate retrieval result.  It never asserts that an answer is correct."""

    retrieval_status: KnowledgeRetrievalStatus
    retrieval_notice: str


class KnowledgeAnswerResponse(KnowledgeSourceResponse):
    """A provider answer that has passed source and evidence-contract validation."""

    answer_status: KnowledgeAnswerStatus
    answer: str
    answer_route: str = "KNOWLEDGE"
    generation_mode: str
    next_action: str
    model_id: str | None = None
    clarification_question: str | None = None
    # Case data is returned as structured, permission-checked context.  It is
    # intentionally separate from citations, which always refer to MinIO
    # knowledge sources and therefore remain independently verifiable.
    case_context: CaseAssistantContextResponse | None = None


class KnowledgeSourceDownloadResponse(BaseModel):
    """A short-lived URL for a source already authorized by the API."""

    document_id: UUID
    document_title: str
    original_filename: str
    expires_in_seconds: int
    download_url: str


class CaseBrief(BaseModel):
    case_id: UUID
    case_no: str
    case_title: str
    case_type: str
    case_status: str
    valuation_base_date: date
    city_code: str
    district_code: str
    land_use_type: str | None = None
    updated_at: datetime


class ReviewFindingSummary(BaseModel):
    finding_id: UUID
    finding_code: str
    finding_type: str
    severity: str
    title: str
    description: str
    status: str
    created_at: datetime


class MissingItemSummary(BaseModel):
    missing_item_id: UUID
    item_code: str
    item_name: str
    document_type: str | None = None
    severity: str
    status: str
    details: str | None = None


class ReviewResultSummary(BaseModel):
    review_id: UUID
    review_type: str
    review_status: str
    started_at: datetime
    completed_at: datetime | None = None
    overall_risk_level: str | None = None
    risk_score: float | None = None
    summary: str | None = None
    category_scores: dict = Field(default_factory=dict)
    findings: list[ReviewFindingSummary] = Field(default_factory=list)
    missing_items: list[MissingItemSummary] = Field(default_factory=list)


class CaseAssistantContextResponse(BaseModel):
    """Read-only data contract for a future case-aware front-end assistant."""

    case: CaseBrief
    review_access: bool
    review_access_note: str
    latest_review: ReviewResultSummary | None = None


class KnowledgeProviderStatusResponse(BaseModel):
    provider: str
    configured: bool
    runtime_available: bool
    model_id: str | None = None
    note: str


class KnowledgeConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    case_id: UUID | None = None
    review_id: UUID | None = None
    finding_id: UUID | None = None
    workspace: str | None = Field(default=None, max_length=30)


class KnowledgeConversationResponse(BaseModel):
    conversation_id: UUID
    case_id: UUID | None = None
    review_id: UUID | None = None
    finding_id: UUID | None = None
    workspace: str | None = None
    title: str
    provider: str
    model_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeConversationMessageResponse(BaseModel):
    message_id: UUID
    message_no: int
    role: str
    content: str
    answer: KnowledgeAnswerResponse | None = None
    created_at: datetime


KnowledgeAnswerResponse.model_rebuild()
