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
