import asyncio
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import make_url

from app.db.session import AsyncSessionFactory
from app.valuation.submissions.schemas import SubmitForReviewCommand
from app.valuation.submissions.service import SubmissionService


def test_submit_review_permission_is_seeded_only_for_appraiser(admin_cursor) -> None:
    admin_cursor.execute(
        """
        SELECT r.role_code
        FROM auth.role_permissions AS rp
        JOIN auth.roles AS r ON r.role_id = rp.role_id
        JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
        WHERE p.permission_code = 'valuation.submit_review'
        ORDER BY r.role_code
        """
    )

    assert [row[0] for row in admin_cursor.fetchall()] == ["APPRAISER"]


def test_submit_runtime_acl_is_limited_to_the_submit_transaction(admin_cursor) -> None:
    runtime_role = make_url(os.environ["DATABASE_URL"]).username
    assert runtime_role is not None
    admin_cursor.execute(
        """
        SELECT
            has_schema_privilege(%s, 'review', 'USAGE'),
            has_schema_privilege(%s, 'history', 'USAGE'),
            has_table_privilege(%s, 'review.reviews', 'SELECT'),
            has_table_privilege(%s, 'review.reviews', 'INSERT'),
            has_table_privilege(%s, 'review.reviews', 'UPDATE'),
            has_table_privilege(%s, 'review.reviews', 'DELETE'),
            has_table_privilege(%s, 'history.case_events', 'INSERT'),
            has_table_privilege(%s, 'history.case_events', 'SELECT'),
            has_table_privilege(%s, 'history.case_events', 'UPDATE'),
            has_table_privilege(%s, 'history.case_events', 'DELETE'),
            has_table_privilege(%s, 'valuation.review_submissions', 'SELECT'),
            has_table_privilege(%s, 'valuation.review_submissions', 'INSERT'),
            has_table_privilege(%s, 'valuation.review_submissions', 'UPDATE'),
            has_table_privilege(%s, 'valuation.review_submissions', 'DELETE')
        """,
        (runtime_role,) * 14,
    )

    assert admin_cursor.fetchone() == (
        True,
        True,
        True,
        True,
        True,
        False,
        True,
        False,
        False,
        False,
        True,
        True,
        False,
        False,
    )
    admin_cursor.execute(
        "SELECT has_column_privilege(%s, 'history.case_events', 'occurred_at', 'SELECT')",
        (runtime_role,),
    )
    assert admin_cursor.fetchone() == (True,)


def test_submit_permission_migration_downgrades_and_reupgrades(
    migration_roundtrip, admin_cursor
) -> None:
    runtime_role = make_url(os.environ["DATABASE_URL"]).username
    assert runtime_role is not None

    migration_roundtrip("downgrade", "20260901_0012")
    admin_cursor.execute(
        "SELECT count(*) FROM auth.permissions WHERE permission_code = 'valuation.submit_review'"
    )
    assert admin_cursor.fetchone() == (0,)
    admin_cursor.execute(
        "SELECT has_schema_privilege(%s, 'review', 'USAGE')",
        (runtime_role,),
    )
    assert admin_cursor.fetchone() == (False,)
    admin_cursor.connection.commit()

    migration_roundtrip("upgrade", "head")
    admin_cursor.execute(
        """
        SELECT count(*)
        FROM auth.role_permissions AS rp
        JOIN auth.roles AS r ON r.role_id = rp.role_id
        JOIN auth.permissions AS p ON p.permission_id = rp.permission_id
        WHERE r.role_code = 'APPRAISER'
          AND p.permission_code = 'valuation.submit_review'
        """
    )
    assert admin_cursor.fetchone() == (1,)


