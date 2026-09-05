from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class FakeDatabase:
    def __init__(self) -> None:
        self.appraiser_role_id = UUID("11111111-1111-1111-1111-111111111111")
        self.roles = {
            "APPRAISER": {"role_id": self.appraiser_role_id, "is_active": True},
            "REVIEWER": {"role_id": UUID("22222222-2222-2222-2222-222222222222"), "is_active": True},
        }
        self.permissions = {
            "case.create",
            "case.read",
            "case.update",
            "valuation.read",
            "valuation.update",
            "valuation.submit_review",
            "document.upload",
            "document.download",
        }
        self.users: dict[str, dict[str, object]] = {}
        self.user_roles: set[tuple[UUID, UUID]] = set()
        self.commits = 0
        self.rollbacks = 0
        self.queries: list[str] = []

    def snapshot(self) -> tuple[dict[str, dict[str, object]], set[tuple[UUID, UUID]]]:
        return deepcopy(self.users), set(self.user_roles)

    def restore(self, snapshot) -> None:
        self.users, self.user_roles = snapshot


class FakeCursor:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database
        self.result: list[tuple[object, ...]] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params=()) -> None:
        normalized = " ".join(query.split()).lower()
        self.database.queries.append(normalized)
        self.result = []
        self.rowcount = 0

        if "select r.role_id" in normalized and "from auth.roles" in normalized:
            role = self.database.roles.get(params[0])
            if role and role["is_active"]:
                self.result = [(role["role_id"],)]
            return

        if "select p.permission_code" in normalized and "from auth.role_permissions" in normalized:
            role_id = params[0]
            if role_id == self.database.appraiser_role_id:
                self.result = [(code,) for code in sorted(self.database.permissions)]
            return

        if "select user_id, email, display_name, is_active" in normalized:
            user = self.database.users.get(params[0])
            if user:
                self.result = [
                    (
                        user["user_id"],
                        user["email"],
                        user["display_name"],
                        user["is_active"],
                    )
                ]
            return

        if "select r.role_code, p.permission_code" in normalized:
            user_id = params[0]
            role_ids = {role_id for linked_user_id, role_id in self.database.user_roles if linked_user_id == user_id}
            rows = []
            for role_code, role in self.database.roles.items():
                if role["role_id"] in role_ids and role["is_active"]:
                    for permission in sorted(self.database.permissions):
                        rows.append((role_code, permission))
            self.result = rows
            return

        if normalized.startswith("insert into auth.users"):
            user_id, username, email, password_hash, display_name = params
            self.database.users[username] = {
                "user_id": user_id,
                "email": email,
                "display_name": display_name,
                "password_hash": password_hash,
                "is_active": True,
            }
            self.rowcount = 1
            return

        if normalized.startswith("update auth.users"):
            email, display_name, password_hash, user_id = params
            for user in self.database.users.values():
                if user["user_id"] == user_id:
                    user.update(
                        email=email,
                        display_name=display_name,
                        password_hash=password_hash,
                        is_active=True,
                    )
                    self.rowcount = 1
                    return
            return

        if normalized.startswith("delete from auth.user_roles"):
            user_id = params[0]
            before = len(self.database.user_roles)
            self.database.user_roles = {
                item for item in self.database.user_roles if item[0] != user_id
            }
            self.rowcount = before - len(self.database.user_roles)
            return

        if normalized.startswith("insert into auth.user_roles"):
            user_id, role_id = params
            self.database.user_roles.add((user_id, role_id))
            self.rowcount = 1
            return

        if normalized.startswith("delete from auth.users"):
            user_id = params[0]
            username = next(
                username
                for username, user in self.database.users.items()
                if user["user_id"] == user_id
            )
            del self.database.users[username]
            self.rowcount = 1
            return

        raise AssertionError(f"unhandled SQL: {query}")

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return list(self.result)


class FakeConnection:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database
        self._transaction_snapshot = database.snapshot()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def cursor(self):
        return FakeCursor(self.database)

    def commit(self) -> None:
        self.database.commits += 1
        self._transaction_snapshot = self.database.snapshot()

    def rollback(self) -> None:
        self.database.rollbacks += 1
        self.database.restore(self._transaction_snapshot)

    def close(self) -> None:
        return None


