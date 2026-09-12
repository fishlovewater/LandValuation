from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.valuation.schemas import FormCode, RequestModel


class ExtractionStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExtractedFieldStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


class ExtractedFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    extracted_field_id: UUID
    extraction_id: UUID
    document_id: UUID
    form_code: str
    field_name: str
    field_label: str = ""
    field_guidance: str = ""
    extracted_value: Any
    confidence: Decimal
    source_page: int | None
    source_text: str | None
    analysis_provider: str
    model_id: str | None
    prompt_version: str | None
    field_status: ExtractedFieldStatus
    confirmed_value: Any | None
    confirmed_by_user_id: UUID | None
    confirmed_at: datetime | None
    applied_form_instance_id: UUID | None
    applied_at: datetime | None


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    extraction_id: UUID
    case_id: UUID
    document_id: UUID
    provider: str
    extraction_status: ExtractionStatus
    page_count: int | None
    extracted_text: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    candidates: list[ExtractedFieldResponse] = Field(default_factory=list)


class CandidateDecision(StrEnum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"


class CandidateConfirmation(BaseModel):
    extracted_field_id: UUID
    decision: CandidateDecision
    corrected_value: Any | None = None

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision == CandidateDecision.REJECT and self.corrected_value is not None:
            raise ValueError("拒絕候選欄位時不可提供 corrected_value")
        return self


class ExtractionConfirmRequest(BaseModel):
    confirmations: list[CandidateConfirmation] = Field(min_length=1, max_length=100)


class FieldAnalysisRequest(RequestModel):
    form_code: FormCode


class CodexCandidateInput(RequestModel):
    field_name: str = Field(min_length=1, max_length=100)
    extracted_value: str = Field(min_length=1, max_length=500)
    confidence: Decimal = Field(ge=0, le=1)
    source_text: str = Field(min_length=1, max_length=2000)


class CodexCandidateImportRequest(RequestModel):
    form_code: FormCode
    model_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    )
    candidates: list[CodexCandidateInput] = Field(default_factory=list, max_length=100)


class CodexAnalysisPackageResponse(BaseModel):
    form_code: FormCode
    prompt_version: str
    prompt: str
    output_schema: dict[str, Any]
