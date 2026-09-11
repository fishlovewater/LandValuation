from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import CurrentUser, DbSession
from app.auth.schemas import CurrentUserResponse, DemoLoginRequest, LoginRequest, TokenResponse
from app.auth.service import authenticate_user, get_active_user_by_username, permission_codes, role_codes
from app.core.config import get_settings
from app.core.security import create_access_token

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    user = await authenticate_user(session, payload.username, payload.password)
    token, expires_in = create_access_token(user.user_id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(payload: DemoLoginRequest, session: DbSession) -> TokenResponse:
    """Development-only one-click login for the fixed hackathon Demo accounts."""

    if get_settings().app_env.lower() != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    username_by_role = {
        "APPRAISER": "valuation_demo",
        "REVIEWER": "review_demo",
        "INSPECTOR": "inspector_demo",
    }
    user = await get_active_user_by_username(session, username_by_role[payload.role])
    if payload.role not in role_codes(user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Demo account role mismatch")

    token, expires_in = create_access_token(user.user_id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        roles=sorted(role_codes(user)),
        permissions=sorted(permission_codes(user)),
    )
