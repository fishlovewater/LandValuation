from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubmitForReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    expected_case_version: int = Field(ge=1)
    source_validation_run_id: UUID
    source_report_document_id: UUID


class SubmitForReviewResult(BaseModel):
    submission_id: UUID
    submission_no: int
    review_id: UUID
    case_status: str
    submitted_at: datetime


class HandoffSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    submission_id: UUID
    submission_no: int
    submitted_at: datetime


class HandoffCorrectionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_code: str
    severity: str
    document_id: UUID | None
    page_number: int | None
    issue_summary: str
    requested_correction: str


class HandoffCorrectionRead(BaseModel):
    correction_request_id: UUID
    request_no: int
    status: str
    due_at: datetime
    message: str
    items: list[HandoffCorrectionItemRead]


class HandoffMissingItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_code: str
    item_name: str
    document_type: str | None
    severity: str
    reason: str | None
    due_at: datetime | None


class ValuationReviewHandoffRead(BaseModel):
    case_id: UUID
    case_status: str
    display_status: str
    review_id: UUID | None
    review_status: str | None
    latest_submission: HandoffSubmissionRead | None
    correction: HandoffCorrectionRead | None
    missing_items: list[HandoffMissingItemRead] = Field(default_factory=list)
