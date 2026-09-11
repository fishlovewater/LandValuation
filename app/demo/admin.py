"""Development-only bootstrap for the account-management administrator.

The account is intentionally separate from the three one-click Demo roles.
It exists only so the real ``auth.manage`` workflow can be exercised locally.
"""

from __future__ import annotations

import argparse
import json
from uuid import uuid4

import psycopg

from app.core.config import get_settings
from app.core.security import hash_password

from .accounts import DEMO_LIFECYCLE_LOCK_KEY, DEMO_PASSWORD
from .contracts import DemoError


ADMIN_USERNAME = "system_admin_demo"
ADMIN_EMAIL = "system_admin_demo@local.invalid"
ADMIN_DISPLAY_NAME = "Demo System Administrator"
ADMIN_ROLE_CODE = "SYSTEM_ADMIN"
ADMIN_PERMISSION_CODE = "auth.manage"


def _ensure_development() -> None:
    if get_settings().app_env != "development":
        raise DemoError("DEVELOPMENT_ONLY: demo admin bootstrap requires APP_ENV=development")


def _connect():
    settings = get_settings()
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )


def _admin_role_id(cursor):
    cursor.execute(
        """
        SELECT r.role_id
        FROM auth.roles AS r
        JOIN auth.role_permissions AS rp ON rp.role_id = r.role_id
        JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
        WHERE r.role_code = %s
          AND r.is_active = true
          AND p.permission_code = %s
        """,
        (ADMIN_ROLE_CODE, ADMIN_PERMISSION_CODE),
    )
    row = cursor.fetchone()
    if row is None:
        raise DemoError("DEMO_ADMIN_ROLE_NOT_READY: run migrations through 20260911_0021")
    return row[0]


def seed() -> dict[str, object]:
    """Create or refresh the typed-login development administrator."""

    _ensure_development()
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (DEMO_LIFECYCLE_LOCK_KEY,))
            role_id = _admin_role_id(cursor)
            cursor.execute(
                """
                SELECT user_id, email, display_name
                FROM auth.users
                WHERE username = %s
                FOR UPDATE
                """,
                (ADMIN_USERNAME,),
            )
            existing = cursor.fetchone()
            password_hash = hash_password(DEMO_PASSWORD)
            if existing is None:
                user_id = uuid4()
                cursor.execute(
                    """
                    INSERT INTO auth.users (
                        user_id, username, email, password_hash, display_name,
                        is_active, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, true, now(), now())
                    """,
                    (user_id, ADMIN_USERNAME, ADMIN_EMAIL, password_hash, ADMIN_DISPLAY_NAME),
                )
            else:
                user_id, email, display_name = existing
                if email != ADMIN_EMAIL or display_name != ADMIN_DISPLAY_NAME:
                    raise DemoError(
                        f"OWNERSHIP_COLLISION: auth.users.username={ADMIN_USERNAME}"
                    )
                cursor.execute(
                    """
                    UPDATE auth.users
                    SET password_hash = %s, is_active = true, updated_at = now()
                    WHERE user_id = %s
                    """,
                    (password_hash, user_id),
                )

            cursor.execute("DELETE FROM auth.user_roles WHERE user_id = %s", (user_id,))
            cursor.execute(
                "INSERT INTO auth.user_roles (user_id, role_id) VALUES (%s, %s)",
                (user_id, role_id),
            )
        connection.commit()
    return {
        "ready": True,
        "username": ADMIN_USERNAME,
        "role": ADMIN_ROLE_CODE,
        "permission": ADMIN_PERMISSION_CODE,
    }


def status() -> dict[str, object]:
    """Return non-secret readiness information for the development admin."""

    _ensure_development()
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.is_active,
                       bool_or(r.role_code = %s AND p.permission_code = %s)
                FROM auth.users AS u
                LEFT JOIN auth.user_roles AS ur ON ur.user_id = u.user_id
                LEFT JOIN auth.roles AS r ON r.role_id = ur.role_id
                LEFT JOIN auth.role_permissions AS rp ON rp.role_id = r.role_id
                LEFT JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
                WHERE u.username = %s
                GROUP BY u.user_id, u.is_active
                """,
                (ADMIN_ROLE_CODE, ADMIN_PERMISSION_CODE, ADMIN_USERNAME),
            )
            row = cursor.fetchone()
    return {
        "ready": bool(row and row[0] and row[1]),
        "username": ADMIN_USERNAME,
        "role": ADMIN_ROLE_CODE,
        "permission": ADMIN_PERMISSION_CODE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the development-only system admin")
    parser.add_argument("command", choices=("seed", "status"))
    args = parser.parse_args()
    try:
        result = seed() if args.command == "seed" else status()
    except DemoError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    except Exception:
        print("DEMO_ADMIN_COMMAND_FAILED")
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())