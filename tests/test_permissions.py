from types import SimpleNamespace

import pytest

from app.auth.dependencies import require_permissions, require_roles
from app.core.exceptions import PermissionDeniedError


def fake_user():
    permissions = [SimpleNamespace(permission_code="case.read")]
    role = SimpleNamespace(role_code="APPRAISER", is_active=True, permissions=permissions)
    return SimpleNamespace(roles=[role])


@pytest.mark.asyncio
async def test_permission_dependency_accepts_granted_permission() -> None:
    user = fake_user()
    assert await require_permissions("case.read")(user) is user


@pytest.mark.asyncio
async def test_permission_dependency_rejects_missing_permission() -> None:
    with pytest.raises(PermissionDeniedError):
        await require_permissions("review.decide")(fake_user())


@pytest.mark.asyncio
async def test_role_dependency() -> None:
    user = fake_user()
    assert await require_roles("APPRAISER")(user) is user
