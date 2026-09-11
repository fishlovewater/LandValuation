from datetime import datetime
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class DemoLoginRequest(BaseModel):
    role: Literal["APPRAISER", "REVIEWER", "INSPECTOR"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    username: str
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]


class AccountAccessRequestCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    display_name: str = Field(min_length=1, max_length=200)
    requested_role: Literal["APPRAISER", "REVIEWER", "INSPECTOR"]
    reason: str | None = Field(default=None, max_length=1000)


class AccountAccessRequestResponse(BaseModel):
    request_id: UUID
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    message: str


class AccountAccessRequestAdminItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    username: str
    email: str
    display_name: str
    requested_role: str
    reason: str | None
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    decision_note: str | None
    created_at: datetime
    handled_at: datetime | None
    handled_by_user_id: UUID | None


class AccountAccessDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    note: str | None = Field(default=None, max_length=2000)


class AccountAccessDecisionResponse(BaseModel):
    request: AccountAccessRequestAdminItem
    account_created: bool = False
    setup_email_sent: bool = False
    debug_setup_token: str | None = None


class PasswordResetRequest(BaseModel):
    account: str = Field(min_length=1, max_length=320)


class PasswordResetRequestResponse(BaseModel):
    message: str
    debug_token: str | None = None


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetConfirmResponse(BaseModel):
    message: str
