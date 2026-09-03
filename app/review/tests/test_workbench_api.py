from types import SimpleNamespace
from uuid import uuid4
import json

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app
from app.storage.dependencies import get_storage_service
from app.valuation.submissions.snapshot import SNAPSHOT_SCHEMA_VERSION, snapshot_fingerprint


class DownloadObject:
    def __init__(self, content: bytes):
        self.content = content
        self.closed = False

    def stream(self, amt: int):
        for offset in range(0, len(self.content), amt):
            yield self.content[offset : offset + amt]

    def close(self):
        self.closed = True

    def release_conn(self):
        pass


class DocumentStorage:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    async def download(self, object_key: str):
        return DownloadObject(self.objects[object_key])


@pytest.fixture
def workbench_records(postgres_connection):
    user_id = uuid4()
    reviewed_case_id = uuid4()
    eligible_case_id = uuid4()
    completed_case_id = uuid4()
    review_id = uuid4()
    completed_review_id = uuid4()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'not-used', '工作台審查員', true, now(), now())
            """,
            (user_id, f"workbench-{user_id}", f"{user_id}@example.test"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status
            ) VALUES
                (%s, 'WB-REVIEWED', '已進入審查案件', 'LAND', CURRENT_DATE,
                 'F', 'F01', 'DRAFT'),
                (%s, 'WB-ELIGIBLE', '可建立審查案件', 'LAND', CURRENT_DATE,
                 'F', 'F02', 'DRAFT'),
                (%s, 'WB-COMPLETED', '已完成審查案件', 'LAND', CURRENT_DATE,
                 'F', 'F03', 'COMPLETED')
            """,
            (reviewed_case_id, eligible_case_id, completed_case_id),
        )
        cursor.execute(
            """
            INSERT INTO review.reviews (
                review_id, case_id, review_status, started_by_user_id,
                assigned_reviewer_id, received_at, due_at, missing_item_count
            ) VALUES (%s, %s, 'RECEIVED', %s, %s, now(), now() + interval '3 days', 0)
            """,
            (review_id, reviewed_case_id, user_id, user_id),
        )
        cursor.execute(
            """
            INSERT INTO review.reviews (
                review_id, case_id, review_status, started_by_user_id,
                assigned_reviewer_id, received_at, completed_at,
                missing_item_count
            ) VALUES (%s, %s, 'REVIEW_COMPLETED', %s, %s,
                      now() - interval '2 days', now(), 0)
            """,
            (completed_review_id, completed_case_id, user_id, user_id),
        )
    postgres_connection.commit()

    yield SimpleNamespace(
        user_id=user_id,
        review_id=review_id,
        reviewed_case_id=reviewed_case_id,
        eligible_case_id=eligible_case_id,
        completed_case_id=completed_case_id,
        completed_review_id=completed_review_id,
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute("DELETE FROM review.missing_items WHERE review_id = %s", (review_id,))
        cursor.execute(
            "DELETE FROM review.reviews WHERE review_id IN (%s, %s)",
            (review_id, completed_review_id),
        )
        cursor.execute(
            "DELETE FROM valuation.cases WHERE case_id IN (%s, %s, %s)",
            (reviewed_case_id, eligible_case_id, completed_case_id),
        )
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
    postgres_connection.commit()


@pytest.fixture
def workbench_submission(workbench_records, postgres_connection):
    submission_id = uuid4()
    validation_run_id = uuid4()
    document_id = uuid4()
    request_id = uuid4()
    document_group_id = uuid4()
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "case_version": 1,
        "submitted_by_user_id": str(workbench_records.user_id),
        "request_id": str(request_id),
        "applied_fields": [
            {
                "extracted_field_id": str(uuid4()),
                "document_id": str(document_id),
                "form_code": "F03",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12",
                "source_page": 3,
                "source_text": "送審調整率 -12%",
                "confidence": "0.9500",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(workbench_records.user_id),
                "confirmed_at": "2026-09-03T01:00:00+00:00",
            }
        ],
        "calculations": {},
        "documents": [
            {
                "document_id": str(document_id),
                "document_type": "original",
                "original_filename": "submitted.pdf",
                "mime_type": "application/pdf",
                "version_no": 1,
                "document_group_id": str(document_group_id),
                "checksum_sha256": "f" * 64,
                "file_size_bytes": 100,
                "uploaded_at": "2026-09-03T01:00:00+00:00",
                "is_active": True,
            }
        ],
        "validation": {},
    }
    input_fingerprint = snapshot_fingerprint(snapshot)
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO valuation.documents (
                document_id, case_id, document_type, original_filename,
                mime_type, bucket_name, object_key, checksum_sha256,
                file_size_bytes, version_no, uploaded_by_user_id,
                is_active, document_group_id
            ) VALUES (%s, %s, 'original', 'submitted.pdf', 'application/pdf',
                      'land-valuation', %s, %s, 100, 1, %s, true, %s)
            """,
            (
                document_id,
                workbench_records.reviewed_case_id,
                f"cases/{workbench_records.reviewed_case_id}/submitted.pdf",
                "f" * 64,
                workbench_records.user_id,
                document_group_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO valuation.validation_runs (
                validation_run_id, case_id, review_id, run_status,
                input_snapshot, ruleset_snapshot
            ) VALUES (%s, %s, %s, 'COMPLETED', '{}'::jsonb,
                      '{"fixture": true}'::jsonb)
            """,
            (
                validation_run_id,
                workbench_records.reviewed_case_id,
                workbench_records.review_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO valuation.review_submissions (
                submission_id, review_id, case_id, submission_no,
                submitted_by_user_id, submitted_at, source_validation_run_id,
                source_report_document_id, input_snapshot, input_fingerprint,
                request_id
            ) VALUES (%s, %s, %s, 1, %s, '2026-09-03T01:02:03+00:00',
                      %s, %s, %s::jsonb, %s, %s)
            """,
            (
                submission_id,
                workbench_records.review_id,
                workbench_records.reviewed_case_id,
                workbench_records.user_id,
                validation_run_id,
                document_id,
                json.dumps(snapshot),
                input_fingerprint,
                request_id,
            ),
        )
        cursor.execute(
            "UPDATE valuation.validation_runs SET submission_id = %s "
            "WHERE validation_run_id = %s",
            (submission_id, validation_run_id),
        )
        cursor.execute(
            "UPDATE review.reviews SET latest_submission_id = %s WHERE review_id = %s",
            (submission_id, workbench_records.review_id),
        )
    postgres_connection.commit()

    yield SimpleNamespace(
        submission_id=submission_id,
        validation_run_id=validation_run_id,
        document_id=document_id,
        input_fingerprint=input_fingerprint,
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE review.reviews SET latest_submission_id = NULL WHERE review_id = %s",
            (workbench_records.review_id,),
        )
        cursor.execute(
            "UPDATE valuation.validation_runs SET submission_id = NULL "
            "WHERE validation_run_id = %s",
            (validation_run_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.review_submissions WHERE submission_id = %s",
            (submission_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.validation_runs WHERE validation_run_id = %s",
            (validation_run_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.documents WHERE document_id = %s",
            (document_id,),
        )
    postgres_connection.commit()


@pytest.fixture
def workbench_client(workbench_records):
    permission = SimpleNamespace(permission_code="review.execute")
    role = SimpleNamespace(role_code="REVIEWER", is_active=True, permissions=[permission])
    user = SimpleNamespace(user_id=workbench_records.user_id, roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def preview_documents(postgres_connection, workbench_records):
    owned_id = uuid4()
    other_id = uuid4()
    html_id = uuid4()
    records = (
        (
            owned_id,
            workbench_records.reviewed_case_id,
            "owned.pdf",
            "application/pdf",
            "cases/reviewed/owned.pdf",
        ),
        (
            other_id,
            workbench_records.eligible_case_id,
            "other.pdf",
            "application/pdf",
            "cases/eligible/other.pdf",
        ),
        (
            html_id,
            workbench_records.reviewed_case_id,
            "unsafe.html",
            "text/html",
            "cases/reviewed/unsafe.html",
        ),
    )
    with postgres_connection.cursor() as cursor:
        for document_id, case_id, filename, mime_type, object_key in records:
            cursor.execute(
                """
                INSERT INTO valuation.documents (
                    document_id, case_id, document_type, original_filename,
                    mime_type, bucket_name, object_key, checksum_sha256,
                    file_size_bytes, version_no, uploaded_by_user_id,
                    is_active, document_group_id
                ) VALUES (%s, %s, 'original', %s, %s, 'land-valuation', %s,
                          %s, 17, 1, %s, true, %s)
                """,
                (
                    document_id,
                    case_id,
                    filename,
                    mime_type,
                    object_key,
                    document_id.hex * 2,
                    workbench_records.user_id,
                    uuid4(),
                ),
            )
    postgres_connection.commit()

    yield SimpleNamespace(owned_id=owned_id, other_id=other_id, html_id=html_id)

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM valuation.documents WHERE document_id IN (%s, %s, %s)",
            (owned_id, other_id, html_id),
        )
    postgres_connection.commit()


def test_workbench_summary_list_eligible_and_detail(
    workbench_client, workbench_records
):
    summary = workbench_client.get("/api/v1/review/workbench/summary")
    assert summary.status_code == 200
    assert summary.json()["status_counts"]["pending"] >= 1

    listed = workbench_client.get(
        "/api/v1/review/workbench/cases?q=WB-REVIEWED&status=RECEIVED"
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["case_no"] == "WB-REVIEWED"
    assert listed.json()["items"][0]["assigned_reviewer_display_name"] == "工作台審查員"

    completed = workbench_client.get(
        "/api/v1/review/workbench/cases?status_group=completed&limit=1&offset=0"
    )
    assert completed.status_code == 200
    assert completed.json()["total"] == 1
    assert completed.json()["items"][0]["review_status"] == "REVIEW_COMPLETED"

    eligible = workbench_client.get(
        "/api/v1/review/workbench/eligible-cases?q=可建立"
    )
    assert eligible.status_code == 200
    assert [item["case_no"] for item in eligible.json()] == ["WB-ELIGIBLE"]

    detail = workbench_client.get(
        f"/api/v1/review/workbench/cases/{workbench_records.review_id}"
    )
    assert detail.status_code == 200
    assert detail.json()["case"]["case_title"] == "已進入審查案件"
    assert detail.json()["documents"] == []
    assert detail.json()["runs"] == []
    assert detail.json()["version_diffs"] == []


def test_workbench_detail_exposes_submission_provenance_without_snapshot_or_object_key(
    workbench_client, workbench_records, workbench_submission
):
    detail = workbench_client.get(
        f"/api/v1/review/workbench/cases/{workbench_records.review_id}"
    )

    assert detail.status_code == 200
    body = detail.json()
    assert body["submission_id"] == str(workbench_submission.submission_id)
    assert body["submission_no"] == 1
    assert body["submitted_at"] == "2026-09-03T01:02:03Z"
    assert body["input_fingerprint"] == workbench_submission.input_fingerprint
    assert "input_snapshot" not in body
    assert "object_key" not in body


def test_workbench_detail_projects_runs_without_nested_raw_snapshot(
    workbench_client, workbench_records, workbench_submission
):
    detail = workbench_client.get(
        f"/api/v1/review/workbench/cases/{workbench_records.review_id}"
    )

    assert detail.status_code == 200
    runs = detail.json()["runs"]
    assert runs
    assert all("input_snapshot" not in run for run in runs)
    assert all("object_key" not in run for run in runs)
    assert all("bucket_name" not in run for run in runs)
    assert runs[0]["submission_id"] == str(workbench_submission.submission_id)
    assert runs[0]["submission_no"] == 1
    assert runs[0]["input_fingerprint"] == workbench_submission.input_fingerprint


def test_submitted_workbench_detail_uses_snapshot_documents_after_live_change(
    workbench_client, workbench_records, workbench_submission, postgres_connection
):
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "case_version": 1,
        "submitted_by_user_id": str(workbench_records.user_id),
        "request_id": str(uuid4()),
        "applied_fields": [
            {
                "extracted_field_id": str(uuid4()),
                "document_id": str(workbench_submission.document_id),
                "form_code": "F03",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12",
                "source_page": 3,
                "source_text": "送審調整率 -12%",
                "confidence": "0.9500",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(workbench_records.user_id),
                "confirmed_at": "2026-09-03T01:00:00+00:00",
            }
        ],
        "calculations": {},
        "documents": [
            {
                "document_id": str(workbench_submission.document_id),
                "document_type": "original",
                "original_filename": "submitted.pdf",
                "mime_type": "application/pdf",
                "version_no": 1,
                "document_group_id": str(uuid4()),
                "checksum_sha256": "f" * 64,
                "file_size_bytes": 100,
                "uploaded_at": "2026-09-03T01:00:00+00:00",
                "is_active": True,
            }
        ],
        "validation": {},
    }
    post_submission_document_id = uuid4()
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE valuation.review_submissions "
            "SET input_snapshot = %s::jsonb, input_fingerprint = %s "
            "WHERE submission_id = %s",
            (json.dumps(snapshot), snapshot_fingerprint(snapshot), workbench_submission.submission_id),
        )
        cursor.execute(
            """
            INSERT INTO valuation.documents (
                document_id, case_id, document_type, original_filename,
                mime_type, bucket_name, object_key, checksum_sha256,
                file_size_bytes, version_no, uploaded_by_user_id,
                is_active, document_group_id
            ) VALUES (%s, %s, 'original', 'post-submit.pdf', 'application/pdf',
                      'land-valuation', %s, %s, 100, 1, %s, true, %s)
            """,
            (
                post_submission_document_id,
                workbench_records.reviewed_case_id,
                f"cases/{workbench_records.reviewed_case_id}/post-submit.pdf",
                "e" * 64,
                workbench_records.user_id,
                uuid4(),
            ),
        )
    postgres_connection.commit()

    try:
        detail = workbench_client.get(
            f"/api/v1/review/workbench/cases/{workbench_records.review_id}"
        )

        assert detail.status_code == 200
        assert [item["document_id"] for item in detail.json()["documents"]] == [
            str(workbench_submission.document_id)
        ]
    finally:
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM valuation.documents WHERE document_id = %s",
                (post_submission_document_id,),
            )
        postgres_connection.commit()


def test_workbench_detail_does_not_project_latest_submission_onto_legacy_run(
    workbench_client, workbench_records, workbench_submission, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE valuation.validation_runs SET submission_id = NULL "
            "WHERE validation_run_id = %s",
            (workbench_submission.validation_run_id,),
        )
    postgres_connection.commit()

    detail = workbench_client.get(
        f"/api/v1/review/workbench/cases/{workbench_records.review_id}"
    )

    assert detail.status_code == 200
    legacy_run = detail.json()["runs"][0]
    assert legacy_run["submission_id"] is None
    assert legacy_run["submission_no"] is None
    assert legacy_run["submitted_at"] is None
    assert legacy_run["input_fingerprint"] is None


def test_submitted_preflight_uses_snapshot_after_live_field_is_invalidated(
    workbench_client, workbench_records, postgres_connection
):
    # This fixture starts without valuation inputs; create a complete submitted
    # snapshot and then make the live canonical fields unavailable to prove
    # preflight does not fall back.
    with postgres_connection.cursor() as cursor:
        document_id = uuid4()
        document_group_id = uuid4()
        land_register_id = uuid4()
        cadastral_map_id = uuid4()
        parcel_id = uuid4()
        extraction_id = uuid4()
        validation_run_id = uuid4()
        form_instance_id = uuid4()
        source_document_id = uuid4()
        rule_version_id = uuid4()
        adjustment_rule_id = uuid4()
        expert_rule_id = uuid4()
        adjustment_id = uuid4()
        grade_id = uuid4()
        cursor.execute(
            """
            INSERT INTO valuation.documents (
                document_id, case_id, document_type, original_filename,
                mime_type, bucket_name, object_key, checksum_sha256,
                file_size_bytes, version_no, is_active, document_group_id
            ) VALUES (%s, %s, 'original', 'preflight.pdf', 'application/pdf',
                      'land-valuation', %s, %s, 100, 1, true, %s)
            """,
            (
                document_id,
                workbench_records.reviewed_case_id,
                f"cases/{workbench_records.reviewed_case_id}/preflight.pdf",
                "d" * 64,
                document_group_id,
            ),
        )
        for extra_document_id, document_type, filename, checksum in (
            (land_register_id, "land-register", "land-register.pdf", "e" * 64),
            (cadastral_map_id, "cadastral-map", "cadastral-map.pdf", "f" * 64),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.documents (
                    document_id, case_id, document_type, original_filename,
                    mime_type, bucket_name, object_key, checksum_sha256,
                    file_size_bytes, version_no, is_active, document_group_id
                ) VALUES (%s, %s, %s, %s, 'application/pdf', 'land-valuation',
                          %s, %s, 100, 1, true, %s)
                """,
                (
                    extra_document_id,
                    workbench_records.reviewed_case_id,
                    document_type,
                    filename,
                    f"cases/{workbench_records.reviewed_case_id}/{filename}",
                    checksum,
                    uuid4(),
                ),
            )
        cursor.execute(
            """
            INSERT INTO valuation.parcels (
                parcel_id, case_id, district_code, section_name,
                subsection_name, land_no, area_sqm
            ) VALUES (%s, %s, 'F01', '測試段', '', '1', 100)
            """,
            (parcel_id, workbench_records.reviewed_case_id),
        )
        cursor.execute(
            """
            INSERT INTO valuation.form_instances (
                form_instance_id, case_id, form_code, version_no, form_status
            ) VALUES (%s, %s, 'F01', 1, 'READY')
            """,
            (form_instance_id, workbench_records.reviewed_case_id),
        )
        cursor.execute(
            """
            INSERT INTO valuation.document_extractions (
                extraction_id, case_id, document_id, provider,
                extraction_status, created_by_user_id, completed_at
            ) VALUES (%s, %s, %s, 'LOCAL_PDF', 'COMPLETED', %s, now())
            """,
            (extraction_id, workbench_records.reviewed_case_id, document_id, workbench_records.user_id),
        )
        cursor.execute(
            """
            INSERT INTO valuation.validation_runs (
                validation_run_id, case_id, review_id, run_status,
                input_snapshot, ruleset_snapshot
            ) VALUES (%s, %s, %s, 'COMPLETED', '{}'::jsonb,
                      '{"fixture": true}'::jsonb)
            """,
            (
                validation_run_id,
                workbench_records.reviewed_case_id,
                workbench_records.review_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO knowledge.documents (
                document_id, document_code, title, document_type,
                original_filename, mime_type, bucket_name, object_key,
                checksum_sha256, file_size_bytes, version_no, effective_from,
                extraction_status, publication_status, approved_by_user_id,
                approved_at
            ) VALUES (%s, %s, 'Preflight Source', 'REGULATION', 'source.pdf',
                      'application/pdf', 'land-valuation', %s, %s, 100, 1,
                      CURRENT_DATE, 'COMPLETED', 'PUBLISHED', %s, now())
            """,
            (
                source_document_id,
                f"PREFLIGHT-SOURCE-{str(source_document_id)[:8]}",
                f"knowledge/{source_document_id}/source.pdf",
                "a" * 64,
                workbench_records.user_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO valuation.rule_versions (
                rule_version_id, rule_set_code, version_no, version_name,
                effective_from, status, applicable_case_type,
                applicable_district_code, selection_priority, source_document_id
            ) VALUES (%s, %s, 1, 'Preflight Rules', CURRENT_DATE, 'PUBLISHED',
                      'LAND', 'F01', 10, %s)
            """,
            (
                rule_version_id,
                f"PREFLIGHT-RULES-{str(rule_version_id)[:8]}",
                source_document_id,
            ),
        )
        for rule_id, rule_code, field_name, expression in (
            (
                adjustment_rule_id,
                "ADJUSTMENT_RATE",
                "adjustment_rate",
                '{"system_rate":"-5","tolerance":"0"}',
            ),
            (
                expert_rule_id,
                "EXPERT_GRADE",
                "expert_grade",
                '{"system_grade":"A"}',
            ),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.validation_rules (
                    validation_rule_id, rule_version_id, rule_code, rule_name,
                    target_form_code, target_table, target_field_code, severity,
                    rule_expression, message_template, is_active
                ) VALUES (%s, %s, %s, %s, 'F01', 'comparison', %s, 'HIGH',
                          %s, %s, true)
                """,
                (
                    rule_id,
                    rule_version_id,
                    rule_code,
                    rule_code,
                    field_name,
                    expression,
                    rule_code,
                ),
            )
        for field_id, name, value in (
            (adjustment_id, "adjustment_rate", "-12"),
            (grade_id, "expert_grade", "A"),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.extracted_fields (
                    extracted_field_id, case_id, extraction_id, document_id,
                    form_code, field_name, extracted_value, confidence,
                    source_page, source_text, field_status, confirmed_value,
                    confirmed_by_user_id, confirmed_at, applied_form_instance_id,
                    applied_at
                ) VALUES (%s, %s, %s, %s, 'F01', %s, %s::jsonb, 0.9500,
                          3, '原文', 'APPLIED', %s::jsonb, %s, now(), %s, now())
                """,
                (
                    field_id,
                    workbench_records.reviewed_case_id,
                    extraction_id,
                    document_id,
                    name,
                    json.dumps(value),
                    json.dumps(value),
                    workbench_records.user_id,
                    form_instance_id,
                ),
            )
        cursor.execute(
            "UPDATE review.reviews SET latest_submission_id = NULL WHERE review_id = %s",
            (workbench_records.review_id,),
        )
    postgres_connection.commit()

    # The API fixture's helper expects runnable-review ids, so use a minimal
    # direct snapshot through the submission table below.
    snapshot = {
        "schema_version": "valuation-review-submission-v1",
        "case_version": 1,
        "submitted_by_user_id": str(workbench_records.user_id),
        "request_id": str(uuid4()),
        "applied_fields": [
            {
                "extracted_field_id": str(adjustment_id),
                "document_id": str(document_id),
                "form_code": "F01",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12",
                "source_page": 3,
                "source_text": "原文",
                "confidence": "0.9500",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(workbench_records.user_id),
                "confirmed_at": "2026-09-03T00:00:00+00:00",
            },
            {
                "extracted_field_id": str(grade_id),
                "document_id": str(document_id),
                "form_code": "F01",
                "field_name": "expert_grade",
                "confirmed_value": "A",
                "source_page": 3,
                "source_text": "原文",
                "confidence": "0.9500",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(workbench_records.user_id),
                "confirmed_at": "2026-09-03T00:00:00+00:00",
            },
        ],
        "calculations": {},
        "documents": [
            {
                "document_id": str(document_id),
                "document_type": "original",
                "original_filename": "preflight.pdf",
                "mime_type": "application/pdf",
                "version_no": 1,
                "document_group_id": str(document_group_id),
                "checksum_sha256": "d" * 64,
                "file_size_bytes": 100,
                "uploaded_at": "2026-09-03T00:00:00+00:00",
                "is_active": True,
            }
        ],
        "validation": {},
    }
    submission_id = uuid4()
    from app.valuation.submissions.snapshot import snapshot_fingerprint

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO valuation.review_submissions (
                submission_id, review_id, case_id, submission_no,
                submitted_by_user_id, source_validation_run_id,
                source_report_document_id, input_snapshot, input_fingerprint,
                request_id
            ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                submission_id,
                workbench_records.review_id,
                workbench_records.reviewed_case_id,
                workbench_records.user_id,
                validation_run_id,
                document_id,
                json.dumps(snapshot),
                snapshot_fingerprint(snapshot),
                uuid4(),
            ),
        )
        cursor.execute(
            "UPDATE review.reviews SET latest_submission_id = %s WHERE review_id = %s",
            (submission_id, workbench_records.review_id),
        )
        cursor.execute(
            """
            UPDATE valuation.extracted_fields
            SET field_status = 'NEEDS_CONFIRMATION', confirmed_value = NULL,
                confirmed_by_user_id = NULL, confirmed_at = NULL,
                applied_form_instance_id = NULL, applied_at = NULL
            WHERE case_id = %s
            """,
            (workbench_records.reviewed_case_id,),
        )
        cursor.execute(
            "UPDATE valuation.documents SET is_active = false WHERE case_id = %s",
            (workbench_records.reviewed_case_id,),
        )
        cursor.execute(
            "DELETE FROM valuation.parcels WHERE parcel_id = %s",
            (parcel_id,),
        )
        cursor.execute(
            "UPDATE valuation.cases SET case_no = '' WHERE case_id = %s",
            (workbench_records.reviewed_case_id,),
        )
    postgres_connection.commit()

    try:
        response = workbench_client.post(
            f"/api/v1/review/workbench/cases/{workbench_records.review_id}/start/preflight"
        )

        assert response.status_code == 200
        assert response.json()["outcome"] == "READY"
    finally:
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE review.reviews SET latest_submission_id = NULL "
                "WHERE review_id = %s",
                (workbench_records.review_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.review_submissions WHERE submission_id = %s",
                (submission_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.validation_runs WHERE validation_run_id = %s",
                (validation_run_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.extracted_fields WHERE extraction_id = %s",
                (extraction_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.document_extractions WHERE extraction_id = %s",
                (extraction_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.form_instances WHERE form_instance_id = %s",
                (form_instance_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.parcels WHERE parcel_id = %s",
                (parcel_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.documents WHERE document_id IN (%s, %s, %s)",
                (document_id, land_register_id, cadastral_map_id),
            )
            cursor.execute(
                "DELETE FROM valuation.validation_rules WHERE rule_version_id = %s",
                (rule_version_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.rule_versions WHERE rule_version_id = %s",
                (rule_version_id,),
            )
            cursor.execute(
                "DELETE FROM knowledge.documents WHERE document_id = %s",
                (source_document_id,),
            )
        postgres_connection.commit()


def test_submitted_preflight_rejects_invalid_snapshot_before_live_completeness(
    workbench_client, workbench_records, workbench_submission, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT input_snapshot FROM valuation.review_submissions "
            "WHERE submission_id = %s",
            (workbench_submission.submission_id,),
        )
        original_snapshot = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE valuation.review_submissions SET input_snapshot = '{}'::jsonb "
            "WHERE submission_id = %s",
            (workbench_submission.submission_id,),
        )
    postgres_connection.commit()

    try:
        response = workbench_client.post(
            f"/api/v1/review/workbench/cases/{workbench_records.review_id}/start/preflight"
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SUBMISSION_SNAPSHOT_INVALID"
    finally:
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE valuation.review_submissions SET input_snapshot = %s::jsonb "
                "WHERE submission_id = %s",
                (json.dumps(original_snapshot), workbench_submission.submission_id),
            )
        postgres_connection.commit()


def test_run_provenance_does_not_cross_review_or_case(
    workbench_client, workbench_records, workbench_submission, postgres_connection
):
    scenarios = (
        ("review_id", workbench_records.completed_review_id),
        ("case_id", workbench_records.completed_case_id),
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE review.reviews SET latest_submission_id = NULL WHERE review_id = %s",
            (workbench_records.review_id,),
        )
    postgres_connection.commit()

    try:
        for owner_column, foreign_value in scenarios:
            with postgres_connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE valuation.review_submissions SET {owner_column} = %s "
                    "WHERE submission_id = %s",
                    (foreign_value, workbench_submission.submission_id),
                )
            postgres_connection.commit()

            detail = workbench_client.get(
                f"/api/v1/review/workbench/cases/{workbench_records.review_id}"
            )

            assert detail.status_code == 200
            run = detail.json()["runs"][0]
            assert run["submission_no"] is None
            assert run["submitted_at"] is None
            assert run["input_fingerprint"] is None

            with postgres_connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE valuation.review_submissions SET {owner_column} = %s "
                    "WHERE submission_id = %s",
                    (
                        workbench_records.review_id
                        if owner_column == "review_id"
                        else workbench_records.reviewed_case_id,
                        workbench_submission.submission_id,
                    ),
                )
            postgres_connection.commit()
    finally:
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE valuation.review_submissions SET review_id = %s, case_id = %s "
                "WHERE submission_id = %s",
                (
                    workbench_records.review_id,
                    workbench_records.reviewed_case_id,
                    workbench_submission.submission_id,
                ),
            )
        postgres_connection.commit()


def test_workbench_start_blocked_does_not_create_run(
    workbench_client, workbench_records, postgres_connection
):
    response = workbench_client.post(
        f"/api/v1/review/workbench/cases/{workbench_records.review_id}/start"
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "BLOCKED"
    assert response.json()["run"] is None
    assert response.json()["completeness"]["ready"] is False
    assert response.json()["completeness"]["items"]

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
            (workbench_records.review_id,),
        )
        assert cursor.fetchone()[0] == 0


def test_workbench_preflight_blocked_does_not_create_run(
    workbench_client, workbench_records, postgres_connection
):
    response = workbench_client.post(
        "/api/v1/review/workbench/cases/"
        f"{workbench_records.review_id}/start/preflight"
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "BLOCKED"
    assert response.json()["completeness"]["ready"] is False
    assert response.json()["completeness"]["items"]

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM valuation.validation_runs WHERE review_id = %s",
            (workbench_records.review_id,),
        )
        assert cursor.fetchone()[0] == 0


def test_workbench_document_content_streams_owned_pdf(
    workbench_client, workbench_records, preview_documents
):
    storage = DocumentStorage({"cases/reviewed/owned.pdf": b"%PDF-review-owned"})
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        response = workbench_client.get(
            "/api/v1/review/workbench/cases/"
            f"{workbench_records.review_id}/documents/"
            f"{preview_documents.owned_id}/content"
        )
    finally:
        app.dependency_overrides.pop(get_storage_service, None)

    assert response.status_code == 200
    assert response.content == b"%PDF-review-owned"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_workbench_document_content_rejects_cross_case_and_missing_documents(
    workbench_client, workbench_records, preview_documents
):
    cross_case = workbench_client.get(
        "/api/v1/review/workbench/cases/"
        f"{workbench_records.review_id}/documents/"
        f"{preview_documents.other_id}/content"
    )
    missing = workbench_client.get(
        "/api/v1/review/workbench/cases/"
        f"{workbench_records.review_id}/documents/{uuid4()}/content"
    )

    assert cross_case.status_code == 404
    assert missing.status_code == 404


def test_workbench_document_content_rejects_active_content(
    workbench_client, workbench_records, preview_documents
):
    response = workbench_client.get(
        "/api/v1/review/workbench/cases/"
        f"{workbench_records.review_id}/documents/"
        f"{preview_documents.html_id}/content"
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "REVIEW_DOCUMENT_PREVIEW_UNSUPPORTED"


def test_workbench_case_list_exposes_urgency_separate_from_risk(
    workbench_client, workbench_records
):
    listed = workbench_client.get(
        "/api/v1/review/workbench/cases?q=WB-REVIEWED&status=RECEIVED"
    )
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    # due_at is now + 3 days, which is inside the default urgent_days=3 window.
    assert item["urgency_level"] == "URGENT"
    assert item["remaining_days"] == 2
    assert item["correction_round"] == 0
    assert item["latest_correction_status"] is None
    # Deadline urgency must never be reported as content risk.
    assert item["current_risk_level"] != item["urgency_level"]
    assert {"high_count", "medium_count", "low_count"} <= item.keys()


def test_workbench_case_without_deadline_is_not_set(
    workbench_client, workbench_records, postgres_connection
):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE review.reviews SET due_at = NULL WHERE review_id = %s",
            (workbench_records.review_id,),
        )
    postgres_connection.commit()
    listed = workbench_client.get(
        "/api/v1/review/workbench/cases?q=WB-REVIEWED&status=RECEIVED"
    )
    item = listed.json()["items"][0]
    assert item["urgency_level"] == "NOT_SET"
    assert item["remaining_days"] is None


def test_urgency_settings_get_returns_seeded_defaults(workbench_client):
    response = workbench_client.get("/api/v1/review/settings/urgency")
    assert response.status_code == 200
    body = response.json()
    assert body["urgent_days"] == 3
    assert body["due_soon_days"] == 7


def test_urgency_settings_put_requires_supervisor_permission(workbench_client):
    # workbench_client only holds review.execute.
    response = workbench_client.put(
        "/api/v1/review/settings/urgency",
        json={"urgent_days": 1, "due_soon_days": 5},
    )
    assert response.status_code == 403


def test_urgency_settings_put_rejects_invalid_pair(
    workbench_records, postgres_connection
):
    permissions = [
        SimpleNamespace(permission_code="review.execute"),
        SimpleNamespace(permission_code="review.override_high_risk"),
    ]
    role = SimpleNamespace(
        role_code="SUPERVISOR", is_active=True, permissions=permissions
    )
    user = SimpleNamespace(user_id=workbench_records.user_id, roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            invalid = client.put(
                "/api/v1/review/settings/urgency",
                json={"urgent_days": 7, "due_soon_days": 3},
            )
            assert invalid.status_code == 422
            updated = client.put(
                "/api/v1/review/settings/urgency",
                json={"urgent_days": 1, "due_soon_days": 5},
            )
            assert updated.status_code == 200
            assert updated.json()["urgent_days"] == 1
            # Restore the seeded defaults for other tests.
            client.put(
                "/api/v1/review/settings/urgency",
                json={"urgent_days": 3, "due_soon_days": 7},
            )
    finally:
        app.dependency_overrides.clear()
        # Release the settings FK so the shared user fixture can be deleted.
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE review.urgency_settings SET updated_by_user_id = NULL"
            )
        postgres_connection.commit()


def test_workbench_detail_never_exposes_storage_internals(
    workbench_client, workbench_records
):
    detail = workbench_client.get(
        f"/api/v1/review/workbench/cases/{workbench_records.review_id}"
    )
    assert detail.status_code == 200
    body = detail.text
    assert "bucket_name" not in body
    assert "object_key" not in body
    assert "land-valuation" not in body
    assert "localhost" not in body
    assert detail.json()["generated_reports"] == []