@pytest.fixture
def demo_context(monkeypatch):
    from app.valuation import demo

    database = FakeDatabase()
    connections = []

    def connect():
        connection = FakeConnection(database)
        connections.append(connection)
        return connection

    monkeypatch.setattr(demo, "_connect", connect)
    monkeypatch.setattr(
        demo,
        "get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )
    return demo, database, connections


def test_module_contract_and_required_permissions():
    from app.valuation import demo

    assert demo.DEMO_USERNAME == "valuation_demo"
    assert demo.DEMO_EMAIL == "valuation_demo@local.invalid"
    assert demo.DEMO_DISPLAY_NAME == "Valuation Demo Appraiser"
    assert demo.REQUIRED_PERMISSIONS == {
        "case.create",
        "case.read",
        "case.update",
        "valuation.read",
        "valuation.update",
        "valuation.submit_review",
        "document.upload",
        "document.download",
    }
    assert set(demo.build_parser()._actions[-1].choices) == {"seed", "status", "reset"}


def test_seed_uses_hash_helper_and_does_not_persist_plaintext(monkeypatch, demo_context):
    demo, database, _connections = demo_context
    plaintext = "ValuationDemo123!"
    hashes = []

    def fake_hash(password: str) -> str:
        hashes.append(password)
        return "argon2-hash"

    monkeypatch.setattr(demo, "hash_password", fake_hash)

    result = demo.seed(password=plaintext)

    assert result == {
        "command": "seed",
        "username": "valuation_demo",
        "password": plaintext,
        "role": "APPRAISER",
        "permissions": sorted(database.permissions),
    }
    assert hashes == [plaintext]
    assert plaintext not in repr(database.users)
    user = database.users["valuation_demo"]
    assert user["password_hash"] == "argon2-hash"
    assert database.commits == 1


def test_seed_is_retry_safe_and_leaves_exactly_appraiser_role(monkeypatch, demo_context):
    demo, database, _connections = demo_context
    hashes = iter(("hash-1", "hash-2"))
    monkeypatch.setattr(demo, "hash_password", lambda _password: next(hashes))

    first = demo.seed(password="first")
    second = demo.seed(password="second")

    assert first["username"] == second["username"] == "valuation_demo"
    assert len(database.users) == 1
    user_id = database.users["valuation_demo"]["user_id"]
    assert database.user_roles == {(user_id, database.appraiser_role_id)}
    assert database.users["valuation_demo"]["password_hash"] == "hash-2"
    assert database.commits == 2


def test_seed_refuses_missing_role_or_permission_without_writes(demo_context):
    demo, database, connections = demo_context
    database.roles["APPRAISER"]["is_active"] = False

    with pytest.raises(demo.DemoError, match="APPRAISER_ROLE_MISSING"):
        demo.seed(password="unused")

    assert database.users == {}
    assert database.commits == 0
    assert len(connections) == 1
    assert database.rollbacks == 1

    database.roles["APPRAISER"]["is_active"] = True
    database.permissions.remove("document.download")
    with pytest.raises(demo.DemoError, match="APPRAISER_PERMISSIONS_MISSING"):
        demo.seed(password="unused")
    assert database.users == {}
    assert database.commits == 0


def test_status_never_exposes_password(demo_context):
    demo, database, _connections = demo_context
    database.users["valuation_demo"] = {
        "user_id": uuid4(),
        "email": demo.DEMO_EMAIL,
        "display_name": demo.DEMO_DISPLAY_NAME,
        "password_hash": "secret-hash",
        "is_active": True,
    }
    user_id = database.users["valuation_demo"]["user_id"]
    database.user_roles.add((user_id, database.appraiser_role_id))

    result = demo.status()

    assert "password" not in result
    assert "password_hash" not in result
    assert "secret-hash" not in repr(result)
    assert result["role"] == "APPRAISER"
    assert result["permissions"] == sorted(database.permissions)


def test_reset_removes_only_demo_user_and_role_link_and_is_retry_safe(
    monkeypatch, demo_context
):
    demo, database, _connections = demo_context
    monkeypatch.setattr(demo, "hash_password", lambda _password: "argon2-hash")
    demo.seed(password="unused")
    other_user_id = uuid4()
    database.users["other_user"] = {
        "user_id": other_user_id,
        "email": "other@example.test",
        "display_name": "Other User",
        "password_hash": "other-hash",
        "is_active": True,
    }
    reviewer_role_id = database.roles["REVIEWER"]["role_id"]
    database.user_roles.add((other_user_id, reviewer_role_id))

    result = demo.reset()

    assert result == {"command": "reset", "removed": True}
    assert set(database.users) == {"other_user"}
    assert database.user_roles == {(other_user_id, reviewer_role_id)}
    assert demo.reset() == {"command": "reset", "removed": False}


def test_seed_and_reset_refuse_non_development_before_connecting(monkeypatch):
    from app.valuation import demo

    calls = []
    monkeypatch.setattr(
        demo,
        "get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )
    monkeypatch.setattr(demo, "_connect", lambda: calls.append(True))

    with pytest.raises(demo.DemoError, match="DEVELOPMENT_ONLY"):
        demo.seed(password="unused")
    with pytest.raises(demo.DemoError, match="DEVELOPMENT_ONLY"):
        demo.reset()

    assert calls == []


def test_cli_prints_copyable_json_and_rejects_invalid_usage(monkeypatch, demo_context, capsys):
    demo, _database, _connections = demo_context
    monkeypatch.setattr(demo, "seed", lambda: {"command": "seed", "password": "once"})

    assert demo.main(["seed"]) == 0
    assert '"password": "once"' in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc_info:
        demo.main(["invalid"])
    assert exc_info.value.code != 0
