import asyncio
import os
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db.session import AsyncSessionFactory
from app.core.exceptions import AppError
from app.review.correction_repository import CorrectionRepository
from app.review.correction_service import CorrectionService
from app.review.repository import ReviewRepository
from app.valuation.submissions.repository import SubmissionRepository
from app.valuation.submissions.schemas import SubmitForReviewCommand
from app.valuation.submissions.service import SubmissionService
from app.valuation.repository import ValuationRepository
from app.valuation.schemas import CaseUpdate
from app.valuation.service import ValuationService


REVIEW_WORKFLOW_UPDATE_COLUMNS = {
    "assigned_reviewer_id",
    "completed_at",
    "current_risk_level",
    "form_instance_id",
    "high_count",
    "latest_submission_id",
    "latest_validation_run_id",
    "low_count",
    "manual_priority",
    "manual_priority_reason",
    "medium_count",
    "missing_item_count",
    "review_status",
    "validation_run_id",
}


@dataclass
class _SubmissionFixtureGraph:
    case_id: UUID
    user_id: UUID
    document_id: UUID
    document_group_id: UUID
    rule_source_document_id: UUID
    rule_version_id: UUID
    validation_rule_id: UUID
    form_instance_id: UUID
    extraction_id: UUID
    extracted_field_id: UUID
    validation_run_id: UUID
    request_id: UUID
    review_ids: set[UUID] = field(default_factory=set)
    submission_ids: set[UUID] = field(default_factory=set)
    finding_ids: set[UUID] = field(default_factory=set)
    correction_request_ids: set[UUID] = field(default_factory=set)


