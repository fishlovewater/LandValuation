from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.review.schemas import (
    CompletenessResponse,
    CorrectionRequestRead,
    DecisionRead,
    FindingRead,
    MissingItemRead,
    ReportDocumentRead,
    ReviewRead,
    RiskSummaryRead,
)

WorkbenchStatusGroup = Literal[
    "pending", "in_progress", "needs_input", "completed", "risk"
]
WorkbenchCaseSource = Literal["PLATFORM", "EXTERNAL"]
WorkbenchCaseSort = Literal[
    "case_no", "case_title", "status", "received_at", "due_at", "risk"
]
WorkbenchSortDirection = Literal["asc", "desc"]
WorkbenchUrgency = Literal["OVERDUE", "URGENT", "DUE_SOON", "NORMAL", "NOT_SET"]


class ExternalReviewCaseCreate(BaseModel):
    case_no: str | None = Field(default=None, max_length=50)
    case_title: str = Field(min_length=1, max_length=200)
    source_organization: str | None = Field(default=None, max_length=200)
    district_code: str = Field(min_length=1, max_length=20)
    valuation_base_date: date
    received_at: datetime | None = None
    due_at: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.received_at and self.due_at and self.due_at < self.received_at:
            raise ValueError("due_at 不得早於 received_at")
        return self


class ExternalReviewCaseCreatedRead(BaseModel):
    review_id: UUID
    case_id: UUID
    case_no: str
    case_source: WorkbenchCaseSource = "EXTERNAL"
    review_status: str


class WorkbenchSummaryRead(BaseModel):
    status_counts: dict[str, int]
    high_risk_count: int
    open_finding_count: int
    missing_item_count: int


class WorkbenchLatestRunRead(BaseModel):
    validation_run_id: UUID
    run_no: int | None
    run_status: str


class WorkbenchCaseListItem(BaseModel):
    review_id: UUID
    case_id: UUID
    case_no: str
    case_title: str
    district_code: str
    case_source: WorkbenchCaseSource
    review_status: str
    current_risk_level: str | None
    missing_item_count: int
    high_count: int
    medium_count: int
    low_count: int
    received_at: datetime
    due_at: datetime | None
    assigned_reviewer_display_name: str | None
    latest_run: WorkbenchLatestRunRead | None
    # Deadline urgency is separate from content risk.
    urgency_level: Literal["OVERDUE", "URGENT", "DUE_SOON", "NORMAL", "NOT_SET"]
    remaining_days: int | None
    correction_round: int
    latest_correction_status: str | None


class WorkbenchCaseList(BaseModel):
    items: list[WorkbenchCaseListItem]
    total: int
    limit: int
    offset: int


class EligibleCaseRead(BaseModel):
    case_id: UUID
    case_no: str
    case_title: str
    district_code: str
    valuation_base_date: date
    case_status: str


class WorkbenchCaseSummaryRead(BaseModel):
    case_id: UUID
    case_no: str
    case_title: str
    case_type: str
    district_code: str
    valuation_base_date: date
    case_status: str


class WorkbenchRunRead(BaseModel):
    """Safe Run projection for the product-facing workbench.

    The immutable input snapshot remains available from the dedicated Run API
    for authorized technical consumers, but is intentionally not nested in the
    workbench payload.
    """

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
    model_id: str | None
    prompt_version: str | None
    error_code: str | None
    error_message: str | None
    submission_id: UUID | None = None
    submission_no: int | None = None
    submitted_at: datetime | None = None
    input_fingerprint: str | None = None
    external_input_snapshot_id: UUID | None = None
    external_input_snapshot_no: int | None = None
    external_input_snapshot_created_at: datetime | None = None
    external_input_fingerprint: str | None = None


class WorkbenchDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    document_group_id: UUID | None = None
    document_type: str
    original_filename: str
    mime_type: str
    version_no: int
    is_active: bool
    uploaded_at: datetime


class WorkbenchFieldVersionRead(BaseModel):
    document_id: UUID
    document_group_id: UUID
    document_version: int
    field_code: str
    field_path: str | None
    normalized_value: Any
    raw_text: str | None
    page_number: int | None


class FieldVersionDiffRead(BaseModel):
    document_group_id: UUID
    field_code: str
    field_path: str | None
    previous: WorkbenchFieldVersionRead
    current: WorkbenchFieldVersionRead


class WorkbenchCaseDetailRead(BaseModel):
    case: WorkbenchCaseSummaryRead
    review: ReviewRead
    case_source: WorkbenchCaseSource
    # Safe Submission metadata only; the immutable input body stays server-side.
    submission_id: UUID | None = None
    submission_no: int | None = None
    submitted_at: datetime | None = None
    input_fingerprint: str | None = None
    documents: list[WorkbenchDocumentRead]
    missing_items: list[MissingItemRead]
    runs: list[WorkbenchRunRead]
    findings: list[FindingRead]
    risk_summary: RiskSummaryRead | None
    decisions: list[DecisionRead]
    version_diffs: list[FieldVersionDiffRead]
    # Safe metadata only: never a bucket name or object key.
    report_document: ReportDocumentRead | None
    generated_reports: list[ReportDocumentRead] = Field(default_factory=list)
    correction_requests: list[CorrectionRequestRead] = Field(default_factory=list)


class WorkbenchCompletenessRead(CompletenessResponse):
    @classmethod
    def from_result(cls, result, review, items):
        return cls(
            ready=result.ready,
            review_status=review.review_status,
            missing_item_count=review.missing_item_count,
            blocked_rule_codes=sorted(result.blocked_rule_codes),
            items=items,
        )


class WorkbenchPreflightRead(BaseModel):
    outcome: Literal["READY", "BLOCKED"]
    completeness: WorkbenchCompletenessRead


class WorkbenchStartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outcome: Literal["BLOCKED", "COMPLETED"]
    completeness: WorkbenchCompletenessRead
    run: WorkbenchRunRead | None = None
    findings: list[FindingRead] = Field(default_factory=list)
    risk_summary: RiskSummaryRead | None = None
