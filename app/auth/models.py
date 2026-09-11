from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Table, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("auth.users.user_id"), primary_key=True),
    Column("role_id", ForeignKey("auth.roles.role_id"), primary_key=True),
    schema="auth",
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("auth.roles.role_id"), primary_key=True),
    Column("permission_id", ForeignKey("auth.permissions.permission_id"), primary_key=True),
    schema="auth",
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, lazy="selectin")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "auth"}

    role_id: Mapped[UUID] = mapped_column(primary_key=True)
    role_code: Mapped[str] = mapped_column(String(80), unique=True)
    role_name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions,
        lazy="selectin",
    )


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "auth"}

    permission_id: Mapped[UUID] = mapped_column(primary_key=True)
    permission_code: Mapped[str] = mapped_column(String(120), unique=True)
    permission_name: Mapped[str] = mapped_column(String(200))
    resource: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)


class AccountAccessRequest(Base):
    __tablename__ = "account_access_requests"
    __table_args__ = (
        CheckConstraint(
            "requested_role IN ('APPRAISER', 'REVIEWER', 'INSPECTOR')",
            name="ck_account_access_requests_role",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_account_access_requests_status",
        ),
        Index(
            "uq_account_access_requests_pending_username",
            "username",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "uq_account_access_requests_pending_email",
            "email",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        {"schema": "auth"},
    )

    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    requested_role: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("auth.users.user_id")
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = {"schema": "auth"}

    token_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.user_id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
