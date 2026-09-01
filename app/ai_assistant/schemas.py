from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
            raise ValueError("confirmed_candidate_ids 不可重複")
        if self.nearest_facility is not None and not self.confirm_action:
            raise ValueError("步行距離查詢必須將 confirm_action 設為 true")
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
