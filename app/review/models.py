from datetime import datetime
from uuid import UUID

from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _review_submission_record_class():
    """Resolve the valuation handoff mapping only when SQLAlchemy configures it."""

    from app.valuation.models import ReviewSubmissionRecord

    return ReviewSubmissionRecord


class Review(Base):
    """ORM mapping for the Alembic-managed review.reviews table."""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_reviews_case_id"),
        {"schema": "review"},
    )

    review_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    form_instance_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    validation_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    review_type: Mapped[str] = mapped_column(String(50), server_default="SMART_REVIEW")
    review_status: Mapped[str] = mapped_column(String(30), server_default="PENDING")
    started_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_reviewer_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    manual_priority: Mapped[int] = mapped_column(Integer, server_default="0")
    manual_priority_reason: Mapped[str | None] = mapped_column(Text)
    current_risk_level: Mapped[str | None] = mapped_column(String(20))
    high_count: Mapped[int] = mapped_column(Integer, server_default="0")
    medium_count: Mapped[int] = mapped_column(Integer, server_default="0")
    low_count: Mapped[int] = mapped_column(Integer, server_default="0")
    missing_item_count: Mapped[int] = mapped_column(Integer, server_default="0")
    latest_validation_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    latest_submission_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("valuation.review_submissions.submission_id"),
    )
    latest_submission = relationship(
        _review_submission_record_class,
        foreign_keys=[latest_submission_id],
        post_update=True,
        uselist=False,
    )


class MissingItem(Base):
    __tablename__ = "missing_items"
    __table_args__ = {"schema": "review"}

    missing_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    item_code: Mapped[str] = mapped_column(String(100), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20), server_default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), server_default="OPEN")
    details: Mapped[str | None] = mapped_column(Text)
    resolved_document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    validation_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    field_path: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    affected_rule_codes: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_status: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    __table_args__ = {"schema": "valuation"}

    validation_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    form_instance_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    run_status: Mapped[str] = mapped_column(String(20), server_default="RUNNING")
    passed_count: Mapped[int] = mapped_column(Integer, server_default="0")
    warning_count: Mapped[int] = mapped_column(Integer, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    rule_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    ruleset_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    review_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    run_no: Mapped[int | None] = mapped_column(Integer)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    submission_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("valuation.review_submissions.submission_id"),
    )


class ValidationFinding(Base):
    __tablename__ = "validation_findings"
    __table_args__ = {"schema": "valuation"}

    finding_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    validation_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    validation_rule_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    field_code: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_value: Mapped[dict | None] = mapped_column(JSONB)
    expected_value: Mapped[dict | None] = mapped_column(JSONB)
    finding_message: Mapped[str] = mapped_column(Text, nullable=False)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = {"schema": "review"}

    finding_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_validation_finding_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    finding_code: Mapped[str] = mapped_column(String(100), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), server_default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    validation_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    document_version: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    field_path: Mapped[str | None] = mapped_column(Text)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB)
    source_evidence: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    reported_text: Mapped[str | None] = mapped_column(Text)
    reported_value: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    reported_grade: Mapped[str | None] = mapped_column(String(100))
    system_grade: Mapped[str | None] = mapped_column(String(100))
    reported_adjustment_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    system_adjustment_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    comparison_result: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    recommended_action: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ai_reasoning_summary: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    ai_status: Mapped[str] = mapped_column(String(40), server_default="NOT_REQUESTED")
    supersedes_finding_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    rule_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))


class RiskSummary(Base):
    __tablename__ = "risk_summaries"
    __table_args__ = {"schema": "review"}

    risk_summary_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    overall_risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    category_scores: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    validation_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    high_count: Mapped[int] = mapped_column(Integer, server_default="0")
    medium_count: Mapped[int] = mapped_column(Integer, server_default="0")
    low_count: Mapped[int] = mapped_column(Integer, server_default="0")
    missing_item_count: Mapped[int] = mapped_column(Integer, server_default="0")
    risk_reasons: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = {"schema": "review"}

    decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    finding_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    request_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    before_value: Mapped[dict | None] = mapped_column(JSONB)
    after_value: Mapped[dict | None] = mapped_column(JSONB)


class CorrectionRequest(Base):
    __tablename__ = "correction_requests"
    __table_args__ = {"schema": "review"}

    correction_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_no: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_validation_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), server_default="DRAFT")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    base_document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    base_document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    response_document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    response_document_version: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    sent_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resubmitted_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    resubmitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rechecked_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    rechecked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CorrectionRequestItem(Base):
    __tablename__ = "correction_request_items"
    __table_args__ = {"schema": "review"}

    correction_request_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    correction_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    finding_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    finding_code: Mapped[str] = mapped_column(String(100), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    document_version: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    reported_text: Mapped[str | None] = mapped_column(Text)
    reported_value: Mapped[str | None] = mapped_column(Text)
    legal_basis_snapshot: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    source_evidence_snapshot: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    issue_summary: Mapped[str] = mapped_column(Text, nullable=False)
    requested_correction: Mapped[str] = mapped_column(Text, nullable=False)
    recheck_outcome: Mapped[str] = mapped_column(String(20), server_default="PENDING")
    resulting_finding_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    rechecked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UrgencySettings(Base):
    __tablename__ = "urgency_settings"
    __table_args__ = {"schema": "review"}

    settings_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    urgent_days: Mapped[int] = mapped_column(Integer, nullable=False)
    due_soon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
