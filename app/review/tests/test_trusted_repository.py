from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.session import AsyncSessionFactory
from app.review.repository import ReviewRepository


@pytest.fixture
def trusted_repository_data(postgres_connection):
    ids = SimpleNamespace(
        user_id=uuid4(),
        case_id=uuid4(),
        other_case_id=uuid4(),
        document_group_id=uuid4(),
        original_v1_id=uuid4(),
        original_v2_id=uuid4(),
        inactive_original_v99_id=uuid4(),
        other_document_id=uuid4(),
        extraction_v1_id=uuid4(),
        extraction_v2_id=uuid4(),
        other_extraction_id=uuid4(),
        wrong_version_extraction_id=uuid4(),
        pending_extraction_id=uuid4(),
        source_document_id=uuid4(),
        completed_draft_source_document_id=uuid4(),
        pending_published_source_document_id=uuid4(),
        published_rule_version_id=uuid4(),
        draft_rule_version_id=uuid4(),
        global_rule_id=uuid4(),
        f01_rule_id=uuid4(),
        f02_rule_id=uuid4(),
        inactive_rule_id=uuid4(),
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'not-used', 'Trusted Repository Tester',
                      true, now(), now())
            """,
            (ids.user_id, f"trusted-repository-{ids.user_id}", f"{ids.user_id}@example.test"),
        )
        for case_id, case_no in (
            (ids.case_id, f"TRUSTED-{str(ids.case_id)[:8]}"),
            (ids.other_case_id, f"OTHER-{str(ids.other_case_id)[:8]}"),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.cases (
                    case_id, case_no, case_title, case_type,
                    valuation_base_date, city_code, district_code, case_status
                ) VALUES (%s, %s, 'Trusted Repository Case', 'LAND',
                          DATE '2026-08-25', 'F', 'F01', 'DRAFT')
                """,
                (case_id, case_no),
            )
        for document_id, case_id, filename, checksum, version_no, group_id, is_active in (
            (
                ids.original_v1_id,
                ids.case_id,
                "original-v1.pdf",
                "1" * 64,
                1,
                ids.document_group_id,
                True,
            ),
            (
                ids.original_v2_id,
                ids.case_id,
                "original-v2.pdf",
                "2" * 64,
                2,
                ids.document_group_id,
                True,
            ),
            (
                ids.inactive_original_v99_id,
                ids.case_id,
                "original-inactive-v99.pdf",
                "9" * 64,
                99,
                ids.document_group_id,
                False,
            ),
            (
                ids.other_document_id,
                ids.other_case_id,
                "other-original.pdf",
                "3" * 64,
                9,
                uuid4(),
                True,
            ),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.documents (
                    document_id, case_id, document_type, original_filename,
                    mime_type, bucket_name, object_key, checksum_sha256,
                    file_size_bytes, version_no, is_active, document_group_id
                    ) VALUES (%s, %s, 'original', %s, 'application/pdf',
                              'land-valuation', %s, %s, 100, %s, %s, %s)
                """,
                (
                    document_id,
                    case_id,
                    filename,
                    f"cases/{case_id}/{filename}",
                    checksum,
                    version_no,
                    is_active,
                    group_id,
                ),
            )
        cursor.execute(
            """
            INSERT INTO valuation.form_instances (
                form_instance_id, case_id, form_code, version_no, form_status
            ) VALUES (%s, %s, 'F01', 1, 'READY'),
                     (%s, %s, 'F02', 1, 'VOID')
            """,
            (uuid4(), ids.case_id, uuid4(), ids.case_id),
        )
        for extraction_id, case_id, document_id, version_no, run_no, status in (
            (ids.extraction_v1_id, ids.case_id, ids.original_v1_id, 1, 1, "COMPLETED"),
            (ids.extraction_v2_id, ids.case_id, ids.original_v2_id, 2, 2, "COMPLETED"),
            (ids.other_extraction_id, ids.other_case_id, ids.other_document_id, 9, 99, "COMPLETED"),
            (ids.wrong_version_extraction_id, ids.case_id, ids.original_v2_id, 1, 100, "COMPLETED"),
            (ids.pending_extraction_id, ids.case_id, ids.original_v2_id, 2, 99, "PENDING"),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.extraction_runs (
                    extraction_run_id, case_id, document_id, document_version,
                    run_no, status, extractor_name, started_at, completed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'fixture',
                          now() - interval '1 minute',
                          CASE WHEN %s = 'COMPLETED' THEN now() ELSE NULL END)
                """,
                (extraction_id, case_id, document_id, version_no, run_no, status, status),
            )
        for field_code, value_type, raw_text, normalized_value, is_official in (
            ("adjustment_rate", "DECIMAL", "-5%", '"-5"', True),
            ("expert_grade", "TEXT", "A 級", '"A"', True),
            ("nonofficial_only", "TEXT", "草稿欄位", '"draft"', False),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.extracted_fields (
                    extracted_field_id, extraction_run_id, field_code, field_path,
                    value_type, raw_text, normalized_value, page_number,
                    verification_status, is_official
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 1,
                              'AUTO_EXTRACTED', %s)
                """,
                (
                    uuid4(),
                    ids.extraction_v2_id,
                    field_code,
                    f"report.{field_code}",
                    value_type,
                    raw_text,
                    normalized_value,
                    is_official,
                ),
            )
        for document_id, document_code, filename, checksum, extraction_status, publication_status in (
            (
                ids.source_document_id,
                f"TRUSTED-SOURCE-{str(ids.source_document_id)[:8]}",
                "trusted-source.pdf",
                "a" * 64,
                "COMPLETED",
                "PUBLISHED",
            ),
            (
                ids.completed_draft_source_document_id,
                f"COMPLETED-DRAFT-{str(ids.completed_draft_source_document_id)[:8]}",
                "completed-draft-source.pdf",
                "b" * 64,
                "COMPLETED",
                "DRAFT",
            ),
            (
                ids.pending_published_source_document_id,
                f"PENDING-PUBLISHED-{str(ids.pending_published_source_document_id)[:8]}",
                "pending-published-source.pdf",
                "c" * 64,
                "PENDING",
                "PUBLISHED",
            ),
        ):
            approved_by_user_id = (
                ids.user_id if publication_status == "PUBLISHED" else None
            )
            approved_at = datetime.now(UTC) if approved_by_user_id else None
            cursor.execute(
                """
                INSERT INTO knowledge.documents (
                    document_id, document_code, title, document_type,
                    original_filename, mime_type, bucket_name, object_key,
                    checksum_sha256, file_size_bytes, version_no, effective_from,
                    effective_to, extraction_status, publication_status,
                    approved_by_user_id, approved_at
                ) VALUES (%s, %s, 'Trusted Source', 'REGULATION', %s,
                          'application/pdf', 'land-valuation', %s, %s, 100, 3,
                          DATE '2026-01-01', DATE '2026-12-31', %s, %s, %s, %s)
                """,
                (
                    document_id,
                    document_code,
                    filename,
                    f"knowledge/rules/{document_id}/{filename}",
                    checksum,
                    extraction_status,
                    publication_status,
                    approved_by_user_id,
                    approved_at,
                ),
            )
        cursor.execute(
            """
            INSERT INTO valuation.rule_versions (
                rule_version_id, rule_set_code, version_no, version_name,
                effective_from, status, applicable_case_type,
                applicable_district_code, selection_priority, source_document_id
            ) VALUES (%s, %s, 1, 'Published Rules', DATE '2026-01-01',
                      'PUBLISHED', 'LAND', 'F01', 10, %s),
                     (%s, %s, 1, 'Draft Rules', DATE '2026-01-01',
                      'DRAFT', NULL, NULL, 0, NULL)
            """,
            (
                ids.published_rule_version_id,
                f"TRUSTED_{str(ids.published_rule_version_id)[:8]}",
                ids.source_document_id,
                ids.draft_rule_version_id,
                f"DRAFT_{str(ids.draft_rule_version_id)[:8]}",
            ),
        )
        for rule_id, rule_code, target_form_code, is_active in (
            (ids.global_rule_id, "GLOBAL", None, True),
            (ids.f01_rule_id, "F01", "F01", True),
            (ids.f02_rule_id, "F02", "F02", True),
            (ids.inactive_rule_id, "INACTIVE", "F01", False),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.validation_rules (
                    validation_rule_id, rule_version_id, rule_code, rule_name,
                    target_form_code, target_table, target_field_code, severity,
                    rule_expression, message_template, is_active
                ) VALUES (%s, %s, %s, %s, %s, 'comparison',
                          'adjustment_rate', 'HIGH', '{}', %s, %s)
                """,
                (
                    rule_id,
                    ids.published_rule_version_id,
                    rule_code,
                    rule_code,
                    target_form_code,
                    rule_code,
                    is_active,
                ),
            )
    postgres_connection.commit()
    yield ids
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM valuation.extracted_fields WHERE extraction_run_id IN (%s, %s, %s, %s, %s)",
            (
                ids.extraction_v1_id,
                ids.extraction_v2_id,
                ids.other_extraction_id,
                ids.wrong_version_extraction_id,
                ids.pending_extraction_id,
            ),
        )
        cursor.execute(
            "DELETE FROM valuation.extraction_runs WHERE extraction_run_id IN (%s, %s, %s, %s, %s)",
            (
                ids.extraction_v1_id,
                ids.extraction_v2_id,
                ids.other_extraction_id,
                ids.wrong_version_extraction_id,
                ids.pending_extraction_id,
            ),
        )
        cursor.execute(
            "DELETE FROM valuation.validation_rules WHERE rule_version_id IN (%s, %s)",
            (ids.published_rule_version_id, ids.draft_rule_version_id),
        )
        cursor.execute(
            "DELETE FROM valuation.rule_versions WHERE rule_version_id IN (%s, %s)",
            (ids.published_rule_version_id, ids.draft_rule_version_id),
        )
        cursor.execute(
            "DELETE FROM knowledge.documents WHERE document_id IN (%s, %s, %s)",
            (
                ids.source_document_id,
                ids.completed_draft_source_document_id,
                ids.pending_published_source_document_id,
            ),
        )
        cursor.execute("DELETE FROM valuation.form_instances WHERE case_id = %s", (ids.case_id,))
        cursor.execute(
            "DELETE FROM valuation.documents WHERE case_id IN (%s, %s)",
            (ids.case_id, ids.other_case_id),
        )
        cursor.execute(
            "DELETE FROM valuation.cases WHERE case_id IN (%s, %s)",
            (ids.case_id, ids.other_case_id),
        )
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (ids.user_id,))
    postgres_connection.commit()


