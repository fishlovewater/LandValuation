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
