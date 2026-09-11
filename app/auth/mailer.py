import asyncio
from email.message import EmailMessage
import smtplib
from urllib.parse import quote

from app.core.config import Settings


def smtp_delivery_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


def _reset_url(settings: Settings, token: str) -> str:
    return f"{settings.public_app_url}/forgot-password?token={quote(token, safe='')}"


def _send_message(settings: Settings, message: EmailMessage) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP host is not configured")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
        if settings.smtp_starttls:
            client.starttls()
        if settings.smtp_username:
            if settings.smtp_password is None:
                raise RuntimeError("SMTP password is required when SMTP username is configured")
            client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        client.send_message(message)


async def send_password_setup_email(
    settings: Settings,
    *,
    recipient: str,
    display_name: str,
    token: str,
    purpose: str = "reset",
) -> bool:
    """Send a one-time password setup/reset link without logging the raw token."""

    if not smtp_delivery_configured(settings):
        return False

    action = "設定" if purpose == "setup" else "重設"
    message = EmailMessage()
    message["Subject"] = f"{settings.app_name}｜{action}登入密碼"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        f"{display_name} 您好：\n\n"
        f"請使用下列一次性連結{action}登入密碼：\n"
        f"{_reset_url(settings, token)}\n\n"
        f"此連結將在 {settings.password_reset_token_minutes} 分鐘後失效，且僅能使用一次。\n"
        "若您未提出此要求，請忽略本信。\n"
    )
    await asyncio.to_thread(_send_message, settings, message)
    return True
