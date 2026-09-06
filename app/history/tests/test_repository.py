from uuid import uuid4

import pytest

from app.history.repository import HistoryRepository


class Result:
    def mappings(self):
        return self

    def all(self):
        return []


class Session:
    def __init__(self):
        self.statements = []

    async def execute(self, statement, _params):
        self.statements.append(str(statement))
        return Result()


class DetailSession(Session):
    async def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        if "FROM review.reviews" in sql:
            return ResultWithRows(
                [
                    {
                        "review_id": uuid4(),
                        "review_type": "AI_ASSISTED",
                        "review_status": "REVIEW_REQUIRED",
                        "received_at": None,
                        "started_at": None,
                        "completed_at": None,
                        "form_instance_id": None,
                        "validation_run_id": None,
                    }
                ]
            )
        return Result()


class ResultWithRows(Result):
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def one_or_none(self):
        return self.rows[0] if self.rows else None


def test_history_search_reads_and_orders_reviews_by_received_at():
    sql = HistoryRepository(None)._base_cte()

    assert "lr.received_at" in sql
    assert "lr.started_at AS received_at" not in sql
    assert "ORDER BY r.received_at DESC" in sql


def test_history_current_risk_summary_is_scoped_to_latest_run_or_null_legacy():
    normalized_sql = " ".join(HistoryRepository(None)._base_cte().split())

    assert "rs.review_id = r.review_id" in normalized_sql
    assert "rs.validation_run_id = r.latest_validation_run_id" in normalized_sql
    assert (
        "r.latest_validation_run_id IS NULL AND rs.validation_run_id IS NULL"
        in normalized_sql
    )


@pytest.mark.asyncio
async def test_history_detail_reads_and_orders_reviews_by_received_at():
    session = Session()

    await HistoryRepository(session).review_data(uuid4())

    sql = session.statements[0]
    assert "received_at" in sql
    assert "started_at AS received_at" not in sql
    assert (
        "ORDER BY completed_at DESC NULLS LAST, received_at DESC, review_id DESC"
        in sql
    )


@pytest.mark.asyncio
async def test_history_detail_risk_summaries_are_scoped_to_latest_run_and_ordered():
    session = DetailSession()

    await HistoryRepository(session).review_data(uuid4())

    risk_sql = next(
        sql for sql in session.statements if "review.risk_summaries" in sql
    )
    normalized_sql = " ".join(risk_sql.split())
    assert "JOIN review.reviews r ON r.review_id = rs.review_id" in normalized_sql
    assert "rs.validation_run_id = r.latest_validation_run_id" in normalized_sql
    assert (
        "r.latest_validation_run_id IS NULL AND rs.validation_run_id IS NULL"
        in normalized_sql
    )
    assert "ORDER BY rs.generated_at DESC, rs.risk_summary_id DESC" in normalized_sql