def _delete_submission_fixture_graph(admin_cursor, graph: _SubmissionFixtureGraph) -> None:
    review_ids = tuple(graph.review_ids)
    submission_ids = tuple(graph.submission_ids)
    finding_ids = tuple(graph.finding_ids)
    correction_request_ids = tuple(graph.correction_request_ids)

    if correction_request_ids:
        admin_cursor.execute(
            "DELETE FROM review.correction_request_items "
            "WHERE correction_request_id = ANY(%s)",
            (list(correction_request_ids),),
        )
    if review_ids:
        admin_cursor.execute(
            "DELETE FROM review.decisions WHERE review_id = ANY(%s)",
            (list(review_ids),),
        )
    if correction_request_ids:
        admin_cursor.execute(
            "DELETE FROM review.correction_requests "
            "WHERE correction_request_id = ANY(%s)",
            (list(correction_request_ids),),
        )
    if finding_ids:
        admin_cursor.execute(
            "DELETE FROM review.findings WHERE finding_id = ANY(%s)",
            (list(finding_ids),),
        )

    if review_ids:
        admin_cursor.execute(
            """
            UPDATE review.reviews
            SET latest_submission_id = NULL,
                latest_validation_run_id = NULL,
                validation_run_id = NULL,
                form_instance_id = NULL
            WHERE review_id = ANY(%s)
            """,
            (list(review_ids),),
        )
    admin_cursor.execute(
        """
        UPDATE valuation.validation_runs
        SET submission_id = NULL, review_id = NULL
        WHERE validation_run_id = %s
        """,
        (graph.validation_run_id,),
    )
    if submission_ids:
        admin_cursor.execute(
            "DELETE FROM valuation.review_submissions "
            "WHERE submission_id = ANY(%s)",
            (list(submission_ids),),
        )
    if review_ids:
        admin_cursor.execute(
            "DELETE FROM review.reviews WHERE review_id = ANY(%s)",
            (list(review_ids),),
        )
    admin_cursor.execute(
        "DELETE FROM history.case_events WHERE case_id = %s AND request_id = %s",
        (graph.case_id, graph.request_id),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.extracted_fields WHERE extracted_field_id = %s",
        (graph.extracted_field_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.document_extractions WHERE extraction_id = %s",
        (graph.extraction_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.validation_findings "
        "WHERE validation_run_id = %s",
        (graph.validation_run_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.validation_runs WHERE validation_run_id = %s",
        (graph.validation_run_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.form_instances WHERE form_instance_id = %s",
        (graph.form_instance_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.documents WHERE document_id = %s",
        (graph.document_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.validation_rules WHERE validation_rule_id = %s",
        (graph.validation_rule_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.rule_versions WHERE rule_version_id = %s",
        (graph.rule_version_id,),
    )
    admin_cursor.execute(
        "DELETE FROM knowledge.documents WHERE document_id = %s",
        (graph.rule_source_document_id,),
    )
    admin_cursor.execute(
        "DELETE FROM valuation.cases WHERE case_id = %s", (graph.case_id,)
    )
    admin_cursor.execute(
        "DELETE FROM auth.users WHERE user_id = %s", (graph.user_id,)
    )


@pytest.fixture
def submission_fixture_graphs(admin_cursor):
    graphs: list[_SubmissionFixtureGraph] = []
    try:
        yield graphs
    finally:
        admin_cursor.connection.rollback()
        try:
            for graph in graphs:
                _delete_submission_fixture_graph(admin_cursor, graph)
            admin_cursor.connection.commit()
        except Exception:
            admin_cursor.connection.rollback()
            raise


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


def test_review_runtime_acl_is_limited_to_the_minimal_workflow(admin_cursor) -> None:
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
        False,
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

    admin_cursor.execute(
        """
        SELECT
            has_table_privilege(%s, 'review.reviews', 'UPDATE'),
            array_agg(column_name::text ORDER BY column_name)
                FILTER (WHERE has_column_privilege(
                    %s, 'review.reviews', column_name, 'UPDATE'
                )),
            array_agg(column_name::text ORDER BY column_name)
                FILTER (WHERE NOT has_column_privilege(
                    %s, 'review.reviews', column_name, 'UPDATE'
                ))
        FROM information_schema.columns
        WHERE table_schema = 'review' AND table_name = 'reviews'
        """,
        (runtime_role,) * 3,
    )
    table_update, allowed_columns, denied_columns = admin_cursor.fetchone()
    assert table_update is False
    assert set(allowed_columns or ()) == REVIEW_WORKFLOW_UPDATE_COLUMNS
    assert {
        "case_id",
        "review_type",
        "started_by_user_id",
        "started_at",
        "received_at",
        "due_at",
    }.issubset(set(denied_columns or ()))


@pytest.mark.asyncio
async def test_runtime_role_can_update_review_priority(
    admin_cursor, db_cursor, submission_fixture_graphs
) -> None:
    case_id, actor, _command = _seed_submittable_case(
        admin_cursor, cleanup=submission_fixture_graphs
    )
    review_id = uuid4()
    admin_cursor.execute(
        """
        INSERT INTO review.reviews
            (review_id, case_id, review_type, review_status, started_by_user_id)
        VALUES (%s, %s, 'SMART_REVIEW', 'RECEIVED', %s)
        """,
        (review_id, case_id, actor.user_id),
    )
    submission_fixture_graphs[-1].review_ids.add(review_id)
    admin_cursor.connection.commit()

    async with AsyncSessionFactory() as session:
        review = await ReviewRepository(session).set_priority(
            review_id, 90, "法定期限將屆", actor.user_id
        )
        await session.commit()

    db_cursor.execute(
        """
        SELECT manual_priority, manual_priority_reason
        FROM review.reviews
        WHERE review_id = %s
        """,
        (review_id,),
    )
    assert db_cursor.fetchone() == (90, "法定期限將屆")


def test_review_runtime_acl_can_read_cross_schema_inputs(admin_cursor) -> None:
    runtime_role = make_url(os.environ["DATABASE_URL"]).username
    assert runtime_role is not None
    admin_cursor.execute(
        """
        SELECT
            has_schema_privilege(%s, 'auth', 'USAGE'),
            has_schema_privilege(%s, 'knowledge', 'USAGE'),
            has_table_privilege(%s, 'auth.users', 'SELECT'),
            has_table_privilege(%s, 'knowledge.documents', 'SELECT')
        """,
        (runtime_role,) * 4,
    )
    assert admin_cursor.fetchone() == (True, True, True, True)

    admin_cursor.execute(
        """
        SELECT
            has_table_privilege(%s, 'auth.users', 'DELETE'),
            has_table_privilege(%s, 'knowledge.documents', 'DELETE')
        """,
        (runtime_role,) * 2,
    )
    assert admin_cursor.fetchone() == (False, False)


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
    admin_cursor.execute(
        """
        SELECT
            has_schema_privilege(%s, 'auth', 'USAGE'),
            has_schema_privilege(%s, 'knowledge', 'USAGE')
        """,
        (runtime_role,) * 2,
    )
    assert admin_cursor.fetchone() == (False, False)
    admin_cursor.execute(
        """
        SELECT
            has_table_privilege(%s, 'review.reviews', 'UPDATE'),
            has_column_privilege(%s, 'review.reviews', 'case_id', 'UPDATE')
        """,
        (runtime_role,) * 2,
    )
    assert admin_cursor.fetchone() == (True, True)
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
    admin_cursor.execute(
        """
        SELECT
            has_table_privilege(%s, 'review.reviews', 'UPDATE'),
            has_column_privilege(%s, 'review.reviews', 'case_id', 'UPDATE'),
            has_column_privilege(%s, 'review.reviews', 'review_status', 'UPDATE')
        """,
        (runtime_role,) * 3,
    )
    assert admin_cursor.fetchone() == (False, False, True)


def _seed_submittable_case(
    admin_cursor,
    *,
    cleanup: list[_SubmissionFixtureGraph] | None = None,
) -> tuple[UUID, SimpleNamespace, SubmitForReviewCommand]:
    case_id = uuid4()
    user_id = uuid4()
    report_id = uuid4()
    document_id = uuid4()
    document_group_id = uuid4()
    extraction_id = uuid4()
    extracted_field_id = uuid4()
    rule_source_document_id = uuid4()
    rule_version_id = uuid4()
    validation_rule_id = uuid4()
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
        INSERT INTO knowledge.documents
            (document_id, document_code, title, document_type,
             original_filename, mime_type, bucket_name, object_key,
             checksum_sha256, file_size_bytes, version_no, effective_from,
             extraction_status, publication_status, approved_by_user_id,
             approved_at)
        VALUES (%s, %s, 'Submission rule source', 'REGULATION',
                'submission-rule.pdf', 'application/pdf', 'land-valuation', %s,
                %s, 100, 1, DATE '2026-09-01', 'COMPLETED', 'PUBLISHED', %s, now())
        """,
        (
            rule_source_document_id,
            f"SUBMISSION-RULE-{rule_source_document_id.hex[:12]}",
            f"knowledge/{rule_source_document_id}/submission-rule.pdf",
            "b" * 64,
            user_id,
        ),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.rule_versions
            (rule_version_id, rule_set_code, version_no, version_name,
             effective_from, status, source_document_id, applicable_case_type,
             applicable_district_code, selection_priority)
        VALUES (%s, %s, 1, 'Submission rules', DATE '2026-09-01', 'PUBLISHED', %s,
                'LAND', 'BANQIAO', 100)
        """,
        (
            rule_version_id,
            f"SUBMISSION-RULESET-{rule_version_id.hex[:12]}",
            rule_source_document_id,
        ),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.validation_rules
            (validation_rule_id, rule_version_id, rule_code, rule_name,
             target_form_code, target_table, target_field_code, severity,
             rule_expression, message_template, is_active)
        VALUES (%s, %s, 'SUBMISSION_SOURCE_READY', 'Submission source ready',
                'F02', 'forms', 'adjustment_rate', 'MEDIUM', '{}',
                'Submission source is ready', true)
        """,
        (validation_rule_id, rule_version_id),
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
            document_group_id,
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
             triggered_by_user_id, rule_version_id, input_snapshot,
             ruleset_snapshot)
        VALUES (%s, %s, %s, 'COMPLETED', 1, 0, 0, now(), %s,
                %s,
                jsonb_build_object('case_version', 1, 'source', 'valuation'),
                jsonb_build_object(
                    'ruleset_code', 'COMPLETE_REPORT_VALIDATION_V1',
                    'rule_version_id', %s::text,
                    'validation_rule_ids', jsonb_build_array(%s::text)
                ))
        """,
        (
            validation_run_id,
            case_id,
            report_id,
            user_id,
            rule_version_id,
            rule_version_id,
            validation_rule_id,
        ),
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
        (
            extracted_field_id,
            case_id,
            extraction_id,
            document_id,
            user_id,
            report_id,
        ),
    )
    admin_cursor.connection.commit()

    if cleanup is not None:
        cleanup.append(
            _SubmissionFixtureGraph(
                case_id=case_id,
                user_id=user_id,
                document_id=document_id,
                document_group_id=document_group_id,
                rule_source_document_id=rule_source_document_id,
                rule_version_id=rule_version_id,
                validation_rule_id=validation_rule_id,
                form_instance_id=report_id,
                extraction_id=extraction_id,
                extracted_field_id=extracted_field_id,
                validation_run_id=validation_run_id,
                request_id=request_id,
            )
        )

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


def _seed_review_race_case(
    admin_cursor,
    *,
    with_correction: bool,
    cleanup: list[_SubmissionFixtureGraph] | None = None,
) -> tuple[UUID, UUID, SimpleNamespace, SubmitForReviewCommand, UUID | None]:
    case_id, actor, command_value = _seed_submittable_case(
        admin_cursor, cleanup=cleanup
    )
    review_id = uuid4()
    admin_cursor.execute(
        """
        INSERT INTO review.reviews
            (review_id, case_id, review_type, review_status,
             latest_validation_run_id)
        VALUES (%s, %s, 'SMART_REVIEW', 'REVIEW_REQUIRED', %s)
        """,
        (review_id, case_id, command_value.source_validation_run_id),
    )
    request_id = None
    if with_correction:
        finding_id = uuid4()
        admin_cursor.execute(
            """
            INSERT INTO review.findings
                (finding_id, review_id, finding_code, finding_type, severity,
                 title, description, status, validation_run_id,
                 document_id, document_version, page_number)
            VALUES (%s, %s, 'RACE:CONFIRMED', 'RATE_OUT_OF_RANGE', 'HIGH',
                    '需修正', '並行鎖定測試', 'CONFIRMED_ISSUE', %s,
                    %s, 1, 1)
            """,
            (
                finding_id,
                review_id,
                command_value.source_validation_run_id,
                command_value.source_report_document_id,
            ),
        )
        request_id = uuid4()
        admin_cursor.execute(
            """
            INSERT INTO review.correction_requests
                (correction_request_id, review_id, request_no,
                 based_on_validation_run_id, status, due_at, message,
                 base_document_id, base_document_version, created_by_user_id)
            VALUES (%s, %s, 1, %s, 'DRAFT', now() + interval '5 days',
                    '並行鎖定測試', %s, 1, %s)
            """,
            (
                request_id,
                review_id,
                command_value.source_validation_run_id,
                command_value.source_report_document_id,
                actor.user_id,
            ),
        )
    if cleanup is not None:
        graph = cleanup[-1]
        graph.review_ids.add(review_id)
        if with_correction:
            assert request_id is not None
            graph.finding_ids.add(finding_id)
            graph.correction_request_ids.add(request_id)
    admin_cursor.connection.commit()
    return case_id, review_id, actor, command_value, request_id


class _SubmitLockProbeRepository(SubmissionRepository):
    def __init__(self, session, case_locked, correction_next_lock):
        super().__init__(session)
        self.case_locked = case_locked
        self.correction_next_lock = correction_next_lock

    async def lock_case(self, case_id):
        case = await super().lock_case(case_id)
        self.case_locked.set()
        await self.correction_next_lock.wait()
        return case


class _CaseWriterProbeRepository(ValuationRepository):
    def __init__(self, session, writer_ready, submission_attempted, release_writer):
        super().__init__(session)
        self.writer_ready = writer_ready
        self.submission_attempted = submission_attempted
        self.release_writer = release_writer

    async def get_case(self, case_id, for_update=False):
        case = await super().get_case(case_id, for_update=for_update)
        if not self.writer_ready.is_set():
            self.writer_ready.set()
            await self.submission_attempted.wait()
            await self.release_writer.wait()
        return case


class _SubmissionAttemptProbeRepository(SubmissionRepository):
    def __init__(self, session, submission_attempted):
        super().__init__(session)
        self.submission_attempted = submission_attempted

    async def lock_case(self, case_id):
        self.submission_attempted.set()
        return await super().lock_case(case_id)


class _CorrectionLockProbeRepository(ReviewRepository):
    def __init__(self, session, correction_next_lock):
        super().__init__(session)
        self.correction_next_lock = correction_next_lock

    async def get(self, review_id, for_update=False):
        review = await super().get(review_id, for_update=for_update)
        if for_update:
            self.correction_next_lock.set()
        return review

    async def get_case(self, case_id, for_update=False):
        if for_update:
            # Signal before the FOR UPDATE query.  With a case-first lock
            # order the submission can proceed while this session waits on
            # the case; the old Review-first order deadlocks deterministically.
            self.correction_next_lock.set()
        return await super().get_case(case_id, for_update=for_update)


class _InitialRequestReadBarrierRepository(CorrectionRepository):
    def __init__(self, session, initial_reads):
        super().__init__(session)
        self.initial_reads = initial_reads

    async def get_request(self, request_id, for_update=False):
        request = await super().get_request(request_id, for_update=for_update)
        if not for_update:
            await self.initial_reads.wait()
        return request


async def _run_submission_with_probe(
    case_id, command_value, actor, case_locked, correction_next_lock
):
    async with AsyncSessionFactory() as session:
        repository = _SubmitLockProbeRepository(
            session, case_locked, correction_next_lock
        )
        try:
            result = await SubmissionService(
                session, repository=repository
            ).submit(case_id, command_value, actor)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


async def _run_case_writer_with_probe(
    case_id, actor, writer_ready, submission_attempted, release_writer
):
    async with AsyncSessionFactory() as session:
        repository = _CaseWriterProbeRepository(
            session, writer_ready, submission_attempted, release_writer
        )
        try:
            result = await ValuationService(session, repository=repository).update_case(
                case_id,
                CaseUpdate(case_title="writer committed title"),
                actor,
            )
            await session.execute(
                text(
                    """
                    UPDATE valuation.form_instances
                    SET form_content = form_content ||
                        '{"writer_marker": "writer committed form"}'::jsonb
                    WHERE form_instance_id = (
                        SELECT form_instance_id
                        FROM valuation.form_instances
                        WHERE case_id = :case_id
                          AND form_code = 'F02'
                        ORDER BY version_no DESC, form_instance_id DESC
                        LIMIT 1
                    )
                    """
                ),
                {"case_id": case_id},
            )
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


async def _run_submission_with_attempt_probe(case_id, command_value, actor, submission_attempted):
    async with AsyncSessionFactory() as session:
        repository = _SubmissionAttemptProbeRepository(session, submission_attempted)
        try:
            result = await SubmissionService(
                session, repository=repository
            ).submit(case_id, command_value, actor)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


async def _run_correction_with_probe(
    review_id,
    request_id,
    actor_id,
    *,
    complete: bool,
    correction_next_lock,
):
    async with AsyncSessionFactory() as session:
        repository = _CorrectionLockProbeRepository(session, correction_next_lock)
        corrections = CorrectionService(
            repository,
            CorrectionRepository(session),
        )
        try:
            if complete:
                result = await corrections.complete_review(
                    review_id, "並行完成測試", actor_id, uuid4()
                )
            else:
                result = await corrections.send(request_id, actor_id, uuid4())
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


async def _run_lock_order_race(
    admin_cursor,
    *,
    complete: bool,
    cleanup: list[_SubmissionFixtureGraph] | None = None,
) -> tuple[UUID, UUID, list[object]]:
    case_id, review_id, actor, command_value, request_id = _seed_review_race_case(
        admin_cursor, with_correction=not complete, cleanup=cleanup
    )
    case_locked = asyncio.Event()
    correction_next_lock = asyncio.Event()
    submit_task = asyncio.create_task(
        _run_submission_with_probe(
            case_id,
            command_value,
            actor,
            case_locked,
            correction_next_lock,
        )
    )
    await asyncio.wait_for(case_locked.wait(), timeout=5)
    correction_task = asyncio.create_task(
        _run_correction_with_probe(
            review_id,
            request_id,
            actor.user_id,
            complete=complete,
            correction_next_lock=correction_next_lock,
        )
    )
    try:
        outcomes = await asyncio.wait_for(
            asyncio.gather(submit_task, correction_task, return_exceptions=True),
            timeout=10,
        )
    except asyncio.TimeoutError as exc:
        for task in (submit_task, correction_task):
            task.cancel()
        await asyncio.gather(submit_task, correction_task, return_exceptions=True)
        raise AssertionError("submission/correction lock-order race deadlocked") from exc
    if cleanup is not None:
        graph = cleanup[-1]
        if not isinstance(outcomes[0], Exception):
            graph.submission_ids.add(outcomes[0].submission_id)
    return case_id, review_id, outcomes


@pytest.mark.asyncio
async def test_real_sessions_submit_vs_send_have_no_deadlock(
    admin_cursor, submission_fixture_graphs
) -> None:
    case_id, review_id, outcomes = await _run_lock_order_race(
        admin_cursor, complete=False, cleanup=submission_fixture_graphs
    )

    assert not isinstance(outcomes[0], Exception)
    assert isinstance(outcomes[1], AppError)
    assert outcomes[1].code == "REVIEW_STATE_CONFLICT"
    admin_cursor.execute(
        """
        SELECT r.review_status, c.case_status,
               (SELECT count(*) FROM valuation.review_submissions s
                WHERE s.case_id = c.case_id)
        FROM review.reviews r
        JOIN valuation.cases c ON c.case_id = r.case_id
        WHERE r.review_id = %s AND c.case_id = %s
        """,
        (review_id, case_id),
    )
    assert admin_cursor.fetchone() == ("RECEIVED", "IN_REVIEW", 1)


@pytest.mark.asyncio
async def test_real_sessions_submit_vs_complete_have_no_deadlock(
    admin_cursor, submission_fixture_graphs
) -> None:
    case_id, review_id, outcomes = await _run_lock_order_race(
        admin_cursor, complete=True, cleanup=submission_fixture_graphs
    )

    assert not isinstance(outcomes[0], Exception)
    assert not isinstance(outcomes[1], Exception)
    admin_cursor.execute(
        """
        SELECT r.review_status, c.case_status,
               (SELECT count(*) FROM valuation.review_submissions s
                WHERE s.case_id = c.case_id),
               (SELECT count(*) FROM review.decisions d
                WHERE d.review_id = r.review_id AND d.decision = 'APPROVED')
        FROM review.reviews r
        JOIN valuation.cases c ON c.case_id = r.case_id
        WHERE r.review_id = %s AND c.case_id = %s
        """,
        (review_id, case_id),
    )
    assert admin_cursor.fetchone() == ("REVIEW_COMPLETED", "REVIEW_COMPLETED", 1, 1)


@pytest.mark.asyncio
async def test_case_writer_and_submission_share_case_lock_for_consistent_snapshot(
    admin_cursor, submission_fixture_graphs
) -> None:
    case_id, actor, command_value = _seed_submittable_case(
        admin_cursor, cleanup=submission_fixture_graphs
    )
    writer_ready = asyncio.Event()
    submission_attempted = asyncio.Event()
    release_writer = asyncio.Event()

    writer_task = asyncio.create_task(
        _run_case_writer_with_probe(
            case_id,
            actor,
            writer_ready,
            submission_attempted,
            release_writer,
        )
    )
    await asyncio.wait_for(writer_ready.wait(), timeout=5)
    submission_task = asyncio.create_task(
        _run_submission_with_attempt_probe(
            case_id, command_value, actor, submission_attempted
        )
    )
    await asyncio.wait_for(submission_attempted.wait(), timeout=5)
    release_writer.set()

    writer_result, submission_result = await asyncio.wait_for(
        asyncio.gather(writer_task, submission_task), timeout=10
    )
    graph = submission_fixture_graphs[-1]
    graph.review_ids.add(submission_result.review_id)
    graph.submission_ids.add(submission_result.submission_id)

    admin_cursor.execute(
        """
        SELECT input_snapshot->'execution_context'->'case'->>'case_title',
               input_snapshot->'execution_context'->'report'->'form'
                   ->'form_content'->>'writer_marker'
        FROM valuation.review_submissions
        WHERE submission_id = %s
        """,
        (submission_result.submission_id,),
    )
    assert admin_cursor.fetchone() == (
        writer_result.case_title,
        "writer committed form",
    )


@pytest.mark.asyncio
async def test_real_sessions_submit_same_request_once(
    admin_cursor, submission_fixture_graphs
) -> None:
    case_id, actor, command = _seed_submittable_case(
        admin_cursor, cleanup=submission_fixture_graphs
    )

    async def submit_once():
        async with AsyncSessionFactory() as session:
            result = await SubmissionService(session).submit(case_id, command, actor)
            await session.commit()
            return result

    first, second = await asyncio.gather(submit_once(), submit_once())

    graph = submission_fixture_graphs[-1]
    graph.review_ids.add(first.review_id)
    graph.submission_ids.add(first.submission_id)

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


@pytest.mark.asyncio
async def test_real_sessions_send_same_draft_once(
    admin_cursor, submission_fixture_graphs
) -> None:
    case_id, review_id, actor, _command, request_id = _seed_review_race_case(
        admin_cursor,
        with_correction=True,
        cleanup=submission_fixture_graphs,
    )
    assert request_id is not None
    initial_reads = asyncio.Barrier(2)

    async def send_once():
        async with AsyncSessionFactory() as session:
            corrections = _InitialRequestReadBarrierRepository(session, initial_reads)
            service = CorrectionService(ReviewRepository(session), corrections)
            try:
                result = await service.send(request_id, actor.user_id, uuid4())
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    first, second = await asyncio.gather(send_once(), send_once())
    outcomes = (first, second)

    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    failed = next(outcome for outcome in outcomes if isinstance(outcome, Exception))
    assert isinstance(failed, AppError)
    assert failed.code == "CORRECTION_REQUEST_STATE_CONFLICT"

    admin_cursor.execute(
        "SELECT status FROM review.correction_requests "
        "WHERE correction_request_id = %s",
        (request_id,),
    )
    assert admin_cursor.fetchone() == ("SENT",)
    admin_cursor.execute(
        "SELECT review_status FROM review.reviews WHERE review_id = %s",
        (review_id,),
    )
    assert admin_cursor.fetchone() == ("RETURNED_FOR_REVISION",)
    admin_cursor.execute(
        "SELECT case_status FROM valuation.cases WHERE case_id = %s",
        (case_id,),
    )
    assert admin_cursor.fetchone() == ("REVISION_REQUIRED",)
    admin_cursor.execute(
        "SELECT count(*) FROM review.decisions "
        "WHERE review_id = %s AND decision = 'RETURNED_FOR_REVISION'",
        (review_id,),
    )
    assert admin_cursor.fetchone() == (1,)
