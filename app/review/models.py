from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Review(Base):
    """ORM mapping for the Alembic-managed review.reviews table."""

    __tablename__ = "reviews"
    __table_args__ = {"schema": "review"}

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
