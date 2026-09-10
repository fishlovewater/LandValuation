"""Development-only permission-code role-link swaps for the Demo user."""

from __future__ import annotations

from contextlib import closing
from typing import Any

import psycopg

from app.core.config import get_settings

from .accounts import (
    ALLOWED_DYNAMIC_PERMISSIONS,
    APPRAISER,
    ASSISTANT_ROLE,
    ASSISTANT_ROLE_PERMISSIONS,
    DEMO_LIFECYCLE_LOCK_KEY,
    PERMISSION_TEST_ROLE,
    _acquire_lifecycle_lock,
    _assert_production_grants_unchanged,
    _ensure_owned_user,
    _permission_id,
    _role_links,
    _role_permission_entries,
    _role_row,
    _role_linked_usernames,
    _snapshot_production_grants,
    _user_row,
    _validate_demo_role_ownership,
)
from .contracts import DemoError

_ACTIONS = frozenset({"revoke", "restore"})


def validate_permission_code(permission_code: str) -> str:
    """Return one normalized, explicitly allowlisted permission code."""

    if not isinstance(permission_code, str):
        raise DemoError("UNSUPPORTED_DEMO_PERMISSION")
    normalized = permission_code.strip()
    if normalized not in ALLOWED_DYNAMIC_PERMISSIONS:
        raise DemoError("UNSUPPORTED_DEMO_PERMISSION")
    return normalized


def _validate_action(action: str) -> str:
    if not isinstance(action, str) or action not in _ACTIONS:
        raise DemoError("UNSUPPORTED_DEMO_ACTION")
    return action


def _owned_appraiser(cursor):
    row = _user_row(cursor, APPRAISER[0], for_update=True)
    if row is None:
        raise DemoError("DEMO_ACCOUNT_MISSING: valuation_demo")
    user_id = _ensure_owned_user(row, APPRAISER)
    return user_id


def _owned_role_ids(cursor):
    appraiser_row = _role_row(cursor, APPRAISER[3], for_update=False)
    if appraiser_row is None or not appraiser_row[3]:
        raise DemoError(f"DEMO_ROLE_MISSING: {APPRAISER[3]}")
    assistant_role_id = _validate_demo_role_ownership(cursor, ASSISTANT_ROLE, allow_missing=False)
    assistant_row = _role_row(cursor, ASSISTANT_ROLE[0], for_update=False)
    if assistant_row is None or not assistant_row[3]:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    return appraiser_row[0], assistant_role_id


def _effective_permission_codes(cursor, user_id) -> set[str]:
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
    return {row[1] for row in cursor.fetchall()}


def _permission_entries_by_code(entries: list[tuple[str, Any]]) -> dict[str, Any]:
    return {code: permission_id for code, permission_id in entries}


def _ensure_permission_test_role(cursor):
    role_id = _validate_demo_role_ownership(cursor, PERMISSION_TEST_ROLE)
    if role_id is not None:
        if not _role_row(cursor, PERMISSION_TEST_ROLE[0])[3]:
            cursor.execute(
                """
                UPDATE auth.roles
                SET role_name = %s, description = %s, is_active = true,
                    updated_at = now()
                WHERE role_id = %s
                """,
                (PERMISSION_TEST_ROLE[1], PERMISSION_TEST_ROLE[2], role_id),
            )
        return role_id
    role_code, role_name, description = PERMISSION_TEST_ROLE
    cursor.execute(
        """
        INSERT INTO auth.roles (
            role_code, role_name, description, is_active, created_at, updated_at
        ) VALUES (%s, %s, %s, true, now(), now())
        RETURNING role_id
        """,
        (role_code, role_name, description),
    )
    row = cursor.fetchone()
    if row is None:
        raise DemoError("DEMO_ROLE_CREATE_FAILED: DEMO_PERMISSION_TEST_APPRAISER")
    return row[0]


def _assert_no_unexpected_target_grant(cursor, user_id, appraiser_role_id, assistant_role_id, target):
    """Reject a third linked role that would defeat additive-RBAC revoke."""

    links = _role_links(cursor, user_id)
    for role_id in links - {appraiser_role_id, assistant_role_id}:
        if target in {code for code, _permission_id_value in _role_permission_entries(cursor, role_id)}:
            raise DemoError("PERMISSION_REVOKE_INEFFECTIVE")


