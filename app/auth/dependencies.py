from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import get_active_user, permission_codes, role_codes
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.session import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("需要登入")
    user_id = decode_access_token(credentials.credentials)
    return await get_active_user(session, user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permissions(*required: str) -> Callable:
    async def dependency(user: CurrentUser) -> User:
        if not set(required).issubset(permission_codes(user)):
            raise PermissionDeniedError()
        return user

    return dependency


def require_roles(*required: str) -> Callable:
    async def dependency(user: CurrentUser) -> User:
        if not set(required).intersection(role_codes(user)):
            raise PermissionDeniedError()
        return user

    return dependency
