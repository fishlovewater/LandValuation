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