def _seed_submittable_case(
    admin_cursor,
) -> tuple[UUID, SimpleNamespace, SubmitForReviewCommand]:
    case_id = uuid4()
    user_id = uuid4()
    report_id = uuid4()
    document_id = uuid4()
    extraction_id = uuid4()
    validation_run_id = uuid4()
    request_id = uuid4()
    admin_cursor.execute(
        """
        INSERT INTO auth.users
            (user_id, username, email, password_hash, display_name, is_active,
             created_at, updated_at)
        VALUES (%s, %s, %s, 'not-used', 'Submission integration user', true,
                now(), now())
        """,
        (user_id, f"submission-{user_id.hex}", f"{user_id.hex}@example.test"),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.cases
            (case_id, case_no, case_title, case_type, valuation_base_date,
             city_code, district_code, case_status, created_by_user_id,
             updated_by_user_id)
        VALUES (%s, %s, 'Submission concurrency test', 'LAND', '2026-09-03',
                'NEW_TAIPEI', 'BANQIAO', 'PROCESSING', %s, %s)
        """,
        (case_id, f"SUBMIT-{case_id.hex[:12]}", user_id, user_id),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.documents
            (document_id, case_id, document_type, original_filename, mime_type,
             bucket_name, object_key, checksum_sha256, file_size_bytes,
             version_no, uploaded_by_user_id, uploaded_at, is_active,
             document_group_id)
        VALUES (%s, %s, 'complete-valuation-report', 'submission-report.pdf',
                'application/pdf', 'land-valuation', %s, %s, 1, 1, %s, now(),
                true, %s)
        """,
        (
            document_id,
            case_id,
            f"cases/{case_id}/submission-report.pdf",
            "a" * 64,
            user_id,
            uuid4(),
        ),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.form_instances
            (form_instance_id, case_id, form_code, version_no, form_status,
             form_content, output_document_id, created_by_user_id,
             updated_by_user_id)
        VALUES (
            %s, %s, 'F02', 1, 'FINAL',
            jsonb_build_object(
                'report_type', 'REPORT_COMPARISON_COMMERCIAL',
                'report_id', %s::text,
                'report_version', 1,
                'data', jsonb_build_object(
                    'calculation_status', 'CALCULATED',
                    'calculation_snapshot', jsonb_build_object('formula_code', 'FORMAL_V1'),
                    'benchmark_comparison_price', '246.9000',
                    'calculated_at', now()::text
                )
            ),
            %s, %s, %s
        )
        """,
        (report_id, case_id, report_id, document_id, user_id, user_id),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.document_extractions
            (extraction_id, case_id, document_id, provider, extraction_status,
             created_by_user_id, completed_at)
        VALUES (%s, %s, %s, 'LOCAL_PDF', 'COMPLETED', %s, now())
        """,
        (extraction_id, case_id, document_id, user_id),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.validation_runs
            (validation_run_id, case_id, form_instance_id, run_status,
             passed_count, warning_count, failed_count, completed_at,
             triggered_by_user_id, ruleset_snapshot)
        VALUES (%s, %s, %s, 'COMPLETED', 1, 0, 0, now(), %s,
                jsonb_build_object('ruleset_code', 'COMPLETE_REPORT_VALIDATION_V1'))
        """,
        (validation_run_id, case_id, report_id, user_id),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.extracted_fields
            (extracted_field_id, case_id, extraction_id, document_id, form_code,
             field_name, extracted_value, confidence, analysis_provider,
             field_status, confirmed_value, confirmed_by_user_id, confirmed_at,
             applied_form_instance_id, applied_at)
        VALUES (%s, %s, %s, %s, 'F03', 'unit_price',
                to_jsonb('123.4500'::text), 1.0000, 'RULE', 'APPLIED',
                to_jsonb('123.4500'::text), %s, now(), %s, now())
        """,
        (uuid4(), case_id, extraction_id, document_id, user_id, report_id),
    )
    admin_cursor.connection.commit()

    return (
        case_id,
        SimpleNamespace(
            user_id=user_id,
            roles=[
                SimpleNamespace(
                    role_code="APPRAISER",
                    is_active=True,
                    permissions=[
                        SimpleNamespace(permission_code="valuation.submit_review")
                    ],
                )
            ],
        ),
        SubmitForReviewCommand(
            request_id=request_id,
            expected_case_version=1,
            source_validation_run_id=validation_run_id,
            source_report_document_id=document_id,
        ),
    )


@pytest.mark.asyncio
async def test_real_sessions_submit_same_request_once(admin_cursor) -> None:
    case_id, actor, command = _seed_submittable_case(admin_cursor)

    async def submit_once():
        async with AsyncSessionFactory() as session:
            result = await SubmissionService(session).submit(case_id, command, actor)
            await session.commit()
            return result

    first, second = await asyncio.gather(submit_once(), submit_once())

    assert first.submission_id == second.submission_id
    assert first.review_id == second.review_id
    admin_cursor.execute(
        "SELECT latest_submission_id FROM review.reviews WHERE review_id = %s",
        (first.review_id,),
    )
    assert admin_cursor.fetchone() == (first.submission_id,)
    admin_cursor.execute(
        "SELECT count(*) FROM valuation.review_submissions WHERE case_id = %s",
        (case_id,),
    )
    submission_count = admin_cursor.fetchone()[0]
    admin_cursor.execute(
        """
        SELECT count(*)
        FROM history.case_events
        WHERE case_id = %s AND event_type = 'SUBMITTED_FOR_REVIEW'
        """,
        (case_id,),
    )
    event_count = admin_cursor.fetchone()[0]

    assert submission_count == 1
    assert event_count == 1
