"""Owned development Demo accounts and their auth-role links.

This module deliberately consumes a caller-owned psycopg cursor.  The caller
owns the transaction boundary; every mutating helper takes the same advisory
lock and leaves commit/rollback to that boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.security import hash_password

from .contracts import DemoError, DemoIdentity

ALLOWED_DYNAMIC_PERMISSIONS = frozenset({"knowledge.read", "case.read"})
ASSISTANT_ROLE_PERMISSIONS = frozenset({"assistant.use"})
DEMO_PASSWORD = "Demo1234!"

APPRAISER = (
    "valuation_demo",
    "valuation_demo@local.invalid",
    "Valuation Demo Appraiser",
    "APPRAISER",
)
REVIEWER = (
    "review_demo",
    "review_demo@local.invalid",
    "Review Demo Reviewer",
    "REVIEWER",
)
INSPECTOR = (
    "inspector_demo",
    "inspector_demo@local.invalid",
    "Persistent Demo Inspector",
    "INSPECTOR",
)
ASSISTANT_ROLE = (
    "DEMO_ASSISTANT_APPRAISER",
    "Valuation Demo Assistant Appraiser",
    "Development-only companion role owned by app.demo; grants assistant.use only",
)
# Keep the legacy companion-role code/name for existing persistent Demo
# databases, but link it to every owned Demo persona.  The role still grants
# only ``assistant.use`` and never changes the production APPRAISER/REVIEWER/
# INSPECTOR permission sets.
ASSISTANT_ROLE_USERNAMES = frozenset({APPRAISER[0], REVIEWER[0], INSPECTOR[0]})
PERMISSION_TEST_ROLE = (
    "DEMO_PERMISSION_TEST_APPRAISER",
    "Valuation Demo Permission Test Appraiser",
    "Development-only transient role owned by app.demo permission lifecycle",
)
DEMO_LIFECYCLE_LOCK_KEY = 2026090802

_ACCOUNT_DEFINITIONS = (APPRAISER, REVIEWER, INSPECTOR)


@dataclass(frozen=True)
class DemoAccounts:
    """The one-time credentials and IDs created by :func:`seed_accounts`.

    Passwords are intentionally present only in this returned in-memory
    object.  Database rows contain only the hashes produced by
    ``app.core.security.hash_password``.
    """

    appraiser: DemoIdentity
    reviewer: DemoIdentity
    inspector: DemoIdentity
    user_ids: dict[str, UUID]
    role_ids: dict[str, UUID]

    @property
    def identities(self) -> tuple[DemoIdentity, DemoIdentity, DemoIdentity]:
        return self.appraiser, self.reviewer, self.inspector

    @property
    def appraiser_user_id(self) -> UUID:
        return self.user_ids[self.appraiser.username]

    @property
    def reviewer_user_id(self) -> UUID:
        return self.user_ids[self.reviewer.username]

    @property
    def inspector_user_id(self) -> UUID:
        return self.user_ids[self.inspector.username]


def _acquire_lifecycle_lock(cursor) -> None:
    cursor.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (DEMO_LIFECYCLE_LOCK_KEY,),
    )


def _role_row(cursor, role_code: str, *, for_update: bool = False):
    lock_clause = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT role_id, role_name, description, is_active
        FROM auth.roles
        WHERE role_code = %s{lock_clause}
        """,
        (role_code,),
    )
    return cursor.fetchone()


