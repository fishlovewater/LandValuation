import inspect

import pytest

from app.history import demo


def test_demo_ids_are_unique():
    assert len(set(demo.CASE_IDS)) == 3
    assert len(set(demo.DOCUMENT_IDS)) == 5
    assert len(set(demo.REVIEW_IDS)) == 2
    assert len(set(demo.USER_IDS)) == 2
    assert len(set(demo.EXTRACTION_IDS)) == 2
    assert len(set(demo.EXTRACTED_FIELD_IDS)) == 2


def test_demo_users_cover_the_two_history_roles():
    assert {user["username"] for user in demo.DEMO_USERS} == {
        "history_appraiser",
        "history_reviewer",
    }
    assert {user["role_code"] for user in demo.DEMO_USERS} == {
        "APPRAISER",
        "REVIEWER",
    }
    assert all(user["user_id"] in demo.USER_IDS for user in demo.DEMO_USERS)


def test_missing_object_is_distinct_from_downloadable_object():
    assert demo.MISSING_OBJECT_KEY != demo.DOWNLOAD_OBJECT_KEY
    assert demo.MISSING_OBJECT_KEY.endswith("history-demo-missing.docx")
    assert demo.DOWNLOAD_OBJECT_KEY.endswith("history-demo-report.pdf")


def test_rich_demo_documents_cover_word_excel_and_version_history():
    assert len(set(demo.UPLOAD_OBJECT_KEYS)) == 4
    assert demo.DOCX_OBJECT_KEY in demo.UPLOAD_OBJECT_KEYS
    assert demo.XLSX_V1_OBJECT_KEY in demo.UPLOAD_OBJECT_KEYS
    assert demo.XLSX_V2_OBJECT_KEY in demo.UPLOAD_OBJECT_KEYS
    assert demo.XLSX_V1_OBJECT_KEY != demo.XLSX_V2_OBJECT_KEY
    seed_source = inspect.getsource(demo.seed)
    assert "_build_docx_bytes()" in seed_source
    assert "_build_xlsx_bytes(1, 120000)" in seed_source
    assert "_build_xlsx_bytes(2, 125000)" in seed_source


def test_downloadable_both_case_is_seeded_as_review_report():
    source = "".join(inspect.getsource(demo.seed).split())

    assert (
        "(:did,:did,:both,'review-report','history-demo-report.pdf','application/pdf',"
        in source
    )


def test_demo_cli_uses_psycopg_compatible_windows_event_loop():
    source = inspect.getsource(demo.run_cli)

    assert 'sys.platform == "win32"' in source
    assert "WindowsSelectorEventLoopPolicy" in source


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ("seed", "reset"))
async def test_mutating_demo_commands_require_development(monkeypatch, command):
    monkeypatch.setenv("APP_ENV", "production")
    calls = []
    monkeypatch.setattr(
        demo,
        "_database_runtime",
        lambda: calls.append("database"),
    )
    monkeypatch.setattr(
        demo,
        "_minio_client",
        lambda: calls.append("minio"),
    )

    with pytest.raises(RuntimeError, match="DEVELOPMENT_ONLY"):
        await getattr(demo, command)()

    assert calls == []


@pytest.mark.asyncio
async def test_reset_propagates_minio_failure(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")

    class SessionContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def begin(self):
            return self

    class MinioClient:
        def remove_object(self, *_args):
            raise RuntimeError("MinIO unavailable")

    async def no_rows(_session):
        return None

    monkeypatch.setattr(
        demo,
        "_database_runtime",
        lambda: (None, lambda: SessionContext()),
    )
    monkeypatch.setattr(demo, "_delete_rows", no_rows)
    monkeypatch.setattr(demo, "_minio_client", lambda: MinioClient())

    with pytest.raises(RuntimeError, match="MinIO unavailable"):
        await demo.reset()


def test_demo_review_insert_uses_authoritative_deterministic_timestamps():
    source = inspect.getsource(demo.seed).replace(" ", "")

    assert "review_status,received_at,started_at,completed_at" in source
    review_insert = source.split("INSERTINTOreview.reviews", 1)[1].split(
        "INSERTINTOreview.risk_summaries", 1
    )[0]
    assert review_insert.count("TIMESTAMPTZ") == 6
    assert review_insert.count("REVIEW_COMPLETED") == 2
