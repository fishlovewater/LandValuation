from datetime import datetime
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
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
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