def _user_row(cursor, username: str, *, for_update: bool = False):
    lock_clause = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT user_id, email, display_name, is_active
        FROM auth.users
        WHERE username = %s{lock_clause}
        """,
        (username,),
    )
    return cursor.fetchone()


def _ensure_owned_user(row, definition: tuple[str, str, str, str]) -> UUID:
    username, email, display_name, _role_code = definition
    if row[1] != email or row[2] != display_name:
        raise DemoError(f"OWNERSHIP_COLLISION: auth.users.username={username}")
    return row[0]


def _ensure_owned_role(row, definition: tuple[str, str, str]) -> UUID:
    role_code, role_name, description = definition
    if row[1] != role_name or row[2] != description:
        raise DemoError(f"OWNERSHIP_COLLISION: auth.roles.role_code={role_code}")
    return row[0]


def _role_permission_entries(cursor, role_id: UUID) -> list[tuple[str, UUID]]:
    """Return ``(permission_code, permission_id)`` pairs for one role.

    The two-column query keeps the code and immutable ID together.  The small
    fallback handles focused fake cursors that expose only the code column.
    """

    cursor.execute(
        """
        SELECT p.permission_code, p.permission_id
        FROM auth.role_permissions AS rp
        JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
        WHERE rp.role_id = %s
        ORDER BY p.permission_code
        """,
        (role_id,),
    )
    rows = cursor.fetchall()
    entries: list[tuple[str, UUID]] = []
    for row in rows:
        code = row[0]
        permission_id = row[1] if len(row) > 1 else None
        if permission_id is None:
            cursor.execute(
                """
                SELECT permission_id
                FROM auth.permissions
                WHERE permission_code = %s
                """,
                (code,),
            )
            permission_row = cursor.fetchone()
            if permission_row is None:
                raise DemoError(f"DEMO_PERMISSION_MISSING: {code}")
            permission_id = permission_row[0]
        entries.append((code, permission_id))
    return entries


def _role_permission_map(cursor, role_id: UUID) -> dict[str, UUID]:
    return {
        code: permission_id
        for code, permission_id in _role_permission_entries(cursor, role_id)
    }


def _permission_id(cursor, permission_code: str) -> UUID:
    cursor.execute(
        """
        SELECT permission_id
        FROM auth.permissions
        WHERE permission_code = %s
        """,
        (permission_code,),
    )
    row = cursor.fetchone()
    if row is None:
        raise DemoError(f"DEMO_PERMISSION_MISSING: {permission_code}")
    return row[0]


def _role_links(cursor, user_id: UUID) -> set[UUID]:
    cursor.execute(
        """
        SELECT ur.role_id
        FROM auth.user_roles AS ur
        WHERE ur.user_id = %s
        ORDER BY ur.role_id
        """,
        (user_id,),
    )
    return {row[0] for row in cursor.fetchall()}


def _role_linked_usernames(cursor, role_id: UUID, *, exclude: str | None = None) -> list[str]:
    if exclude is None:
        cursor.execute(
            """
            SELECT u.username
            FROM auth.user_roles AS ur
            JOIN auth.users AS u ON u.user_id = ur.user_id
            WHERE ur.role_id = %s
            ORDER BY u.username
            """,
            (role_id,),
        )
    else:
        cursor.execute(
            """
            SELECT u.username
            FROM auth.user_roles AS ur
            JOIN auth.users AS u ON u.user_id = ur.user_id
            WHERE ur.role_id = %s AND u.username <> %s
            ORDER BY u.username
            """,
            (role_id, exclude),
        )
    return [row[0] for row in cursor.fetchall()]


def _snapshot_production_grants(cursor) -> dict[str, frozenset[UUID]]:
    snapshot: dict[str, frozenset[UUID]] = {}
    for _username, _email, _display_name, role_code in _ACCOUNT_DEFINITIONS:
        row = _role_row(cursor, role_code)
        if row is None or not row[3]:
            raise DemoError(f"DEMO_ROLE_MISSING: {role_code}")
        snapshot[role_code] = frozenset(
            permission_id for _code, permission_id in _role_permission_entries(cursor, row[0])
        )
    return snapshot


def _assert_production_grants_unchanged(cursor, before: dict[str, frozenset[UUID]]) -> None:
    after = _snapshot_production_grants(cursor)
    if after != before:
        raise DemoError("PRODUCTION_ROLE_GRANTS_CHANGED")


def _validate_demo_role_ownership(cursor, definition: tuple[str, str, str], *, allow_missing: bool = True):
    role_code, _role_name, _description = definition
    row = _role_row(cursor, role_code, for_update=True)
    if row is None:
        if allow_missing:
            return None
        raise DemoError(f"DEMO_ROLE_MISSING: {role_code}")
    role_id = _ensure_owned_role(row, definition)
    linked = _role_linked_usernames(cursor, role_id)
    allowed = ASSISTANT_ROLE_USERNAMES if definition == ASSISTANT_ROLE else {APPRAISER[0]}
    if any(username not in allowed for username in linked):
        raise DemoError(f"OWNERSHIP_COLLISION: auth.roles.role_code={role_code}")
    return role_id


def _validate_ownership(cursor, *, require_formal_roles: bool = True):
    formal_role_ids: dict[str, UUID] = {}
    for _username, _email, _display_name, role_code in _ACCOUNT_DEFINITIONS:
        row = _role_row(cursor, role_code, for_update=False)
        if row is None or not row[3]:
            if require_formal_roles:
                raise DemoError(f"DEMO_ROLE_MISSING: {role_code}")
            continue
        formal_role_ids[role_code] = row[0]

    users: dict[str, tuple[object, ...] | None] = {}
    for definition in _ACCOUNT_DEFINITIONS:
        username = definition[0]
        row = _user_row(cursor, username, for_update=True)
        if row is not None:
            _ensure_owned_user(row, definition)
        users[username] = row

    assistant_role_id = _validate_demo_role_ownership(cursor, ASSISTANT_ROLE)
    permission_test_role_id = _validate_demo_role_ownership(cursor, PERMISSION_TEST_ROLE)

    # A refresh/reset may delete only links owned by this lifecycle.  Extra
    # links are treated as a collision before any destructive statement.
    allowed_links = {
        APPRAISER[0]: {formal_role_ids.get("APPRAISER"), assistant_role_id, permission_test_role_id},
        REVIEWER[0]: {formal_role_ids.get("REVIEWER"), assistant_role_id},
        INSPECTOR[0]: {formal_role_ids.get("INSPECTOR"), assistant_role_id},
    }
    for username, row in users.items():
        if row is None:
            continue
        links = _role_links(cursor, row[0])
        expected = {role_id for role_id in allowed_links[username] if role_id is not None}
        if not links.issubset(expected):
            raise DemoError(f"OWNERSHIP_COLLISION: auth.users.username={username}")

    return formal_role_ids, users, assistant_role_id, permission_test_role_id


def _validate_owned_demo_role_state(
    cursor,
    formal_role_ids: dict[str, UUID],
    users: dict[str, tuple[object, ...] | None],
    assistant_role_id: UUID | None,
    permission_test_role_id: UUID | None,
) -> None:
    """Prove Demo role grants before any reset/seed cleanup can mutate them."""

    if assistant_role_id is not None:
        expected_assistant = {
            permission_code: _permission_id(cursor, permission_code)
            for permission_code in ASSISTANT_ROLE_PERMISSIONS
        }
        if _role_permission_map(cursor, assistant_role_id) != expected_assistant:
            raise DemoError("PERMISSION_STATE_MISMATCH")

    if permission_test_role_id is None:
        return

    if assistant_role_id is None:
        raise DemoError("PERMISSION_STATE_MISMATCH")

    test_role = _role_row(cursor, PERMISSION_TEST_ROLE[0])
    if test_role is None or not test_role[3]:
        raise DemoError("PERMISSION_STATE_MISMATCH")

    appraiser_permissions = _role_permission_map(
        cursor, formal_role_ids[APPRAISER[3]]
    )
    test_permissions = _role_permission_map(cursor, permission_test_role_id)
    missing = set(appraiser_permissions) - set(test_permissions)
    expected_test_codes = set(appraiser_permissions) - missing
    if (
        len(missing) != 1
        or not missing.issubset(ALLOWED_DYNAMIC_PERMISSIONS)
        or set(test_permissions) != expected_test_codes
        or any(
            test_permissions[code] != appraiser_permissions[code]
            for code in expected_test_codes
        )
    ):
        raise DemoError("PERMISSION_STATE_MISMATCH")

    linked_usernames = set(_role_linked_usernames(cursor, permission_test_role_id))
    if linked_usernames - {APPRAISER[0]}:
        raise DemoError("PERMISSION_STATE_MISMATCH")
    appraiser_row = users.get(APPRAISER[0])
    if appraiser_row is None:
        if linked_usernames:
            raise DemoError("PERMISSION_STATE_MISMATCH")
        return
    appraiser_links = _role_links(cursor, appraiser_row[0])
    if (
        permission_test_role_id not in appraiser_links
        or assistant_role_id not in appraiser_links
        or formal_role_ids[APPRAISER[3]] in appraiser_links
    ):
        raise DemoError("PERMISSION_STATE_MISMATCH")


def _normalise_passwords(passwords: Mapping[str, str] | Sequence[str] | None) -> dict[str, str]:
    usernames = (APPRAISER[0], REVIEWER[0], INSPECTOR[0])
    if passwords is None:
        return dict.fromkeys(usernames, DEMO_PASSWORD)
    if isinstance(passwords, Mapping):
        values = {
            username: passwords.get(username, passwords.get(role_code))
            for username, _email, _display_name, role_code in _ACCOUNT_DEFINITIONS
        }
        if any(not isinstance(value, str) or not value for value in values.values()):
            raise DemoError("DEMO_PASSWORDS_INVALID")
        return values  # type: ignore[return-value]
    if isinstance(passwords, (str, bytes)) or len(passwords) != len(usernames):
        raise DemoError("DEMO_PASSWORDS_INVALID")
    values = dict(zip(usernames, passwords, strict=True))
    if any(not isinstance(value, str) or not value for value in values.values()):
        raise DemoError("DEMO_PASSWORDS_INVALID")
    return values


def _ensure_role(cursor, definition: tuple[str, str, str]) -> UUID:
    role_code, role_name, description = definition
    row = _role_row(cursor, role_code, for_update=True)
    if row is not None:
        role_id = _ensure_owned_role(row, definition)
        if not row[3]:
            cursor.execute(
                """
                UPDATE auth.roles
                SET role_name = %s, description = %s, is_active = true,
                    updated_at = now()
                WHERE role_id = %s
                """,
                (definition[1], definition[2], role_id),
            )
        return role_id
    cursor.execute(
        """
        INSERT INTO auth.roles (
            role_code, role_name, description, is_active, created_at, updated_at
        ) VALUES (%s, %s, %s, true, now(), now())
        RETURNING role_id
        """,
        (role_code, role_name, description),
    )
    inserted = cursor.fetchone()
    if inserted is None:
        raise DemoError(f"DEMO_ROLE_CREATE_FAILED: {role_code}")
    return inserted[0]


def _ensure_user(cursor, definition: tuple[str, str, str, str], password: str) -> tuple[UUID, DemoIdentity]:
    username, email, display_name, _role_code = definition
    existing = _user_row(cursor, username, for_update=True)
    encoded_password = hash_password(password)
    if existing is None:
        user_id = uuid4()
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, true, now(), now())
            """,
            (user_id, username, email, encoded_password, display_name),
        )
    else:
        user_id = _ensure_owned_user(existing, definition)
        cursor.execute(
            """
            UPDATE auth.users
            SET email = %s, display_name = %s, password_hash = %s,
                is_active = true, updated_at = now()
            WHERE user_id = %s
            """,
            (email, display_name, encoded_password, user_id),
        )
    return user_id, DemoIdentity(username=username, password=password)


