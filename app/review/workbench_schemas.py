from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.review.schemas import (
    CompletenessResponse,
    DecisionRead,
    FindingRead,
    MissingItemRead,
    ReportDocumentRead,
    ReviewRead,
    RiskSummaryRead,
    ValidationRunRead,
)

WorkbenchStatusGroup = Literal[
    "pending", "in_progress", "needs_input", "completed", "risk"
]


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
    review_status: str
    current_risk_level: str | None
    missing_item_count: int
    received_at: datetime
    due_at: datetime | None
    assigned_reviewer_display_name: str | None
    latest_run: WorkbenchLatestRunRead | None


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
    district_code: str
    valuation_base_date: date
    case_status: str


class WorkbenchDocumentRead(BaseModel):
    document_id: UUID
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
    documents: list[WorkbenchDocumentRead]
    missing_items: list[MissingItemRead]
    runs: list[ValidationRunRead]
    findings: list[FindingRead]
    risk_summary: RiskSummaryRead | None
    decisions: list[DecisionRead]
    version_diffs: list[FieldVersionDiffRead]
    report_document: ReportDocumentRead | None


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


class WorkbenchStartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outcome: Literal["BLOCKED", "COMPLETED"]
    completeness: WorkbenchCompletenessRead
    run: ValidationRunRead | None = None
    findings: list[FindingRead] = Field(default_factory=list)
    risk_summary: RiskSummaryRead | None = None
