from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, DbSession
from app.auth.schemas import CurrentUserResponse, LoginRequest, TokenResponse
from app.auth.service import authenticate_user, permission_codes, role_codes
from app.core.security import create_access_token

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    user = await authenticate_user(session, payload.username, payload.password)
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
