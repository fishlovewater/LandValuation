from uuid import uuid4

import pytest

from app.knowledge.case_repository import CaseContextRepository


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Rows(self._rows)


class _Session:
    def __init__(self, review, findings, missing_items):
        self.review = review
        self.findings = findings
        self.missing_items = missing_items
        self.calls = []

    async def execute(self, statement, params):
        sql = statement.text
        self.calls.append((sql, params))
        if "FROM review.reviews" in sql:
            return _Result([self.review])
        if "FROM review.findings" in sql:
            rows = self.findings
            if "validation_run_id = :validation_run_id" in sql:
                rows = [
                    row
                    for row in rows
                    if row["validation_run_id"] == params["validation_run_id"]
                ]
            return _Result(rows)
        if "FROM review.missing_items" in sql:
            return _Result(self.missing_items)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_latest_review_excludes_stale_findings_but_keeps_review_missing_items():
    review_id = uuid4()
    current_run_id = uuid4()
    stale_run_id = uuid4()
    session = _Session(
        {
            "review_id": review_id,
            "review_type": "AI_ASSISTED",
            "review_status": "REVIEW_REQUIRED",
            "started_at": "2026-09-06T00:00:00Z",
            "completed_at": None,
            "latest_validation_run_id": current_run_id,
            "overall_risk_level": None,
            "risk_score": None,
            "summary": None,
            "category_scores": {},
        },
        [
            {"finding_id": uuid4(), "validation_run_id": stale_run_id},
            {"finding_id": uuid4(), "validation_run_id": current_run_id},
        ],
        [
            {"missing_item_id": uuid4(), "validation_run_id": stale_run_id},
            {"missing_item_id": uuid4(), "validation_run_id": current_run_id},
        ],
    )

    result = await CaseContextRepository(session).latest_review(uuid4())

    assert [item["validation_run_id"] for item in result["findings"]] == [
        current_run_id
    ]
    assert [item["validation_run_id"] for item in result["missing_items"]] == [
        stale_run_id,
        current_run_id,
    ]
    findings_call = next(
        (call for call in session.calls if "FROM review.findings" in call[0]), None
    )
    assert findings_call is not None
    assert findings_call[1]["validation_run_id"] == current_run_id