def _revoke(cursor, permission_code: str) -> dict[str, object]:
    user_id = _owned_appraiser(cursor)
    appraiser_role_id, assistant_role_id = _owned_role_ids(cursor)
    links = _role_links(cursor, user_id)
    test_role_id = _validate_demo_role_ownership(cursor, PERMISSION_TEST_ROLE)
    if appraiser_role_id not in links or assistant_role_id not in links:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    if test_role_id is not None and test_role_id in links:
        raise DemoError("PERMISSION_STATE_MISMATCH")

    appraiser_entries = _role_permission_entries(cursor, appraiser_role_id)
    appraiser_by_code = _permission_entries_by_code(appraiser_entries)
    if permission_code not in appraiser_by_code:
        raise DemoError("PERMISSION_NOT_GRANTED")

    assistant_codes = {
        code for code, _permission_id_value in _role_permission_entries(cursor, assistant_role_id)
    }
    if permission_code in assistant_codes:
        raise DemoError("PERMISSION_REVOKE_INEFFECTIVE")
    if assistant_codes != set(ASSISTANT_ROLE_PERMISSIONS):
        raise DemoError("PERMISSION_STATE_MISMATCH")

    # This read happens before the first mutation, so a third role cannot leave
    # a partially-swapped account if the requested revoke is ineffective.
    _assert_no_unexpected_target_grant(
        cursor, user_id, appraiser_role_id, assistant_role_id, permission_code
    )

    test_role_id = _ensure_permission_test_role(cursor)
    cursor.execute("DELETE FROM auth.role_permissions WHERE role_id = %s", (test_role_id,))
    for code, permission_id in appraiser_entries:
        if code == permission_code:
            continue
        cursor.execute(
            """
            INSERT INTO auth.role_permissions (role_id, permission_id)
            VALUES (%s, %s)
            """,
            (test_role_id, permission_id),
        )

    cursor.execute(
        """
        DELETE FROM auth.user_roles
        WHERE user_id = %s AND role_id = %s
        """,
        (user_id, appraiser_role_id),
    )
    if cursor.rowcount != 1:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    cursor.execute(
        """
        INSERT INTO auth.user_roles (user_id, role_id)
        VALUES (%s, %s)
        """,
        (user_id, test_role_id),
    )

    if permission_code in _effective_permission_codes(cursor, user_id):
        raise DemoError("PERMISSION_REVOKE_INEFFECTIVE")
    return {
        "command": "permission",
        "action": "revoke",
        "permission_code": permission_code,
        "username": APPRAISER[0],
        "role": PERMISSION_TEST_ROLE[0],
    }


def _restore(cursor, permission_code: str) -> dict[str, object]:
    user_id = _owned_appraiser(cursor)
    appraiser_role_id, assistant_role_id = _owned_role_ids(cursor)
    test_role_id = _validate_demo_role_ownership(cursor, PERMISSION_TEST_ROLE, allow_missing=False)
    test_role = _role_row(cursor, PERMISSION_TEST_ROLE[0])
    if test_role is None or not test_role[3]:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    links = _role_links(cursor, user_id)
    if links != {assistant_role_id, test_role_id}:
        raise DemoError("PERMISSION_STATE_MISMATCH")

    appraiser_entries = _role_permission_entries(cursor, appraiser_role_id)
    appraiser_by_code = _permission_entries_by_code(appraiser_entries)
    if permission_code not in appraiser_by_code:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    expected_test_entries = {
        code: permission_id
        for code, permission_id in appraiser_by_code.items()
        if code != permission_code
    }
    actual_test_entries = _role_permission_entries(cursor, test_role_id)
    if _permission_entries_by_code(actual_test_entries) != expected_test_entries:
        raise DemoError("PERMISSION_STATE_MISMATCH")

    assistant_codes = {
        code for code, _permission_id_value in _role_permission_entries(cursor, assistant_role_id)
    }
    if assistant_codes != set(ASSISTANT_ROLE_PERMISSIONS):
        raise DemoError("PERMISSION_STATE_MISMATCH")

    cursor.execute(
        "INSERT INTO auth.user_roles (user_id, role_id) VALUES (%s, %s)",
        (user_id, appraiser_role_id),
    )
    cursor.execute(
        """
        DELETE FROM auth.user_roles
        WHERE user_id = %s AND role_id = %s
        """,
        (user_id, test_role_id),
    )
    if cursor.rowcount != 1:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    if _role_linked_usernames(cursor, test_role_id):
        raise DemoError("PERMISSION_STATE_MISMATCH")
    cursor.execute("DELETE FROM auth.role_permissions WHERE role_id = %s", (test_role_id,))
    cursor.execute("DELETE FROM auth.roles WHERE role_id = %s", (test_role_id,))

    if _role_links(cursor, user_id) != {assistant_role_id, appraiser_role_id}:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    return {
        "command": "permission",
        "action": "restore",
        "permission_code": permission_code,
        "username": APPRAISER[0],
        "role": APPRAISER[3],
    }


def change_permission(cursor, action: str, permission_code: str) -> dict[str, object]:
    """Atomically swap the owned APPRAISER role link for one allowed code."""

    action = _validate_action(action)
    permission_code = validate_permission_code(permission_code)
    _acquire_lifecycle_lock(cursor)
    before = _snapshot_production_grants(cursor)
    if action == "revoke":
        result = _revoke(cursor, permission_code)
    else:
        result = _restore(cursor, permission_code)
    _assert_production_grants_unchanged(cursor, before)
    return result


def _connect():
    settings = get_settings()
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )


def _ensure_development() -> None:
    if get_settings().app_env != "development":
        raise DemoError("DEVELOPMENT_ONLY: demo commands require APP_ENV=development")


def permission_command(action: str, permission_code: str) -> dict[str, object]:
    """CLI adapter; account/lifecycle seed remains a separate future path."""

    _ensure_development()
    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                result = change_permission(cursor, action, permission_code)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return result


# A concise alias is useful to the composition root without exposing any
# account-seed path as a second public command.
permission = permission_command


__all__ = [
    "ALLOWED_DYNAMIC_PERMISSIONS",
    "ASSISTANT_ROLE_PERMISSIONS",
    "DEMO_LIFECYCLE_LOCK_KEY",
    "DemoError",
    "validate_permission_code",
    "change_permission",
    "permission_command",
    "permission",
]
