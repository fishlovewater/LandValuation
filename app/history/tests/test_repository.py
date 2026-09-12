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


@pytest.mark.asyncio
async def test_history_review_data_exposes_run_and_input_version_metadata_without_snapshot_payload():
    session = DetailSession()

    result = await HistoryRepository(session).review_data(uuid4())

    assert result["validation_runs"] == []
    assert result["input_snapshots"] == []
    validation_sql = next(
        sql for sql in session.statements if "FROM valuation.validation_runs" in sql
    )
    platform_sql = next(
        sql for sql in session.statements if "FROM valuation.review_submissions" in sql
    )
    external_sql = next(
        sql for sql in session.statements if "FROM review.external_input_snapshots" in sql
    )
    assert "run_no" in validation_sql
    assert "submission_id" in validation_sql
    assert "external_input_snapshot_id" in validation_sql
    assert "input_fingerprint AS fingerprint" in platform_sql
    assert "jsonb_array_length(s.input_snapshot -> 'documents')" in platform_sql
    assert "document_row ->> 'original_filename'" in platform_sql
    assert "document_versions" in platform_sql
    assert "JOIN valuation.documents" not in platform_sql
    assert "jsonb_array_length(s.input_snapshot -> 'documents')" in external_sql
    assert "document_versions" in external_sql
    assert "s.input_snapshot," not in platform_sql
    assert "s.input_snapshot," not in external_sql
    assert "object_key" not in platform_sql
    assert "object_key" not in external_sql


@pytest.mark.asyncio
async def test_history_case_versions_are_ordered_newest_first_and_resolve_actor_name():
    session = Session()

    await HistoryRepository(session).list_case_versions(uuid4())

    normalized_sql = " ".join(session.statements[0].split())
    assert "FROM history.case_versions cv" in normalized_sql
    assert "LEFT JOIN auth.users u ON u.user_id = cv.created_by_user_id" in normalized_sql
    assert "u.display_name AS created_by" in normalized_sql
    assert "ORDER BY cv.version_no DESC" in normalized_sql


@pytest.mark.asyncio
async def test_history_changes_are_bounded_and_ordered_newest_first():
    session = Session()

    await HistoryRepository(session).list_changes(uuid4())

    normalized_sql = " ".join(session.statements[0].split())
    assert "FROM history.change_logs cl" in normalized_sql
    assert "LEFT JOIN auth.users u ON u.user_id = cl.changed_by_user_id" in normalized_sql
    assert "ORDER BY cl.changed_at DESC, cl.change_log_id DESC" in normalized_sql
    assert "LIMIT 200" in normalized_sql


@pytest.mark.asyncio
async def test_history_official_field_versions_only_use_latest_completed_applied_extraction():
    session = Session()

    await HistoryRepository(session).list_official_field_versions(uuid4())

    normalized_sql = " ".join(session.statements[0].split())
    assert "FROM valuation.documents d" in normalized_sql
    assert "FROM valuation.document_extractions" in normalized_sql
    assert "extraction_status = 'COMPLETED'" in normalized_sql
    assert "ORDER BY completed_at DESC NULLS LAST, created_at DESC, extraction_id DESC" in normalized_sql
    assert "LIMIT 1" in normalized_sql
    assert "JOIN valuation.extracted_fields ef" in normalized_sql
    assert "ef.field_status = 'APPLIED'" in normalized_sql
    assert "ef.confirmed_value AS normalized_value" in normalized_sql
    assert "ORDER BY d.document_group_id, ef.field_name, d.version_no" in normalized_sql
