from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.models import AccountAccessRequest, PasswordResetToken, User
from app.auth.schemas import AccountAccessRequestCreate
from app.auth.service import (
    confirm_password_reset,
    create_account_access_request,
    create_password_reset_token,
)
from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.db.session import AsyncSessionFactory


@pytest.mark.asyncio
async def test_account_request_and_password_reset_persist_in_isolated_database() -> None:
    now = datetime.now(UTC)
    reset_user_id = uuid4()

    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add(
                User(
                    user_id=reset_user_id,
                    username=f"reset-{reset_user_id.hex[:10]}",
                    email=f"reset-{reset_user_id.hex[:10]}@example.test",
                    password_hash=hash_password("initial-value-123"),
                    display_name="Reset Integration User",
                    is_active=True,
                    last_login_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.flush()

            request = await create_account_access_request(
                session,
                AccountAccessRequestCreate(
                    username=f"applicant-{reset_user_id.hex[:10]}",
                    email=f"applicant-{reset_user_id.hex[:10]}@example.test",
                    display_name="Applicant Integration User",
                    requested_role="REVIEWER",
                    reason="integration coverage",
                ),
            )
            assert request.status == "PENDING"

            persisted_request = await session.get(AccountAccessRequest, request.request_id)
            assert persisted_request is not None
            assert persisted_request.requested_role == "REVIEWER"

            raw_token = await create_password_reset_token(
                session,
                f"reset-{reset_user_id.hex[:10]}",
                expires_minutes=30,
            )
            assert raw_token is not None

            persisted_token = await session.scalar(
                select(PasswordResetToken).where(PasswordResetToken.user_id == reset_user_id)
            )
            assert persisted_token is not None
            assert persisted_token.token_hash != raw_token
            assert len(persisted_token.token_hash) == 64

            await confirm_password_reset(session, raw_token, "replacement-value-123")
            user = await session.get(User, reset_user_id)
            assert user is not None
            assert verify_password("replacement-value-123", user.password_hash)
            assert persisted_token.used_at is not None

            with pytest.raises(AppError) as exc_info:
                await confirm_password_reset(session, raw_token, "second-replacement-123")
            assert exc_info.value.code == "PASSWORD_RESET_TOKEN_INVALID"

        await session.rollback()


@pytest.mark.asyncio
async def test_password_reset_unknown_account_returns_no_token() -> None:
    async with AsyncSessionFactory() as session:
        raw_token = await create_password_reset_token(
            session,
            f"missing-{uuid4().hex}@example.test",
            expires_minutes=30,
        )
        assert raw_token is None
        await session.rollback()
