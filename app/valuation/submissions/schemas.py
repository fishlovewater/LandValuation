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