def _set_companion_permissions(cursor, role_id: UUID) -> None:
    permission_id = _permission_id(cursor, "assistant.use")
    cursor.execute("DELETE FROM auth.role_permissions WHERE role_id = %s", (role_id,))
    cursor.execute(
        """
        INSERT INTO auth.role_permissions (role_id, permission_id)
        VALUES (%s, %s)
        """,
        (role_id, permission_id),
    )


def _remove_owned_role(cursor, role_id: UUID | None, definition: tuple[str, str, str]) -> bool:
    if role_id is None:
        return False
    role_code, _role_name, _description = definition
    if _role_linked_usernames(cursor, role_id):
        raise DemoError(f"OWNERSHIP_COLLISION: auth.roles.role_code={role_code}")
    cursor.execute("DELETE FROM auth.role_permissions WHERE role_id = %s", (role_id,))
    cursor.execute("DELETE FROM auth.roles WHERE role_id = %s", (role_id,))
    return True


def seed_accounts(
    cursor,
    passwords: Mapping[str, str] | Sequence[str] | None = None,
) -> DemoAccounts:
    """Create/refresh the three owned users and their role links.

    The function intentionally does not commit.  A future integrated seed can
    compose it with case/Knowledge writes in one transaction.
    """

    _acquire_lifecycle_lock(cursor)
    before = _snapshot_production_grants(cursor)
    formal_role_ids, existing_users, assistant_role_id, permission_test_role_id = _validate_ownership(cursor)
    _validate_owned_demo_role_state(
        cursor,
        formal_role_ids,
        existing_users,
        assistant_role_id,
        permission_test_role_id,
    )
    password_values = _normalise_passwords(passwords)

    # Re-run owned-role validation for the existing companion so an inactive
    # but correctly owned role is safely reactivated before it is linked.
    assistant_role_id = _ensure_role(cursor, ASSISTANT_ROLE)
    _set_companion_permissions(cursor, assistant_role_id)

    assistant_row = _role_row(cursor, ASSISTANT_ROLE[0])
    assistant_codes = {
        code
        for code, _permission_id_value in _role_permission_entries(
            cursor, assistant_role_id
        )
    }
    if (
        assistant_row is None
        or not assistant_row[3]
        or assistant_codes != set(ASSISTANT_ROLE_PERMISSIONS)
    ):
        raise DemoError("PERMISSION_STATE_MISMATCH")

    user_ids: dict[str, UUID] = {}
    identities: dict[str, DemoIdentity] = {}
    for definition in _ACCOUNT_DEFINITIONS:
        username = definition[0]
        user_id, identity = _ensure_user(cursor, definition, password_values[username])
        user_ids[username] = user_id
        identities[username] = identity

    for definition in _ACCOUNT_DEFINITIONS:
        username, _email, _display_name, role_code = definition
        user_id = user_ids[username]
        cursor.execute("DELETE FROM auth.user_roles WHERE user_id = %s", (user_id,))
        cursor.execute(
            """
            INSERT INTO auth.user_roles (user_id, role_id)
            VALUES (%s, %s), (%s, %s)
            """,
            (user_id, formal_role_ids[role_code], user_id, assistant_role_id),
        )
        links = _role_links(cursor, user_id)
        if formal_role_ids[role_code] not in links or assistant_role_id not in links:
            raise DemoError("PERMISSION_STATE_MISMATCH")

    # A fresh seed returns the normal APPRAISER state and removes the transient
    # permission-test role only after all ownership checks have passed.
    if permission_test_role_id is not None:
        _remove_owned_role(cursor, permission_test_role_id, PERMISSION_TEST_ROLE)

    _assert_production_grants_unchanged(cursor, before)
    return DemoAccounts(
        appraiser=identities[APPRAISER[0]],
        reviewer=identities[REVIEWER[0]],
        inspector=identities[INSPECTOR[0]],
        user_ids=user_ids,
        role_ids={
            "APPRAISER": formal_role_ids["APPRAISER"],
            "REVIEWER": formal_role_ids["REVIEWER"],
            "INSPECTOR": formal_role_ids["INSPECTOR"],
            ASSISTANT_ROLE[0]: assistant_role_id,
        },
    )


