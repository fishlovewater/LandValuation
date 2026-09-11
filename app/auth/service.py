from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import AccountAccessRequest, PasswordResetToken, Role, User
from app.auth.schemas import AccountAccessRequestCreate
from app.core.exceptions import AppError, AuthenticationError
from app.core.security import hash_password, verify_password


def _user_query():
    return select(User).options(selectinload(User.roles).selectinload(Role.permissions))


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User:
    user = await session.scalar(_user_query().where(User.username == username))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise AuthenticationError()
    user.last_login_at = datetime.now(UTC)
    return user


async def get_active_user_by_username(session: AsyncSession, username: str) -> User:
    user = await session.scalar(_user_query().where(User.username == username))
    if user is None or not user.is_active:
        raise AuthenticationError("使用者不存在或已停用")
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
    return {
        permission.permission_code
        for role in user.roles
        if role.is_active
        for permission in role.permissions
    }


async def create_account_access_request(
    session: AsyncSession,
    payload: AccountAccessRequestCreate,
) -> AccountAccessRequest:
    username = payload.username.strip()
    email = payload.email.strip().lower()
    existing_user = await session.scalar(
        select(User.user_id).where(or_(User.username == username, User.email == email))
    )
    if existing_user is not None:
        raise AppError(
            "ACCOUNT_ALREADY_EXISTS",
            "此帳號或 Email 已存在；請直接登入或使用忘記密碼。",
            409,
        )
    pending = await session.scalar(
        select(AccountAccessRequest.request_id).where(
            AccountAccessRequest.status == "PENDING",
            or_(
                AccountAccessRequest.username == username,
                AccountAccessRequest.email == email,
            ),
        )
    )
    if pending is not None:
        raise AppError(
            "ACCOUNT_REQUEST_PENDING",
            "已有相同帳號或 Email 的待審申請。",
            409,
        )
    request = AccountAccessRequest(
        request_id=uuid4(),
        username=username,
        email=email,
        display_name=payload.display_name.strip(),
        requested_role=payload.requested_role,
        reason=payload.reason.strip() if payload.reason and payload.reason.strip() else None,
        status="PENDING",
        created_at=datetime.now(UTC),
        handled_at=None,
        handled_by_user_id=None,
    )
    session.add(request)
    await session.flush()
    return request


def _reset_token_hash(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


async def create_password_reset_token(
    session: AsyncSession,
    account: str,
    *,
    expires_minutes: int,
) -> str | None:
    normalized = account.strip()
    user = await session.scalar(
        select(User).where(
            User.is_active.is_(True),
            or_(User.username == normalized, User.email == normalized.lower()),
        )
    )
    if user is None:
        return None
    raw_token = token_urlsafe(48)
    now = datetime.now(UTC)
    session.add(
        PasswordResetToken(
            token_id=uuid4(),
            user_id=user.user_id,
            token_hash=_reset_token_hash(raw_token),
            expires_at=now + timedelta(minutes=expires_minutes),
            used_at=None,
            created_at=now,
        )
    )
    await session.flush()
    return raw_token


async def confirm_password_reset(
    session: AsyncSession,
    raw_token: str,
    new_password: str,
) -> None:
    now = datetime.now(UTC)
    reset = await session.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == _reset_token_hash(raw_token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .with_for_update()
    )
    if reset is None:
        raise AppError(
            "PASSWORD_RESET_TOKEN_INVALID",
            "密碼重設連結無效、已使用或已過期。",
            400,
        )
    user = await session.get(User, reset.user_id)
    if user is None or not user.is_active:
        raise AppError(
            "PASSWORD_RESET_TOKEN_INVALID",
            "密碼重設連結無效、已使用或已過期。",
            400,
        )
    user.password_hash = hash_password(new_password)
    user.updated_at = now
    reset.used_at = now
    await session.flush()
