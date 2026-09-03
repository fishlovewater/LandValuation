from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.db.session import AsyncSessionFactory
from app.review.correction_repository import CorrectionRepository
from app.review.correction_service import CorrectionService
from app.review.repository import ReviewRepository
from app.review.schemas import CorrectionRequestCreate, FindingTriageRequest
from app.review.service import ReviewService
from app.review.workbench_repository import WorkbenchRepository
from app.review.workbench_service import WorkbenchService
from app.valuation.submissions.schemas import SubmitForReviewCommand
from app.valuation.submissions.service import SubmissionService


@dataclass(frozen=True)
class _Case:
    case_id: UUID
    document_id: UUID
    extraction_id: UUID
    report_form_id: UUID
    source_validation_run_id: UUID
    appraiser_id: UUID
    original_filename: str
    adjustment_value: str
    grade_value: str


@dataclass(frozen=True)
class _HandoffData:
    cases: tuple[_Case, _Case]
    rule_version_id: UUID
    validation_rule_ids: tuple[UUID, UUID]
    rule_source_document_id: UUID
    user_ids: tuple[UUID, UUID]


def _insert_user(cursor, user_id: UUID, role_name: str) -> None:
    cursor.execute(
        """
        INSERT INTO auth.users
            (user_id, username, email, password_hash, display_name, is_active,
             created_at, updated_at)
        VALUES (%s, %s, %s, 'not-used', %s, true, now(), now())
        """,
        (
            user_id,
            f"handoff-{role_name.lower()}-{user_id.hex}",
            f"handoff-{role_name.lower()}-{user_id.hex}@example.test",
            f"Handoff {role_name}",
        ),
    )


