from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

import app.auth.router as auth_router
from app.auth.schemas import DemoLoginRequest


@pytest.mark.asyncio
async def test_demo_login_maps_role_to_fixed_development_account(monkeypatch: pytest.MonkeyPatch) -> None:
    looked_up: list[str] = []
    user = SimpleNamespace(user_id=UUID("11111111-1111-4111-8111-111111111111"))

    monkeypatch.setattr(auth_router, "get_settings", lambda: SimpleNamespace(app_env="development"))

    async def fake_get_active_user_by_username(session: object, username: str) -> object:
        assert session is session_marker
        looked_up.append(username)
        return user

    monkeypatch.setattr(auth_router, "get_active_user_by_username", fake_get_active_user_by_username)
    monkeypatch.setattr(auth_router, "role_codes", lambda received: {"APPRAISER"} if received is user else set())
    monkeypatch.setattr(auth_router, "create_access_token", lambda user_id: (f"token-for-{user_id}", 900))

    session_marker = object()
    result = await auth_router.demo_login(DemoLoginRequest(role="APPRAISER"), session_marker)

    assert looked_up == ["valuation_demo"]
    assert result.access_token == "token-for-11111111-1111-4111-8111-111111111111"
    assert result.expires_in == 900


@pytest.mark.asyncio
async def test_demo_login_is_hidden_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_router, "get_settings", lambda: SimpleNamespace(app_env="production"))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.demo_login(DemoLoginRequest(role="REVIEWER"), object())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Not found"
