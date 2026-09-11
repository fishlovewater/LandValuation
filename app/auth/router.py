from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import CurrentUser, DbSession
from app.auth.schemas import (
    AccountAccessRequestCreate,
    AccountAccessRequestResponse,
    CurrentUserResponse,
    DemoLoginRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    TokenResponse,
)
from app.auth.service import (
    authenticate_user,
    confirm_password_reset,
    create_account_access_request,
    create_password_reset_token,
    get_active_user_by_username,
    permission_codes,
    role_codes,
)
from app.core.config import get_settings
from app.core.security import create_access_token

router = APIRouter()


@router.post(
    "/registration-requests",
    response_model=AccountAccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registration_request(
    payload: AccountAccessRequestCreate,
    session: DbSession,
) -> AccountAccessRequestResponse:
    request = await create_account_access_request(session, payload)
    return AccountAccessRequestResponse(
        request_id=request.request_id,
        status="PENDING",
        message="帳號申請已送出，待系統管理者審核後核發工作帳號。",
    )


@router.post(
    "/password-reset-requests",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def password_reset_request(
    payload: PasswordResetRequest,
    session: DbSession,
) -> PasswordResetRequestResponse:
    settings = get_settings()
    token = await create_password_reset_token(
        session,
        payload.account,
        expires_minutes=settings.password_reset_token_minutes,
    )
    debug_token = None
    if (
        token
        and settings.app_env.lower() == "development"
        and settings.password_reset_debug_token_enabled
    ):
        debug_token = token
    return PasswordResetRequestResponse(
        message="若帳號存在，系統已建立密碼重設要求。為避免洩漏帳號資訊，結果一律相同。",
        debug_token=debug_token,
    )


@router.post(
    "/password-reset-confirm",
    response_model=PasswordResetConfirmResponse,
)
async def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    session: DbSession,
) -> PasswordResetConfirmResponse:
    await confirm_password_reset(session, payload.token, payload.new_password)
    return PasswordResetConfirmResponse(message="密碼已更新，請使用新密碼登入。")


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    user = await authenticate_user(session, payload.username, payload.password)
    token, expires_in = create_access_token(user.user_id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(payload: DemoLoginRequest, session: DbSession) -> TokenResponse:
    """Explicitly enabled one-click login for the fixed competition Demo accounts."""

    settings = get_settings()
    if settings.app_env.lower() != "development" and not settings.demo_quick_login_enabled:
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
