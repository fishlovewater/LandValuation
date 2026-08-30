from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app


@pytest.fixture
def queue_case(postgres_connection):
    user_id = uuid4()
    case_id = uuid4()
    case_no = f"QUEUE-{str(case_id)[:8]}"
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, 'not-used', 'Queue Tester', true, now(), now())
            """,
            (user_id, f"queue-{user_id}", f"{user_id}@example.test"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, case_status
            ) VALUES (%s, %s, 'Queue API Case', 'LAND', CURRENT_DATE,
                      'F', 'F01', 'DRAFT')
            """,
            (case_id, case_no),
        )
    postgres_connection.commit()

    yield SimpleNamespace(user_id=user_id, case_id=case_id, case_no=case_no)

    with postgres_connection.cursor() as cursor:
        cursor.execute("DELETE FROM review.reviews WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
    postgres_connection.commit()


@pytest.fixture
def authorized_client(queue_case):
    permission = SimpleNamespace(permission_code="review.execute")
    role = SimpleNamespace(role_code="APPRAISER", is_active=True, permissions=[permission])
    user = SimpleNamespace(user_id=queue_case.user_id, roles=[role])
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_create_list_get_assign_and_prioritize_review_case(authorized_client, queue_case):
    received_at = datetime.now(UTC).replace(microsecond=0)
    response = authorized_client.post(
        "/api/v1/review/cases",
        json={
            "case_id": str(queue_case.case_id),
            "received_at": received_at.isoformat(),
            "due_at": (received_at + timedelta(days=3)).isoformat(),
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["case_id"] == str(queue_case.case_id)
    assert created["review_status"] == "RECEIVED"
    assert created["manual_priority"] == 0

    review_id = created["review_id"]
    listed = authorized_client.get("/api/v1/review/cases?status=RECEIVED")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert review_id in {item["review_id"] for item in listed.json()["items"]}

    fetched = authorized_client.get(f"/api/v1/review/cases/{review_id}")
    assert fetched.status_code == 200
    assert fetched.json()["case_id"] == str(queue_case.case_id)

    assigned = authorized_client.post(
        f"/api/v1/review/cases/{review_id}/assign",
        json={"reviewer_id": str(queue_case.user_id)},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_reviewer_id"] == str(queue_case.user_id)

    prioritized = authorized_client.post(
        f"/api/v1/review/cases/{review_id}/priority",
        json={"priority": 90, "reason": "法定期限將屆"},
    )
    assert prioritized.status_code == 200
    assert prioritized.json()["manual_priority"] == 90
    assert prioritized.json()["manual_priority_reason"] == "法定期限將屆"


def test_update_rejects_illegal_status_transition(authorized_client, queue_case):
    created = authorized_client.post(
        "/api/v1/review/cases", json={"case_id": str(queue_case.case_id)}
    ).json()

    response = authorized_client.patch(
        f"/api/v1/review/cases/{created['review_id']}",
        json={"review_status": "APPROVED"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEW_DECISION_INVALID"


def test_get_unknown_review_returns_404(authorized_client):
    response = authorized_client.get(f"/api/v1/review/cases/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {"priority": 101, "reason": "too high"},
        {"priority": 10, "reason": "   "},
    ],
)
def test_priority_validates_range_and_reason(authorized_client, payload):
    response = authorized_client.post(
        f"/api/v1/review/cases/{uuid4()}/priority", json=payload
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
