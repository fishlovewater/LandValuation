from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.models import AccountAccessRequest, PasswordResetToken, Permission, Role, User
from app.auth.schemas import AccountAccessRequestCreate
from app.auth.service import (
    create_account_access_request,
    decide_account_access_request,
    list_account_access_requests,
)
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.db.session import AsyncSessionFactory


@pytest.mark.asyncio
async def test_admin_can_approve_request_create_role_account_and_setup_token() -> None:
    suffix = uuid4().hex[:10]
    manager_id = uuid4()
    async with AsyncSessionFactory() as session:
        async with session.begin():
            system_admin = await session.scalar(
                select(Role).where(Role.role_code == "SYSTEM_ADMIN")
            )
            assert system_admin is not None
            assert "auth.manage" in {permission.permission_code for permission in system_admin.permissions}
            assert await session.scalar(
                select(Permission.permission_id).where(Permission.permission_code == "auth.manage")
            ) is not None

            manager = User(
                user_id=manager_id,
                username=f"manager-{suffix}",
                email=f"manager-{suffix}@example.test",
                password_hash=hash_password("integration-password-123"),
                display_name="Integration Manager",
                is_active=True,
                last_login_at=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(manager)
            await session.flush()

            request = await create_account_access_request(
                session,
                AccountAccessRequestCreate(
                    username=f"approved-{suffix}",
                    email=f"approved-{suffix}@example.test",
                    display_name="Approved User",
                    requested_role="APPRAISER",
                    reason="integration test",
                ),
            )
            handled, created, raw_token, user = await decide_account_access_request(
                session,
                request_id=request.request_id,
                decision="APPROVED",
                handled_by_user_id=manager_id,
                note="符合申請資格",
                expires_minutes=30,
            )

            assert handled.status == "APPROVED"
            assert handled.decision_note == "符合申請資格"
            assert created is True
            assert raw_token
            assert user is not None
            assert [role.role_code for role in user.roles] == ["APPRAISER"]
            persisted_token = await session.scalar(
                select(PasswordResetToken).where(PasswordResetToken.user_id == user.user_id)
            )
            assert persisted_token is not None
            assert persisted_token.token_hash != raw_token

            approved = await list_account_access_requests(session, status="APPROVED")
            assert request.request_id in {item.request_id for item in approved}

            with pytest.raises(AppError) as error:
                await decide_account_access_request(
                    session,
                    request_id=request.request_id,
                    decision="REJECTED",
                    handled_by_user_id=manager_id,
                    note=None,
                    expires_minutes=30,
                )
            assert error.value.code == "ACCOUNT_REQUEST_ALREADY_HANDLED"

        await session.rollback()


@pytest.mark.asyncio
async def test_admin_can_reject_request_without_creating_account() -> None:
    suffix = uuid4().hex[:10]
    manager_id = uuid4()
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add(
                User(
                    user_id=manager_id,
                    username=f"manager-reject-{suffix}",
                    email=f"manager-reject-{suffix}@example.test",
                    password_hash=hash_password("integration-password-123"),
                    display_name="Integration Manager",
                    is_active=True,
                    last_login_at=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            request = await create_account_access_request(
                session,
                AccountAccessRequestCreate(
                    username=f"rejected-{suffix}",
                    email=f"rejected-{suffix}@example.test",
                    display_name="Rejected User",
                    requested_role="REVIEWER",
                ),
            )
            handled, created, token, user = await decide_account_access_request(
                session,
                request_id=request.request_id,
                decision="REJECTED",
                handled_by_user_id=manager_id,
                note="資料不完整",
                expires_minutes=30,
            )
            assert handled.status == "REJECTED"
            assert handled.decision_note == "資料不完整"
            assert created is False
            assert token is None
            assert user is None
            assert await session.scalar(
                select(User.user_id).where(User.username == request.username)
            ) is None

        await session.rollback()
