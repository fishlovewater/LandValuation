import subprocess
import sys
import os
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from tests.integration.schema_assertions import (
    column_names,
    table_exists,
    unique_columns,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_alembic(command: str, revision: str, *, expect_success: bool = True):
    env = os.environ.copy()
    if env.get("MIGRATION_DATABASE_URL"):
        env["DATABASE_URL"] = env["MIGRATION_DATABASE_URL"]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is expect_success, result.stdout + result.stderr
    return result


def create_user_case_document(cursor, *, case_no: str | None = None):
    user_id = uuid4()
    case_id = uuid4()
    document_id = uuid4()
    case_no = case_no or f"MIG-0009-{uuid4().hex[:10]}"

    cursor.execute(
        """
        INSERT INTO auth.users (
            user_id, username, email, password_hash, display_name, is_active
        ) VALUES (%s, %s, %s, 'hash', 'Migration Tester', true)
        """,
        (user_id, f"user_{uuid4().hex[:10]}", f"{uuid4().hex[:12]}@example.test"),
    )
    cursor.execute(
        """
        INSERT INTO valuation.cases (
            case_id, case_no, case_title, case_type, valuation_base_date,
            city_code, district_code, created_by_user_id, updated_by_user_id
        ) VALUES (%s, %s, 'Migration case', 'LAND', CURRENT_DATE,
                  'TP', 'BANQIAO', %s, %s)
        """,
        (case_id, case_no, user_id, user_id),
    )
    cursor.execute(
        """
        INSERT INTO valuation.documents (
            document_id, case_id, document_type, original_filename, mime_type,
            bucket_name, object_key, checksum_sha256, file_size_bytes,
            uploaded_by_user_id
        ) VALUES (%s, %s, 'APPRAISAL_REPORT', 'migration.pdf', 'application/pdf',
                  'land-valuation', %s, %s, 1, %s)
        """,
        (document_id, case_id, f"cases/{case_id}/{document_id}.pdf", "a" * 64, user_id),
    )
    return user_id, case_id, document_id


def create_extraction(cursor, user_id, case_id, document_id, *, provider="LOCAL_PDF"):
    extraction_id = uuid4()
    cursor.execute(
        """
        INSERT INTO valuation.document_extractions (
            extraction_id, case_id, document_id, provider, extraction_status,
            created_by_user_id
        ) VALUES (%s, %s, %s, %s, 'PENDING', %s)
        """,
        (extraction_id, case_id, document_id, provider, user_id),
    )
    return extraction_id


def test_canonical_extraction_schema_contract(admin_cursor):
    assert set(column_names(admin_cursor, "document_extractions", "valuation")) >= {
        "extraction_id",
        "case_id",
        "document_id",
        "provider",
        "extraction_status",
        "created_by_user_id",
        "completed_at",
    }
    assert set(column_names(admin_cursor, "extracted_fields", "valuation")) >= {
        "extracted_field_id",
        "case_id",
        "extraction_id",
        "document_id",
        "form_code",
        "field_name",
        "extracted_value",
        "source_page",
        "source_text",
        "analysis_provider",
        "model_id",
        "prompt_version",
        "field_status",
        "confirmed_value",
        "confirmed_by_user_id",
        "confirmed_at",
        "applied_form_instance_id",
        "applied_at",
    }
    assert set(column_names(admin_cursor, "assistant_sessions", "valuation")) >= {
        "assistant_session_id",
        "case_id",
        "user_id",
        "current_step",
        "selected_form_type",
        "provider",
        "model_id",
        "prompt_version",
        "session_status",
    }
    assert set(column_names(admin_cursor, "assistant_messages", "valuation")) >= {
        "assistant_message_id",
        "assistant_session_id",
        "message_no",
        "role",
        "content",
        "tool_name",
    }
    assert not table_exists(admin_cursor, "extraction_runs", "valuation")
    assert unique_columns(admin_cursor, "extracted_fields", "valuation") == {
        ("extraction_id", "form_code", "field_name")
    }


def test_canonical_provider_and_provenance_constraints(admin_cursor):
    user_id, case_id, document_id = create_user_case_document(admin_cursor)
    extraction_id = create_extraction(
        admin_cursor, user_id, case_id, document_id, provider="LOCAL_XLSX"
    )

    admin_cursor.execute(
        """
        INSERT INTO valuation.extracted_fields (
            case_id, extraction_id, document_id, form_code, field_name,
            extracted_value, confidence, analysis_provider
        ) VALUES (%s, %s, %s, 'F03', 'land_area',
                  %s, 0.9000, 'RULE')
        """,
        (case_id, extraction_id, document_id, Jsonb({"value": "100"})),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.extracted_fields (
            case_id, extraction_id, document_id, form_code, field_name,
            extracted_value, confidence, analysis_provider, model_id, prompt_version
        ) VALUES (%s, %s, %s, 'F04', 'land_area',
                  %s, 0.8000, 'CODEX', 'codex-test', 'prompt-v1')
        """,
        (case_id, extraction_id, document_id, Jsonb({"value": "100"})),
    )

    with pytest.raises(Exception):
        create_extraction(admin_cursor, user_id, case_id, document_id, provider="REMOTE_XLSX")
    admin_cursor.connection.rollback()

    user_id, case_id, document_id = create_user_case_document(admin_cursor)
    extraction_id = create_extraction(
        admin_cursor, user_id, case_id, document_id, provider="LOCAL_OCR"
    )
    with pytest.raises(Exception):
        admin_cursor.execute(
            """
            INSERT INTO valuation.extracted_fields (
                case_id, extraction_id, document_id, form_code, field_name,
                extracted_value, confidence, analysis_provider
            ) VALUES (%s, %s, %s, 'F03', 'missing_model',
                      %s, 0.7000, 'CODEX')
            """,
            (case_id, extraction_id, document_id, Jsonb({"value": "bad"})),
        )
    admin_cursor.connection.rollback()


def test_extracted_field_unique_key_is_scoped_by_form(admin_cursor):
    user_id, case_id, document_id = create_user_case_document(admin_cursor)
    extraction_id = create_extraction(admin_cursor, user_id, case_id, document_id)

    for form_code in ("F03", "F04"):
        admin_cursor.execute(
            """
            INSERT INTO valuation.extracted_fields (
                case_id, extraction_id, document_id, form_code, field_name,
                extracted_value, confidence
            ) VALUES (%s, %s, %s, %s, 'same_name', %s, 0.5000)
            """,
            (case_id, extraction_id, document_id, form_code, Jsonb({"value": form_code})),
        )

    with pytest.raises(Exception):
        admin_cursor.execute(
            """
            INSERT INTO valuation.extracted_fields (
                case_id, extraction_id, document_id, form_code, field_name,
                extracted_value, confidence
            ) VALUES (%s, %s, %s, 'F03', 'same_name', %s, 0.5000)
            """,
            (case_id, extraction_id, document_id, Jsonb({"value": "duplicate"})),
        )
    admin_cursor.connection.rollback()


def test_non_demo_legacy_extraction_blocks_upgrade(admin_cursor):
    run_alembic("downgrade", "20260830_0008")
    user_id, case_id, document_id = create_user_case_document(admin_cursor)
    admin_cursor.execute(
        """
        INSERT INTO valuation.extraction_runs (
            case_id, document_id, document_version, run_no, status, extractor_name
        ) VALUES (%s, %s, 1, 1, 'PENDING', 'migration-test')
        """,
        (case_id, document_id),
    )
    admin_cursor.connection.commit()

    result = run_alembic("upgrade", "head", expect_success=False)
    assert "non-demo legacy extraction data prevents migration" in (
        result.stdout + result.stderr
    )

    admin_cursor.execute("DELETE FROM valuation.extraction_runs WHERE case_id = %s", (case_id,))
    admin_cursor.connection.commit()
    run_alembic("upgrade", "head")


def test_downgrade_recreates_empty_legacy_schema_and_refuses_data(admin_cursor):
    user_id, case_id, document_id = create_user_case_document(admin_cursor)
    create_extraction(admin_cursor, user_id, case_id, document_id)
    admin_cursor.connection.commit()

    result = run_alembic("downgrade", "20260830_0008", expect_success=False)
    assert "cannot downgrade canonical extraction schema while data exists" in (
        result.stdout + result.stderr
    )

    admin_cursor.execute("DELETE FROM valuation.document_extractions WHERE case_id = %s", (case_id,))
    admin_cursor.connection.commit()
    run_alembic("downgrade", "20260830_0008")
    assert set(column_names(admin_cursor, "extraction_runs", "valuation")) >= {
        "extraction_run_id",
        "document_version",
        "run_no",
        "status",
        "extractor_name",
    }
    assert set(column_names(admin_cursor, "extracted_fields", "valuation")) >= {
        "extraction_run_id",
        "field_code",
        "field_path",
        "raw_text",
        "normalized_value",
        "verification_status",
    }
    run_alembic("upgrade", "head")
