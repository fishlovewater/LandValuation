from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


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
