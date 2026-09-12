from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.knowledge.schemas import KnowledgeAnswerStatus, KnowledgeUnreadableSource
from app.valuation.facilities.schemas import NearestFacilityRequest


class AssistantSessionCreate(BaseModel):
    case_id: UUID
    form_instance_id: UUID
    selected_form_type: str = Field(default="F03", pattern="^F03$")


class AssistantSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assistant_session_id: UUID
    case_id: UUID
    user_id: UUID
    form_instance_id: UUID | None
    current_step: str
    selected_form_type: str
    missing_fields: list[str]
    missing_documents: list[str]
    last_tool_name: str | None
    last_tool_status: str | None
    provider: str
    model_id: str
    prompt_version: str
    session_status: str
    created_at: datetime
    updated_at: datetime


class AssistantProgressResponse(BaseModel):
    assistant_session_id: UUID
    current_step: str
    missing_fields: list[str]
    missing_documents: list[str]
    confirmed_candidate_count: int
    pending_candidate_count: int
    completed_items: int
    total_items: int


class AssistantQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=2000)
    as_of_date: date | None = None
    document_types: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=5, ge=1, le=10)


class AssistantClaim(BaseModel):
    text: str
    citation_ids: list[UUID] = Field(min_length=1)


class AssistantCitation(BaseModel):
    citation_id: UUID
    document_id: UUID
    document_title: str
    document_code: str
    version_no: int
    effective_from: date | None
    effective_to: date | None
    page_start: int | None
    page_end: int | None
    section_title: str | None
    article_no: str | None
    quoted_text: str
    supporting_quote: str | None = None
    supported_claim: str | None = None


class AssistantQuestionResponse(BaseModel):
    assistant_session_id: UUID
    answer_status: KnowledgeAnswerStatus
    answer: str
    generation_mode: str
    next_action: str
    clarification_question: str | None = None
    claims: list[AssistantClaim] = Field(default_factory=list)
    citations: list[AssistantCitation] = Field(default_factory=list)
    unreadable_sources: list[KnowledgeUnreadableSource] = Field(default_factory=list)


class AssistantMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    confirmed_fields: dict[str, Any] = Field(default_factory=dict)
    confirmed_candidate_ids: list[UUID] = Field(default_factory=list, max_length=100)
    confirm_apply: bool = False
    run_calculation: bool = False
    run_validation: bool = False
    generate_report_pdf: bool = False
    nearest_facility: NearestFacilityRequest | None = None
    confirm_action: bool = False

    @model_validator(mode="after")
    def validate_confirmations(self):
        if len(self.confirmed_fields) > 30:
            raise ValueError("單次最多確認 30 個欄位")
        if len(set(self.confirmed_candidate_ids)) != len(
            self.confirmed_candidate_ids
        ):
            raise ValueError("同一筆辨識結果不能重複選取")
        if self.nearest_facility is not None and not self.confirm_action:
            raise ValueError("請先確認步行距離查詢條件")
        return self


class ToolExecutionResponse(BaseModel):
    tool_name: str
    status: str
    result: dict[str, Any]


class AssistantMessageResponse(BaseModel):
    session: AssistantSessionResponse
    reply: str
    progress: AssistantProgressResponse
    tools: list[ToolExecutionResponse]


class AssistantHistoryMessageResponse(BaseModel):
    assistant_message_id: UUID
    message_no: int
    role: str
    content: str
    response_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
