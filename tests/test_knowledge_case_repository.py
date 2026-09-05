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
    def __init__(self, review, findings, missing_items, risk_summaries=None):
        self.review = review
        self.findings = findings
        self.missing_items = missing_items
        self.risk_summaries = risk_summaries
        self.calls = []

    async def execute(self, statement, params):
        sql = statement.text
        self.calls.append((sql, params))
        if "FROM review.reviews" in sql:
            row = dict(self.review)
            if self.risk_summaries is not None:
                normalized_sql = " ".join(sql.split())
                if "rs.validation_run_id = r.latest_validation_run_id" in normalized_sql:
                    summary = next(
                        (
                            item
                            for item in self.risk_summaries
                            if item["validation_run_id"] is not None
                            and row["latest_validation_run_id"] is not None
                            if item["validation_run_id"]
                            == row["latest_validation_run_id"]
                        ),
                        None,
                    )
                else:
                    summary = self.risk_summaries[0] if self.risk_summaries else None
                row.update(
                    {
                        "overall_risk_level": (
                            summary["overall_risk_level"] if summary else None
                        ),
                        "risk_score": summary["risk_score"] if summary else None,
                        "summary": summary["summary"] if summary else None,
                        "category_scores": (
                            summary["category_scores"] if summary else {}
                        ),
                    }
                )
            return _Result([row])
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


@pytest.mark.asyncio
async def test_latest_review_uses_risk_summary_for_latest_validation_run():
    review_id = uuid4()
    run1_id = uuid4()
    run2_id = uuid4()
    session = _Session(
        {
            "review_id": review_id,
            "review_type": "AI_ASSISTED",
            "review_status": "REVIEW_REQUIRED",
            "started_at": "2026-09-06T00:00:00Z",
            "completed_at": None,
            "latest_validation_run_id": run2_id,
        },
        [],
        [],
        [
            {
                "validation_run_id": run1_id,
                "overall_risk_level": "HIGH",
                "risk_score": 80,
                "summary": "run 1",
                "category_scores": {"run": 1},
            },
            {
                "validation_run_id": run2_id,
                "overall_risk_level": "LOW",
                "risk_score": 20,
                "summary": "run 2",
                "category_scores": {"run": 2},
            },
        ],
    )

    result = await CaseContextRepository(session).latest_review(uuid4())

    assert result["latest_validation_run_id"] == run2_id
    assert result["overall_risk_level"] == "LOW"
    assert result["risk_score"] == 20
    assert result["summary"] == "run 2"
    assert result["category_scores"] == {"run": 2}


@pytest.mark.asyncio
async def test_latest_review_returns_empty_risk_fields_when_latest_run_has_no_summary():
    review_id = uuid4()
    run1_id = uuid4()
    run2_id = uuid4()
    session = _Session(
        {
            "review_id": review_id,
            "review_type": "AI_ASSISTED",
            "review_status": "REVIEW_REQUIRED",
            "started_at": "2026-09-06T00:00:00Z",
            "completed_at": None,
            "latest_validation_run_id": run2_id,
        },
        [],
        [],
        [
            {
                "validation_run_id": run1_id,
                "overall_risk_level": "HIGH",
                "risk_score": 80,
                "summary": "stale run 1",
                "category_scores": {"run": 1},
            },
            {
                "validation_run_id": None,
                "overall_risk_level": "MEDIUM",
                "risk_score": 50,
                "summary": "legacy summary",
                "category_scores": {"legacy": True},
            },
        ],
    )

    result = await CaseContextRepository(session).latest_review(uuid4())

    assert result["latest_validation_run_id"] == run2_id
    assert result["overall_risk_level"] is None
    assert result["risk_score"] is None
    assert result["summary"] is None
    assert result["category_scores"] == {}