def _account_status(cursor, definition: tuple[str, str, str, str]) -> dict[str, object]:
    username, email, display_name, _role_code = definition
    row = _user_row(cursor, username)
    if row is None:
        return {"username": username, "found": False, "roles": [], "permissions": []}
    user_id = _ensure_owned_user(row, definition)
    cursor.execute(
        """
        SELECT r.role_code, p.permission_code
        FROM auth.user_roles AS ur
        JOIN auth.roles AS r ON r.role_id = ur.role_id AND r.is_active = true
        JOIN auth.role_permissions AS rp ON rp.role_id = r.role_id
        JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
        WHERE ur.user_id = %s
        ORDER BY r.role_code, p.permission_code
        """,
        (user_id,),
    )
    pairs = cursor.fetchall()
    return {
        "username": username,
        "found": True,
        "is_active": row[3],
        "roles": sorted({pair[0] for pair in pairs}),
        "permissions": sorted({pair[1] for pair in pairs}),
    }


def account_status(cursor) -> dict[str, object]:
    """Return safe status for all three owned accounts without secrets."""

    _acquire_lifecycle_lock(cursor)
    users = {
        definition[0]: _account_status(cursor, definition)
        for definition in _ACCOUNT_DEFINITIONS
    }
    return {
        "command": "status",
        "ready": all(
            bool(value.get("found")) and bool(value.get("is_active"))
            for value in users.values()
        ),
        "users": users,
    }


