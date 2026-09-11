from email.message import EmailMessage

import pytest
from pydantic import ValidationError

from app.auth import mailer
from app.core.config import Settings


@pytest.mark.asyncio
async def test_password_reset_mail_contains_one_time_frontend_link(monkeypatch) -> None:
    captured: list[EmailMessage] = []

    def fake_send(settings: Settings, message: EmailMessage) -> None:
        captured.append(message)

    monkeypatch.setattr(mailer, "_send_message", fake_send)
    settings = Settings(
        _env_file=None,
        app_env="test",
        public_app_url="https://valuation.example.test/",
        smtp_host="smtp.example.test",
        smtp_from_email="noreply@example.test",
        smtp_starttls=True,
    )

    delivered = await mailer.send_password_setup_email(
        settings,
        recipient="user@example.test",
        display_name="測試使用者",
        token="one-time-token-value",
        purpose="reset",
    )

    assert delivered is True
    assert len(captured) == 1
    message = captured[0]
    assert message["To"] == "user@example.test"
    body = message.get_content()
    assert "https://valuation.example.test/forgot-password?token=one-time-token-value" in body
    assert "one-time-token-value" in body


@pytest.mark.asyncio
async def test_password_reset_mail_is_disabled_without_smtp() -> None:
    settings = Settings(_env_file=None, app_env="test", smtp_host=None, smtp_from_email=None)
    delivered = await mailer.send_password_setup_email(
        settings,
        recipient="user@example.test",
        display_name="測試使用者",
        token="token",
    )
    assert delivered is False


def test_non_development_requires_smtp_delivery_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="a-production-secret-that-is-not-the-development-default",
            smtp_host=None,
            smtp_from_email=None,
        )