@pytest.mark.asyncio
async def test_loads_only_server_owned_trusted_context(trusted_repository_data):
    async with AsyncSessionFactory() as session:
        repository = ReviewRepository(session)

        document = await repository.get_latest_original_document(
            trusted_repository_data.case_id
        )
        assert document["document_id"] == trusted_repository_data.original_v2_id
        assert document["version_no"] == 2

        extraction = await repository.get_latest_completed_extraction(
            document["document_id"], document["version_no"]
        )
        assert extraction["extraction_run_id"] == trusted_repository_data.extraction_v2_id
        assert extraction["status"] == "COMPLETED"
        assert extraction["extraction_run_id"] != trusted_repository_data.other_extraction_id

        fields = await repository.list_official_extracted_fields(
            extraction["extraction_run_id"]
        )
        assert {row["field_code"] for row in fields} == {
            "adjustment_rate",
            "expert_grade",
        }

        context = await repository.get_case_rule_context(trusted_repository_data.case_id)
        assert context["case_type"] == "LAND"
        assert context["district_code"] == "F01"
        assert context["form_codes"] == frozenset({"F01"})

        candidates = await repository.list_rule_candidates()
        published = next(
            row
            for row in candidates
            if row["rule_version_id"] == trusted_repository_data.published_rule_version_id
        )
        assert published["applicable_case_type"] == "LAND"
        assert published["applicable_district_code"] == "F01"
        assert published["status"] == "PUBLISHED"
        assert published["effective_from"] == date(2026, 1, 1)
        assert published["effective_to"] is None
        assert published["selection_priority"] == 10
        assert published["source_document_id"] == trusted_repository_data.source_document_id
        assert {
            row["rule_version_id"] for row in candidates
        } >= {
            trusted_repository_data.published_rule_version_id,
            trusted_repository_data.draft_rule_version_id,
        }

        active_rules = await repository.list_active_rules(
            trusted_repository_data.published_rule_version_id,
            context["form_codes"],
        )
        assert {row["validation_rule_id"] for row in active_rules} == {
            trusted_repository_data.global_rule_id,
            trusted_repository_data.f01_rule_id,
        }

        source = await repository.get_rule_source(
            trusted_repository_data.source_document_id, date(2026, 8, 25)
        )
        assert source == {
            "document_id": trusted_repository_data.source_document_id,
            "checksum_sha256": "a" * 64,
            "version_no": 3,
            "effective_from": date(2026, 1, 1),
            "effective_to": date(2026, 12, 31),
        }
        assert await repository.get_rule_source(
            trusted_repository_data.completed_draft_source_document_id,
            date(2026, 8, 25),
        ) is None
        assert await repository.get_rule_source(
            trusted_repository_data.pending_published_source_document_id,
            date(2026, 8, 25),
        ) is None
