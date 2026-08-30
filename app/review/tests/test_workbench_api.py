from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app
from app.storage.dependencies import get_storage_service


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
