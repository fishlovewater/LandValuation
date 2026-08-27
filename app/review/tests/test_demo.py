from types import SimpleNamespace
from uuid import uuid4

import pytest


def test_demo_cli_rejects_non_development(monkeypatch, capsys):
    from app.review import demo

    monkeypatch.setattr(
        demo,
        "get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )

    assert demo.main(["seed"]) == 2
    payload = capsys.readouterr().out
    assert "DEVELOPMENT_ONLY" in payload


def test_demo_ownership_constants_are_fixed():
    from app.review import demo

    assert demo.DEMO_USERNAME == "review_demo"
    assert demo.DEMO_CASE_NO == "DEMO-REVIEW-001"
    assert demo.DEMO_RULE_SET_CODE == "DEMO-REVIEW-RULES"
    assert demo.DEMO_KNOWLEDGE_CODE == "DEMO-REVIEW-SOURCE"
    assert demo.DEMO_DISTRICT_CODE == "DEMO-F01"


def test_demo_pdf_is_a_real_pdf():
    from app.review.demo import build_demo_pdf

    content = build_demo_pdf("Demo review source")

    assert content.startswith(b"%PDF-")
    assert len(content) > 500


@pytest.mark.parametrize("command", ["seed", "revise", "reset"])
def test_demo_commands_are_exposed(command):
    from app.review.demo import build_parser

    assert build_parser().parse_args([command]).command == command


def test_seed_compensates_objects_when_upload_fails(monkeypatch):
    from app.review import demo

    uploaded = {
        "bucket_name": "land-valuation",
        "object_key": "cases/demo/first.pdf",
        "checksum_sha256": "a" * 64,
        "file_size_bytes": 100,
        "storage_etag": "etag",
    }
    calls = 0
    removed = []

    monkeypatch.setattr(demo, "reset_demo", lambda: {"removed": False})

    def fail_second_upload(*_args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated upload failure")
        return uploaded

    monkeypatch.setattr(demo, "_upload_pdf", fail_second_upload)
    monkeypatch.setattr(demo, "_remove_objects", lambda keys: removed.extend(keys))

    with pytest.raises(RuntimeError, match="simulated upload failure"):
        demo.seed_demo()

    assert removed == [uploaded["object_key"]]


def test_reset_rejects_username_collision(postgres_connection):
    from app.review.demo import DEMO_USERNAME, DemoError, reset_demo

    reset_demo()
    user_id = uuid4()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'unused', 'Not Demo', true, now(), now())
            """,
            (user_id, DEMO_USERNAME, f"{user_id}@example.test"),
        )
    postgres_connection.commit()
    try:
        with pytest.raises(DemoError, match="OWNERSHIP_COLLISION"):
            reset_demo()
        with postgres_connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM auth.users WHERE user_id = %s", (user_id,))
            assert cursor.fetchone()[0] == 1
    finally:
        with postgres_connection.cursor() as cursor:
            cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
        postgres_connection.commit()
