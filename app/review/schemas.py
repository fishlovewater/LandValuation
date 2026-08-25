from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ReviewStatus = Literal[
    "RECEIVED",
    "PREPROCESSING",
    "PENDING_MATERIALS",
    "READY_FOR_REVIEW",
    "ANALYZING",
    "REVIEW_REQUIRED",
    "RETURNED_FOR_REVISION",
    "SUPPLEMENT_REQUIRED",
    "EXPERT_REVIEW",
    "APPROVED",
    "REVIEW_COMPLETED",
]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class ReviewCreate(BaseModel):
    case_id: UUID
    received_at: datetime | None = None
    due_at: datetime | None = None

    @model_validator(mode="after")
    def validate_due_at(self):
        if self.received_at and self.due_at and self.due_at < self.received_at:
            raise ValueError("due_at 不得早於 received_at")
        return self


class ReviewUpdate(BaseModel):
    review_status: ReviewStatus


class ReviewAssign(BaseModel):
    reviewer_id: UUID


class ReviewPriority(BaseModel):
    priority: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason 不得為空白")
        return value


class ReviewListQuery(BaseModel):
    status: ReviewStatus | None = None
    assigned_reviewer_id: UUID | None = None
    risk_level: RiskLevel | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: UUID
    case_id: UUID
    review_type: str
    review_status: str
    started_by_user_id: UUID | None
    started_at: datetime
    completed_at: datetime | None
    received_at: datetime
    due_at: datetime | None
    assigned_reviewer_id: UUID | None
    manual_priority: int
    manual_priority_reason: str | None
    current_risk_level: str | None
    high_count: int
    medium_count: int
    low_count: int
    missing_item_count: int
    latest_validation_run_id: UUID | None


class ReviewList(BaseModel):
    items: list[ReviewRead]
    total: int
    limit: int
    offset: int


class MissingItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    missing_item_id: UUID
    review_id: UUID
    item_code: str
    item_name: str
    document_type: str | None
    severity: str
    status: str
    field_path: str | None
    reason: str | None
    affected_rule_codes: list[str]
    due_at: datetime | None
    notified_at: datetime | None
    notification_status: str | None
    created_at: datetime


class CompletenessResponse(BaseModel):
    ready: bool
    review_status: str
    missing_item_count: int
    blocked_rule_codes: list[str]
    items: list[MissingItemRead]


class SupplementRequest(BaseModel):
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("due_at 必須包含時區")
        return value


class AdjustmentRateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_rule_id: UUID
    finding_code: str = Field(min_length=1, max_length=100)
    reported_rate: Decimal
    reported_text: str
    field_path: str
    document_id: UUID
    document_version: int = Field(ge=1)
    page_number: int = Field(ge=1)


class ExpertGradeCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_rule_id: UUID
    finding_code: str = Field(min_length=1, max_length=100)
    reported_grade: str
    reported_text: str
    field_path: str
    document_id: UUID
    document_version: int = Field(ge=1)
    page_number: int = Field(ge=1)


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version_id: UUID
    adjustment_checks: list[AdjustmentRateCheck] = Field(default_factory=list)
    expert_checks: list[ExpertGradeCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_at_least_one_check(self):
        if not self.adjustment_checks and not self.expert_checks:
            raise ValueError("至少必須執行一項檢核")
        return self


class ValidationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    validation_run_id: UUID
    case_id: UUID
    review_id: UUID | None
    run_no: int | None
    run_status: str
    passed_count: int
    warning_count: int
    failed_count: int
    started_at: datetime
    completed_at: datetime | None
    triggered_by_user_id: UUID | None
    rule_version_id: UUID | None
    input_snapshot: dict
    model_id: str | None
    prompt_version: str | None
    error_code: str | None
    error_message: str | None


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_id: UUID
    review_id: UUID
    validation_run_id: UUID | None
    finding_code: str
    finding_type: str
    severity: str
    title: str
    description: str
    status: str
    document_id: UUID | None
    document_version: int | None
    page_number: int | None
    field_path: str | None
    source_evidence: list
    reported_text: str | None
    reported_value: str | None
    legal_basis: list
    reported_grade: str | None
    system_grade: str | None
    reported_adjustment_rate: Decimal | None
    system_adjustment_rate: Decimal | None
    comparison_result: dict
    recommended_action: dict
    ai_reasoning_summary: str | None
    ai_confidence: Decimal | None
    ai_status: str
    supersedes_finding_id: UUID | None
    rule_version_id: UUID | None
    created_at: datetime


class RiskSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_summary_id: UUID
    review_id: UUID
    validation_run_id: UUID | None
    overall_risk_level: str
    risk_score: Decimal | None
    summary: str
    high_count: int
    medium_count: int
    low_count: int
    missing_item_count: int
    risk_reasons: list
    generated_at: datetime


FindingDecisionValue = Literal[
    "ACCEPTED",
    "PARTIALLY_ACCEPTED",
    "REJECTED",
    "REQUIRES_SUPPLEMENT",
    "EXPERT_REVIEW",
]
CaseDecisionValue = Literal[
    "RETURNED_FOR_REVISION",
    "SUPPLEMENT_REQUIRED",
    "EXPERT_REVIEW",
    "APPROVED",
    "REVIEW_COMPLETED",
]


class FindingDecisionRequest(BaseModel):
    review_id: UUID
    decision: FindingDecisionValue
    reason: str
    after_value: dict | None = None


class CaseDecisionRequest(BaseModel):
    decision: CaseDecisionValue
    reason: str
    override_reason: str | None = None


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision_id: UUID
    review_id: UUID
    finding_id: UUID | None
    decision: str
    reason: str | None
    decided_by_user_id: UUID | None
    decided_at: datetime
    request_id: UUID | None
    before_value: dict | None
    after_value: dict | None


class ReportDocumentRead(BaseModel):
    document_id: UUID
    case_id: UUID
    document_type: str
    original_filename: str
    mime_type: str
    bucket_name: str
    object_key: str
    checksum_sha256: str
    file_size_bytes: int
    version_no: int