def _insert_case_graph(
    cursor,
    *,
    appraiser_id: UUID,
    source_validation_run_id: UUID,
    index: int,
) -> _Case:
    case_id = uuid4()
    base_document_id = uuid4()
    document_id = uuid4()
    document_group_id = uuid4()
    extraction_id = uuid4()
    report_form_id = uuid4()
    original_filename = f"handoff-report-{index}.pdf"
    adjustment_value = "-12.0000"
    grade_value = "B"

    cursor.execute(
        """
        INSERT INTO valuation.cases
            (case_id, case_no, case_title, case_type, valuation_base_date,
             city_code, district_code, land_use_type, case_status,
             created_by_user_id, updated_by_user_id)
        VALUES (%s, %s, %s, 'LAND', CURRENT_DATE, 'NEW_TAIPEI', 'BANQIAO',
                'COMMERCIAL', 'PROCESSING', %s, %s)
        """,
        (
            case_id,
            f"HANDOFF-{index}-{case_id.hex[:12]}",
            f"Valuation review handoff {index}",
            appraiser_id,
            appraiser_id,
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.documents
            (document_id, case_id, document_type, original_filename, mime_type,
             bucket_name, object_key, checksum_sha256, file_size_bytes,
             version_no, uploaded_by_user_id, uploaded_at, is_active,
             document_group_id)
        VALUES (%s, %s, 'complete-valuation-report', %s, 'application/pdf',
                'land-valuation', %s, %s, 2048, 1, %s, now(), true, %s)
        """,
        (
            document_id,
            case_id,
            original_filename,
            f"cases/{case_id}/handoff-report-{index}.pdf",
            ("a" if index == 1 else "b") * 64,
            appraiser_id,
            document_group_id,
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.documents
            (document_id, case_id, document_type, original_filename, mime_type,
             bucket_name, object_key, checksum_sha256, file_size_bytes,
             version_no, uploaded_by_user_id, uploaded_at, is_active,
             document_group_id)
        VALUES (%s, %s, 'original', %s, 'application/pdf', 'land-valuation',
                %s, %s, 1024, 1, %s, now(), true, %s)
        """,
        (
            base_document_id,
            case_id,
            f"handoff-original-{index}.pdf",
            f"cases/{case_id}/handoff-original-{index}.pdf",
            ("d" if index == 1 else "e") * 64,
            appraiser_id,
            uuid4(),
        ),
    )
    cursor.execute(
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
                    'calculation_snapshot',
                        jsonb_build_object('formula_code', 'FORMAL_V1'),
                    'benchmark_comparison_price', '246.9000',
                    'calculated_at', now()::text
                )
            ),
            %s, %s, %s
        )
        """,
        (
            report_form_id,
            case_id,
            report_form_id,
            document_id,
            appraiser_id,
            appraiser_id,
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.document_extractions
            (extraction_id, case_id, document_id, provider, extraction_status,
             created_by_user_id, completed_at)
        VALUES (%s, %s, %s, 'LOCAL_PDF', 'COMPLETED', %s, now())
        """,
        (extraction_id, case_id, document_id, appraiser_id),
    )
    for field_name, value, raw_text, page in (
        (
            "adjustment_rate",
            adjustment_value,
            "報告調整率 -12%",
            3,
        ),
        ("expert_grade", grade_value, "報告級距 B", 4),
    ):
        cursor.execute(
            """
            INSERT INTO valuation.extracted_fields
                (extracted_field_id, case_id, extraction_id, document_id,
                 form_code, field_name, extracted_value, confidence,
                 source_page, source_text, analysis_provider, field_status,
                 confirmed_value, confirmed_by_user_id, confirmed_at,
                 applied_form_instance_id, applied_at)
            VALUES (%s, %s, %s, %s, 'F02', %s, to_jsonb(%s::text), 1.0000,
                    %s, %s, 'RULE', 'APPLIED', to_jsonb(%s::text), %s, now(),
                    %s, now())
            """,
            (
                uuid4(),
                case_id,
                extraction_id,
                document_id,
                field_name,
                value,
                page,
                raw_text,
                value,
                appraiser_id,
                report_form_id,
            ),
        )
    cursor.execute(
        """
        INSERT INTO valuation.validation_runs
            (validation_run_id, case_id, form_instance_id, run_status,
             passed_count, warning_count, failed_count, completed_at,
             triggered_by_user_id, ruleset_snapshot)
        VALUES (%s, %s, %s, 'COMPLETED', 2, 0, 0, now(), %s,
                jsonb_build_object('ruleset_code', 'HANDOFF_VALIDATION_V1'))
        """,
        (source_validation_run_id, case_id, report_form_id, appraiser_id),
    )
    return _Case(
        case_id=case_id,
        document_id=document_id,
        extraction_id=extraction_id,
        report_form_id=report_form_id,
        source_validation_run_id=source_validation_run_id,
        appraiser_id=appraiser_id,
        original_filename=original_filename,
        adjustment_value=adjustment_value,
        grade_value=grade_value,
    )


