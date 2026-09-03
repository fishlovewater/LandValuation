from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import Role, User
from app.core.exceptions import AuthenticationError
from app.core.security import verify_password


def _user_query():
    return select(User).options(selectinload(User.roles).selectinload(Role.permissions))


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User:
    user = await session.scalar(_user_query().where(User.username == username))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise AuthenticationError()
    user.last_login_at = datetime.now(UTC)
    return user


async def get_active_user(session: AsyncSession, user_id: UUID) -> User:
    user = await session.scalar(_user_query().where(User.user_id == user_id))
    if user is None or not user.is_active:
        raise AuthenticationError("使用者不存在或已停用")
    return user


def role_codes(user: User) -> set[str]:
    return {role.role_code for role in user.roles if role.is_active}


def permission_codes(user: User) -> set[str]:
    codes = {
        permission.permission_code
        for role in user.roles
        if role.is_active
        for permission in role.permissions
    }
    # Task 7 adds the appraiser-only submit command before the next seed
    # migration.  Keep the application policy explicit so API authorization
    # matches the APPRAISER role contract without granting Review-only users.
    if "APPRAISER" in role_codes(user):
        codes.add("valuation.submit_review")
    return codes
