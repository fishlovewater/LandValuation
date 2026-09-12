"""Development-only lifecycle for the Valuation Demo APPRAISER account."""

from __future__ import annotations

import argparse
import json
import secrets
from contextlib import closing
from uuid import UUID, uuid4

import psycopg

from app.core.config import get_settings
from app.core.security import hash_password

DEMO_USERNAME = "valuation_demo"
DEMO_EMAIL = "valuation_demo@local.invalid"
DEMO_DISPLAY_NAME = "Valuation Demo Appraiser"
DEMO_ROLE = "APPRAISER"
REQUIRED_PERMISSIONS = {
    "case.create",
    "case.read",
    "case.update",
    "valuation.read",
    "valuation.update",
    "valuation.submit_review",
    "document.upload",
    "document.download",
}


class DemoError(RuntimeError):
    """A safe, user-facing failure in the development Demo lifecycle."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the Valuation development Demo APPRAISER account"
    )
    parser.add_argument("command", choices=("seed", "status", "reset"))
    return parser


def _ensure_development() -> None:
    if get_settings().app_env.lower() != "development":
        raise DemoError("DEVELOPMENT_ONLY: demo commands require APP_ENV=development")


def _connect():
    settings = get_settings()
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )


def _appraiser_role_and_permissions(cursor) -> tuple[UUID, list[str]]:
    cursor.execute(
        """
        SELECT r.role_id
        FROM auth.roles AS r
        WHERE r.role_code = %s AND r.is_active = true
        """,
        (DEMO_ROLE,),
    )
    role = cursor.fetchone()
    if role is None:
        raise DemoError("APPRAISER_ROLE_MISSING: run migrations before seed")

    role_id = role[0]
    cursor.execute(
        """
        SELECT p.permission_code
        FROM auth.role_permissions AS rp
        JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
        WHERE rp.role_id = %s
        ORDER BY p.permission_code
        """,
        (role_id,),
    )
    permissions = sorted({row[0] for row in cursor.fetchall()})
    missing = REQUIRED_PERMISSIONS.difference(permissions)
    if missing:
        missing_codes = ", ".join(sorted(missing))
        raise DemoError(
            "APPRAISER_PERMISSIONS_MISSING: "
            f"run migrations before seed ({missing_codes})"
        )
    return role_id, permissions


def _demo_user(cursor, *, for_update: bool = False):
    lock_clause = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT user_id, email, display_name, is_active
        FROM auth.users
        WHERE username = %s{lock_clause}
        """,
        (DEMO_USERNAME,),
    )
    return cursor.fetchone()


def _ensure_owned_user(row) -> UUID:
    if row[1] != DEMO_EMAIL or row[2] != DEMO_DISPLAY_NAME:
        raise DemoError(
            "OWNERSHIP_COLLISION: auth.users.username=" f"{DEMO_USERNAME}"
        )
    return row[0]


def seed(password: str | None = None) -> dict[str, object]:
    """Create or refresh the fixed Demo account.

    ``password`` is intentionally injectable for tests. Normal invocations get
    a fresh cryptographically random password that is returned only in this
    result and the CLI's one JSON response.
    """

    _ensure_development()
    plaintext_password = (
        password if password is not None else secrets.token_urlsafe(32)
    )

    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                role_id, permissions = _appraiser_role_and_permissions(cursor)
                existing = _demo_user(cursor, for_update=True)
                encoded_password = hash_password(plaintext_password)
                if existing is None:
                    user_id = uuid4()
                    cursor.execute(
                        """
                        INSERT INTO auth.users (
                            user_id, username, email, password_hash, display_name,
                            is_active, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, true, now(), now())
                        """,
                        (
                            user_id,
                            DEMO_USERNAME,
                            DEMO_EMAIL,
                            encoded_password,
                            DEMO_DISPLAY_NAME,
                        ),
                    )
                else:
                    user_id = _ensure_owned_user(existing)
                    cursor.execute(
                        """
                        UPDATE auth.users
                        SET email = %s,
                            display_name = %s,
                            password_hash = %s,
                            is_active = true,
                            updated_at = now()
                        WHERE user_id = %s
                        """,
                        (
                            DEMO_EMAIL,
                            DEMO_DISPLAY_NAME,
                            encoded_password,
                            user_id,
                        ),
                    )

                # The Demo account must have exactly one role. This only
                # changes this user's links; role and permission definitions
                # remain migration-owned global data.
                cursor.execute(
                    "DELETE FROM auth.user_roles WHERE user_id = %s",
                    (user_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO auth.user_roles (user_id, role_id)
                    VALUES (%s, %s)
                    """,
                    (user_id, role_id),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        "command": "seed",
        "username": DEMO_USERNAME,
        "password": plaintext_password,
        "role": DEMO_ROLE,
        "permissions": permissions,
    }


def status() -> dict[str, object]:
    """Return safe account/permission status without a password field."""

    _ensure_development()
    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                row = _demo_user(cursor)
                if row is None:
                    connection.commit()
                    return {
                        "command": "status",
                        "username": DEMO_USERNAME,
                        "found": False,
                    }
                user_id = _ensure_owned_user(row)
                cursor.execute(
                    """
                    SELECT r.role_code, p.permission_code
                    FROM auth.user_roles AS ur
                    JOIN auth.roles AS r
                      ON r.role_id = ur.role_id AND r.is_active = true
                    JOIN auth.role_permissions AS rp ON rp.role_id = r.role_id
                    JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
                    WHERE ur.user_id = %s
                    ORDER BY r.role_code, p.permission_code
                    """,
                    (user_id,),
                )
                role_permissions = cursor.fetchall()
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    roles = sorted({row[0] for row in role_permissions})
    permissions = sorted({row[1] for row in role_permissions})
    return {
        "command": "status",
        "username": DEMO_USERNAME,
        "found": True,
        "is_active": row[3],
        "role": roles[0] if len(roles) == 1 else None,
        "roles": roles,
        "permissions": permissions,
    }


def reset() -> dict[str, object]:
    """Delete only the fixed Demo user and its user-role links."""

    _ensure_development()
    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                existing = _demo_user(cursor, for_update=True)
                if existing is None:
                    connection.commit()
                    return {"command": "reset", "removed": False}
                user_id = _ensure_owned_user(existing)
                cursor.execute(
                    "DELETE FROM auth.user_roles WHERE user_id = %s",
                    (user_id,),
                )
                cursor.execute(
                    "DELETE FROM auth.users WHERE user_id = %s",
                    (user_id,),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"command": "reset", "removed": True}


# Keep the existing Review Demo naming convention available to callers that
# use ``*_demo`` lifecycle helpers, while the command contract stays concise.
seed_demo = seed
reset_demo = reset
status_demo = status


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commands = {"seed": seed, "status": status, "reset": reset}
    try:
        result = commands[args.command]()
    except DemoError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    except Exception:
        # Do not echo exception details: a database error must never become a
        # way to log the one-time plaintext password or other connection data.
        print(
            json.dumps(
                {"ok": False, "error": "DEMO_COMMAND_FAILED"},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