@pytest.fixture
def handoff_data(admin_cursor) -> _HandoffData:
    appraiser_id = uuid4()
    reviewer_id = uuid4()
    rule_source_document_id = uuid4()
    rule_version_id = uuid4()
    adjustment_rule_id = uuid4()
    grade_rule_id = uuid4()
    source_validation_run_ids = (uuid4(), uuid4())

    _insert_user(admin_cursor, appraiser_id, "APPRAISER")
    _insert_user(admin_cursor, reviewer_id, "REVIEWER")
    admin_cursor.execute(
        """
        INSERT INTO knowledge.documents
            (document_id, document_code, title, document_type,
             original_filename, mime_type, bucket_name, object_key,
             checksum_sha256, file_size_bytes, version_no, effective_from,
             extraction_status, publication_status, approved_by_user_id,
             approved_at)
        VALUES (%s, %s, 'Handoff rule source', 'REGULATION', 'handoff-rule.pdf',
                'application/pdf', 'land-valuation', %s, %s, 100, 1,
                CURRENT_DATE, 'COMPLETED', 'PUBLISHED', %s, now())
        """,
        (
            rule_source_document_id,
            f"HANDOFF-RULE-{rule_source_document_id.hex[:12]}",
            f"knowledge/{rule_source_document_id}/handoff-rule.pdf",
            "c" * 64,
            reviewer_id,
        ),
    )
    admin_cursor.execute(
        """
        INSERT INTO valuation.rule_versions
            (rule_version_id, rule_set_code, version_no, version_name,
             effective_from, status, source_document_id, applicable_case_type,
             applicable_district_code, selection_priority)
        VALUES (%s, %s, 1, 'Handoff rules', CURRENT_DATE, 'PUBLISHED', %s,
                'LAND', 'BANQIAO', 100)
        """,
        (
            rule_version_id,
            f"HANDOFF-RULESET-{rule_version_id.hex[:12]}",
            rule_source_document_id,
        ),
    )
    for rule_id, rule_code, field_name, severity, expression in (
        (
            adjustment_rule_id,
            "ADJUSTMENT_RATE",
            "adjustment_rate",
            "HIGH",
            '{"system_rate":"-5","tolerance":"0"}',
        ),
        (
            grade_rule_id,
            "EXPERT_GRADE",
            "expert_grade",
            "MEDIUM",
            '{"system_grade":"A"}',
        ),
    ):
        admin_cursor.execute(
            """
            INSERT INTO valuation.validation_rules
                (validation_rule_id, rule_version_id, rule_code, rule_name,
                 target_form_code, target_table, target_field_code, severity,
                 rule_expression, message_template, is_active)
            VALUES (%s, %s, %s, %s, 'F02', 'forms', %s, %s, %s, %s, true)
            """,
            (
                rule_id,
                rule_version_id,
                rule_code,
                f"Handoff {rule_code}",
                field_name,
                severity,
                expression,
                f"Handoff {rule_code}",
            ),
        )

    first = _insert_case_graph(
        admin_cursor,
        appraiser_id=appraiser_id,
        source_validation_run_id=source_validation_run_ids[0],
        index=1,
    )
    second = _insert_case_graph(
        admin_cursor,
        appraiser_id=appraiser_id,
        source_validation_run_id=source_validation_run_ids[1],
        index=2,
    )

    # The canonical Review queries join auth.users and resolve published rule
    # sources in knowledge.documents. Those schemas are intentionally not
    # exposed by the submission-only ACL migration, so grant this ephemeral
    # acceptance fixture the read boundary needed by the reviewer flow.
    admin_cursor.execute(
        "GRANT USAGE ON SCHEMA auth, knowledge TO land_valuation_app"
    )
    admin_cursor.connection.commit()
    data = _HandoffData(
        cases=(first, second),
        rule_version_id=rule_version_id,
        validation_rule_ids=(adjustment_rule_id, grade_rule_id),
        rule_source_document_id=rule_source_document_id,
        user_ids=(appraiser_id, reviewer_id),
    )
    try:
        yield data
    finally:
        admin_cursor.connection.rollback()
        case_ids = tuple(case.case_id for case in data.cases)
        review_ids = []
        admin_cursor.execute(
            "SELECT review_id FROM review.reviews WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        review_ids.extend(row[0] for row in admin_cursor.fetchall())
        if review_ids:
            admin_cursor.execute(
                """
                DELETE FROM review.correction_request_items
                WHERE correction_request_id IN (
                    SELECT correction_request_id FROM review.correction_requests
                    WHERE review_id = ANY(%s)
                )
                """,
                (review_ids,),
            )
            admin_cursor.execute(
                "DELETE FROM review.correction_requests WHERE review_id = ANY(%s)",
                (review_ids,),
            )
            admin_cursor.execute(
                "DELETE FROM review.decisions WHERE review_id = ANY(%s)",
                (review_ids,),
            )
            admin_cursor.execute(
                "DELETE FROM review.risk_summaries WHERE review_id = ANY(%s)",
                (review_ids,),
            )
            admin_cursor.execute(
                "DELETE FROM review.findings WHERE review_id = ANY(%s)",
                (review_ids,),
            )
            admin_cursor.execute(
                "DELETE FROM review.missing_items WHERE review_id = ANY(%s)",
                (review_ids,),
            )
            admin_cursor.execute(
                "UPDATE review.reviews SET latest_validation_run_id = NULL, "
                "latest_submission_id = NULL WHERE review_id = ANY(%s)",
                (review_ids,),
            )
        admin_cursor.execute(
            "UPDATE valuation.validation_runs SET submission_id = NULL "
            "WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.review_submissions WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.validation_findings WHERE validation_run_id IN ("
            "SELECT validation_run_id FROM valuation.validation_runs "
            "WHERE case_id = ANY(%s))",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.validation_runs WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        if review_ids:
            admin_cursor.execute(
                "DELETE FROM review.reviews WHERE review_id = ANY(%s)",
                (review_ids,),
            )
        admin_cursor.execute(
            "DELETE FROM history.case_events WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.extracted_fields WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.document_extractions WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.form_instances WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.documents WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.cases WHERE case_id = ANY(%s)",
            (list(case_ids),),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.validation_rules WHERE rule_version_id = %s",
            (data.rule_version_id,),
        )
        admin_cursor.execute(
            "DELETE FROM valuation.rule_versions WHERE rule_version_id = %s",
            (data.rule_version_id,),
        )
        admin_cursor.execute(
            "DELETE FROM knowledge.documents WHERE document_id = %s",
            (data.rule_source_document_id,),
        )
        admin_cursor.execute(
            "DELETE FROM auth.users WHERE user_id = ANY(%s)",
            (list(data.user_ids),),
        )
        admin_cursor.execute(
            "REVOKE USAGE ON SCHEMA auth, knowledge FROM land_valuation_app"
        )
        admin_cursor.connection.commit()


def _actor(user_id: UUID, role_code: str, *permission_codes: str):
    return SimpleNamespace(
        user_id=user_id,
        roles=[
            SimpleNamespace(
                role_code=role_code,
                is_active=True,
                permissions=[
                    SimpleNamespace(permission_code=code)
                    for code in permission_codes
                ],
            )
        ],
    )


async def _status_pair(session, case_id: UUID, review_id: UUID) -> tuple[str, str]:
    row = (
        await session.execute(
            text(
                """
                SELECT r.review_status, c.case_status
                FROM review.reviews AS r
                JOIN valuation.cases AS c ON c.case_id = r.case_id
                WHERE r.review_id = :review_id AND c.case_id = :case_id
                """
            ),
            {"review_id": review_id, "case_id": case_id},
        )
    ).one()
    return row[0], row[1]


async def _run_and_triage(
    session,
    review_service: ReviewService,
    review_id: UUID,
    reviewer_id: UUID,
    *,
    confirmed: bool,
):
    completeness, _, _ = await review_service.check_completeness(
        review_id, reviewer_id
    )
    assert completeness.ready
    await session.commit()
    run, summary = await review_service.create_run(review_id, reviewer_id)
    await session.commit()
    findings = await review_service.list_findings(run.validation_run_id)
    assert findings
    confirmed_finding_id = None
    for index, finding in enumerate(findings):
        decision = (
            "CONFIRMED_ISSUE"
            if confirmed and index == 0
            else "DISMISSED_FALSE_POSITIVE"
        )
        await review_service.triage_finding(
            finding.finding_id,
            FindingTriageRequest(
                review_id=review_id,
                decision=decision,
                reason="人工確認送審資料與檢核結果",
            ),
            reviewer_id,
            uuid4(),
        )
        await session.commit()
        if decision == "CONFIRMED_ISSUE":
            confirmed_finding_id = finding.finding_id
    return run, summary, confirmed_finding_id


@pytest.mark.asyncio
async def test_appraiser_submission_handoff_is_reviewable_and_statuses_pair(
    admin_cursor, handoff_data: _HandoffData
) -> None:
    appraiser_id, reviewer_id = handoff_data.user_ids
    appraiser = _actor(appraiser_id, "APPRAISER", "valuation.submit_review")
    reviewer = _actor(reviewer_id, "REVIEWER", "review.execute", "review.decide")

    commands = tuple(
        SubmitForReviewCommand(
            request_id=uuid4(),
            expected_case_version=1,
            source_validation_run_id=case.source_validation_run_id,
            source_report_document_id=case.document_id,
        )
        for case in handoff_data.cases
    )
    async with AsyncSessionFactory() as session:
        submissions = []
        for case, command in zip(handoff_data.cases, commands):
            submission = await SubmissionService(session).submit(
                case.case_id, command, appraiser
            )
            submissions.append(submission)
        await session.commit()

        workbench = WorkbenchService(
            WorkbenchRepository(session),
            ReviewRepository(session),
            CorrectionRepository(session),
        )
        queue = await workbench.list_cases(None, None, None, None, 100, 0)
        assert {item.review_id for item in queue.items} >= {
            submission.review_id for submission in submissions
        }

        approval_submission = submissions[0]
        approval_case = handoff_data.cases[0]
        detail = await workbench.detail(approval_submission.review_id)
        assert detail.submission_id == approval_submission.submission_id
        assert detail.submission_no == 1
        assert detail.documents[0].original_filename == approval_case.original_filename

        # Change the authoritative Valuation rows after handoff. Review must
        # continue to read the immutable Submission Snapshot.
        admin_cursor.execute(
            "UPDATE valuation.documents SET original_filename = %s WHERE document_id = %s",
            ("changed-after-submit.pdf", approval_case.document_id),
        )
        admin_cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET confirmed_value = to_jsonb('999.0000'::text),
                source_text = 'changed after submit'
            WHERE case_id = %s AND field_name = 'adjustment_rate'
            """,
            (approval_case.case_id,),
        )
        admin_cursor.connection.commit()

        review_repository = ReviewRepository(session)
        review_service = ReviewService(review_repository)
        run, summary, _ = await _run_and_triage(
            session,
            review_service,
            approval_submission.review_id,
            reviewer.user_id,
            confirmed=False,
        )
        assert run.submission_id == approval_submission.submission_id
        assert summary.review_id == approval_submission.review_id
        assert run.input_snapshot["document"]["checksum_sha256"] == "a" * 64
        assert {
            (check["field_code"], check["reported_value"])
            for check in run.input_snapshot["checks"]
        } == {
            ("adjustment_rate", approval_case.adjustment_value),
            ("expert_grade", approval_case.grade_value),
        }
        detail_after_mutation = await workbench.detail(approval_submission.review_id)
        assert (
            detail_after_mutation.documents[0].original_filename
            == approval_case.original_filename
        )

        correction_repository = CorrectionRepository(session)
        corrections = CorrectionService(
            review_repository,
            correction_repository,
            review_service=review_service,
        )
        await corrections.complete_review(
            approval_submission.review_id,
            "送審資料與檢核結果確認無誤",
            reviewer.user_id,
            uuid4(),
        )
        await session.commit()
        assert await _status_pair(
            session, approval_case.case_id, approval_submission.review_id
        ) == ("REVIEW_COMPLETED", "REVIEW_COMPLETED")

        return_submission = submissions[1]
        return_case = handoff_data.cases[1]
        return_run, return_summary, confirmed_finding_id = await _run_and_triage(
            session,
            review_service,
            return_submission.review_id,
            reviewer.user_id,
            confirmed=True,
        )
        assert return_run.submission_id == return_submission.submission_id
        assert return_summary.review_id == return_submission.review_id
        assert confirmed_finding_id is not None

        draft = await corrections.create_draft(
            return_submission.review_id,
            CorrectionRequestCreate(
                message="請修正送審報告中的確認疑點",
                due_at=datetime.now(UTC) + timedelta(days=5),
            ),
            reviewer.user_id,
        )
        await session.commit()
        correction_items = await correction_repository.list_items(
            draft.correction_request_id
        )
        assert [item.finding_id for item in correction_items] == [
            confirmed_finding_id
        ]
        sent = await corrections.send(
            draft.correction_request_id, reviewer.user_id, uuid4()
        )
        await session.commit()
        assert sent.status == "SENT"
        assert await _status_pair(
            session, return_case.case_id, return_submission.review_id
        ) == ("RETURNED_FOR_REVISION", "REVISION_REQUIRED")