def reset_accounts(cursor) -> None:
    """Delete only owned users, links, and development-owned roles."""

    _acquire_lifecycle_lock(cursor)
    before = _snapshot_production_grants(cursor)
    formal_role_ids, users, assistant_role_id, permission_test_role_id = _validate_ownership(
        cursor, require_formal_roles=True
    )
    _validate_owned_demo_role_state(
        cursor,
        formal_role_ids,
        users,
        assistant_role_id,
        permission_test_role_id,
    )

    for definition in _ACCOUNT_DEFINITIONS:
        row = users[definition[0]]
        if row is None:
            continue
        user_id = row[0]
        cursor.execute("DELETE FROM auth.user_roles WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))

    _remove_owned_role(cursor, assistant_role_id, ASSISTANT_ROLE)
    _remove_owned_role(cursor, permission_test_role_id, PERMISSION_TEST_ROLE)
    _assert_production_grants_unchanged(cursor, before)


__all__ = [
    "ALLOWED_DYNAMIC_PERMISSIONS",
    "ASSISTANT_ROLE_PERMISSIONS",
    "DEMO_PASSWORD",
    "APPRAISER",
    "REVIEWER",
    "INSPECTOR",
    "ASSISTANT_ROLE",
    "ASSISTANT_ROLE_USERNAMES",
    "PERMISSION_TEST_ROLE",
    "DEMO_LIFECYCLE_LOCK_KEY",
    "DemoAccounts",
    "seed_accounts",
    "account_status",
    "reset_accounts",
    "_acquire_lifecycle_lock",
    "_role_row",
    "_user_row",
    "_ensure_owned_user",
    "_ensure_owned_role",
    "_role_permission_entries",
    "_role_permission_map",
    "_permission_id",
    "_role_links",
    "_role_linked_usernames",
    "_snapshot_production_grants",
    "_assert_production_grants_unchanged",
    "_validate_demo_role_ownership",
    "_validate_ownership",
    "_validate_owned_demo_role_state",
]
