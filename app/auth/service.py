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
        decision_note=None,
        created_at=datetime.now(UTC),
        handled_at=None,
        handled_by_user_id=None,
    )
    session.add(request)
    await session.flush()
    return request


async def list_account_access_requests(
    session: AsyncSession,
    *,
    status: str | None = None,
) -> list[AccountAccessRequest]:
    query = select(AccountAccessRequest).order_by(AccountAccessRequest.created_at.desc())
    if status:
        query = query.where(AccountAccessRequest.status == status)
    return list((await session.scalars(query)).all())


async def decide_account_access_request(
    session: AsyncSession,
    *,
    request_id: UUID,
    decision: str,
    handled_by_user_id: UUID,
    note: str | None,
    expires_minutes: int,
) -> tuple[AccountAccessRequest, bool, str | None, User | None]:
    request = await session.scalar(
        select(AccountAccessRequest)
        .where(AccountAccessRequest.request_id == request_id)
        .with_for_update()
    )
    if request is None:
        raise AppError("ACCOUNT_REQUEST_NOT_FOUND", "找不到指定的帳號申請。", 404)
    if request.status != "PENDING":
        raise AppError("ACCOUNT_REQUEST_ALREADY_HANDLED", "此帳號申請已完成處理。", 409)

    now = datetime.now(UTC)
    request.status = decision
    request.decision_note = note.strip() if note and note.strip() else None
    request.handled_at = now
    request.handled_by_user_id = handled_by_user_id

    if decision == "REJECTED":
        await session.flush()
        return request, False, None, None

    existing = await session.scalar(
        select(User.user_id).where(
            or_(User.username == request.username, User.email == request.email)
        )
    )
    if existing is not None:
        raise AppError(
            "ACCOUNT_ALREADY_EXISTS",
            "核准時發現帳號或 Email 已被使用，請先確認現有帳號。",
            409,
        )
    role = await session.scalar(
        select(Role).where(Role.role_code == request.requested_role, Role.is_active.is_(True))
    )
    if role is None:
        raise AppError("ROLE_NOT_AVAILABLE", "申請的工作角色目前不可用。", 409)

    user = User(
        user_id=uuid4(),
        username=request.username,
        email=request.email,
        password_hash=hash_password(token_urlsafe(48)),
        display_name=request.display_name,
        is_active=True,
        last_login_at=None,
        created_at=now,
        updated_at=now,
    )
    user.roles.append(role)
    session.add(user)
    await session.flush()
    setup_token = await _create_password_reset_token_for_user(
        session,
        user,
        expires_minutes=expires_minutes,
    )
    return request, True, setup_token, user


def _reset_token_hash(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


async def find_active_user_for_account(session: AsyncSession, account: str) -> User | None:
    normalized = account.strip()
    return await session.scalar(
        select(User).where(
            User.is_active.is_(True),
            or_(User.username == normalized, User.email == normalized.lower()),
        )
    )


async def _create_password_reset_token_for_user(
    session: AsyncSession,
    user: User,
    *,
    expires_minutes: int,
) -> str:
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


async def create_password_reset_token(
    session: AsyncSession,
    account: str,
    *,
    expires_minutes: int,
) -> str | None:
    normalized = account.strip()
    user = await find_active_user_for_account(session, normalized)
    if user is None:
        return None
    return await _create_password_reset_token_for_user(
        session,
        user,
        expires_minutes=expires_minutes,
    )


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
