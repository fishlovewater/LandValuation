from datetime import date
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.document_types import REVIEW_DOCUMENT_TYPES, VALUATION_DOCUMENT_TYPES
from app.history.permissions import HistoryScope
from app.history.schemas import HistorySearchParams


class HistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _access_sql(scope: HistoryScope) -> str:
        clauses = []
        if scope.valuation:
            clauses.append("(valuation_data OR valuation_documents)")
        if scope.review:
            clauses.append("(review_data OR review_documents)")
        return " OR ".join(clauses) or "false"

    @staticmethod
    def _result_sql(scope: HistoryScope) -> str:
        if not scope.review:
            return """
                CASE
                    WHEN case_status = 'CORRECTION' THEN 'CORRECTION'
                    ELSE 'IN_PROGRESS'
                END
            """
        return """
            CASE
                WHEN review_status IN ('COMPLETED', 'APPROVED', 'REVIEW_COMPLETED') THEN 'PASSED'
                WHEN review_status = 'SUPPLEMENT_REQUIRED' THEN 'SUPPLEMENT_REQUIRED'
                WHEN review_status = 'RETURNED_FOR_REVISION' THEN 'RETURNED'
                WHEN case_status = 'CORRECTION' THEN 'CORRECTION'
                ELSE 'IN_PROGRESS'
            END
        """

    @staticmethod
    def _sort_sql(params: HistorySearchParams) -> str:
        columns = {
            "updated_at": "updated_at",
            "received_at": "received_at",
            "risk_level": "risk_rank",
        }
        direction = "ASC" if params.order == "asc" else "DESC"
        return f"{columns[params.sort]} {direction} NULLS LAST, case_id {direction}"

    def _base_cte(self) -> str:
        return """
            WITH history_cases AS (
                SELECT
                    c.case_id, c.case_no, c.case_title, c.case_type,
                    c.valuation_base_date, c.city_code, c.district_code,
                    c.case_status, c.updated_at,
                    lr.review_status, lr.received_at,
                    lr.completed_at, lr.current_risk_level,
                    CASE lr.current_risk_level
                        WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                        WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                    END AS risk_rank,
                    EXISTS (
                        SELECT 1 FROM valuation.form_instances f
                        WHERE f.case_id = c.case_id
                    ) OR EXISTS (
                        SELECT 1 FROM valuation.valuations v
                        WHERE v.case_id = c.case_id
                    ) OR EXISTS (
                        SELECT 1 FROM valuation.comparison_analyses ca
                        WHERE ca.case_id = c.case_id
                    ) OR EXISTS (
                        SELECT 1 FROM valuation.benchmark_valuations bv
                        WHERE bv.case_id = c.case_id
                    ) OR EXISTS (
                        SELECT 1 FROM valuation.parcel_valuations pv
                        WHERE pv.case_id = c.case_id
                    ) AS valuation_data,
                    lr.review_id IS NOT NULL AS review_data,
                    EXISTS (
                        SELECT 1 FROM valuation.documents d
                        WHERE d.case_id = c.case_id
                          AND d.document_type IN :valuation_types
                    ) AS valuation_documents,
                    EXISTS (
                        SELECT 1 FROM valuation.documents d
                        WHERE d.case_id = c.case_id
                          AND d.document_type IN :review_types
                    ) AS review_documents
                FROM valuation.cases c
                LEFT JOIN LATERAL (
                    SELECT r.review_id, r.review_status, r.received_at, r.started_at,
                           r.completed_at, risk.overall_risk_level AS current_risk_level
                    FROM review.reviews r
                    LEFT JOIN LATERAL (
                        SELECT rs.overall_risk_level
                        FROM review.risk_summaries rs
                        WHERE rs.review_id = r.review_id
                        ORDER BY rs.generated_at DESC, rs.risk_summary_id DESC
                        LIMIT 1
                    ) risk ON true
                    WHERE r.case_id = c.case_id
                    ORDER BY r.received_at DESC, r.review_id DESC
                    LIMIT 1
                ) lr ON true
            )
        """

    def _filters(self, params: HistorySearchParams, scope: HistoryScope):
        filters = [f"({self._access_sql(scope)})"]
        values: dict[str, object] = {
            "valuation_types": tuple(VALUATION_DOCUMENT_TYPES),
            "review_types": tuple(REVIEW_DOCUMENT_TYPES),
        }
        if params.keyword:
            values["keyword"] = params.keyword.strip().lower()
            values["keyword_prefix"] = f"{params.keyword.strip().lower()}%"
            values["keyword_contains"] = f"%{params.keyword.strip().lower()}%"
            values["land_keyword"] = "".join(params.keyword.split()).lower()
            filters.append(
                """(
                    lower(case_no) = :keyword
                    OR lower(case_no) LIKE :keyword_prefix
                    OR lower(case_title) LIKE :keyword_contains
                    OR EXISTS (
                        SELECT 1 FROM valuation.parcels p
                        WHERE p.case_id = history_cases.case_id
                          AND lower(regexp_replace(p.land_no, '\\s+', '', 'g'))
                              LIKE '%' || :land_keyword || '%'
                    )
                )"""
            )
        for field in ("city_code", "district_code"):
            value = getattr(params, field)
            if value:
                filters.append(f"{field} = :{field}")
                values[field] = value
        if params.section_name:
            filters.append(
                """EXISTS (
                    SELECT 1 FROM valuation.parcels p
                    WHERE p.case_id = history_cases.case_id
                      AND p.section_name = :section_name
                )"""
            )
            values["section_name"] = params.section_name
        if params.result:
            filters.append(f"({self._result_sql(scope)}) = :history_result")
            values["history_result"] = params.result
        date_column = {
            "updated_at": "updated_at",
            "received_at": "received_at",
            "completed_at": "completed_at",
        }[params.date_field]
        if params.date_from:
            filters.append(f"{date_column} >= :date_from")
            values["date_from"] = params.date_from
        if params.date_to:
            filters.append(f"{date_column} < (:date_to + INTERVAL '1 day')")
            values["date_to"] = params.date_to
        return filters, values

    @staticmethod
    def _statement(sql: str):
        return text(sql).bindparams(
            bindparam("valuation_types", expanding=True),
            bindparam("review_types", expanding=True),
        )

    async def search(self, params: HistorySearchParams, scope: HistoryScope):
        filters, values = self._filters(params, scope)
        where = " AND ".join(filters)
        result_expr = self._result_sql(scope)
        sql = self._base_cte() + f"""
            SELECT *, ({result_expr}) AS history_result
            FROM history_cases
            WHERE {where}
            ORDER BY {self._sort_sql(params)}
            OFFSET :offset LIMIT :limit
        """
        values.update(offset=params.offset, limit=params.limit)
        rows = (
            await self.session.execute(self._statement(sql), values)
        ).mappings().all()
        count_sql = self._base_cte() + f"SELECT count(*) FROM history_cases WHERE {where}"
        total = await self.session.scalar(self._statement(count_sql), values)
        return [dict(row) for row in rows], int(total or 0)

    async def get_case(self, case_id: UUID):
        row = (
            await self.session.execute(
                text("SELECT * FROM valuation.cases WHERE case_id = :case_id"),
                {"case_id": case_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def case_access(self, case_id: UUID, scope: HistoryScope) -> dict:
        access = self._access_sql(scope)
        statement = self._statement(
            self._base_cte()
            + f"""SELECT valuation_data, review_data,
                         valuation_documents, review_documents,
                         ({access}) AS allowed
                  FROM history_cases WHERE case_id = :case_id"""
        )
        row = (
            await self.session.execute(
                statement,
                {
                    "case_id": case_id,
                    "valuation_types": tuple(VALUATION_DOCUMENT_TYPES),
                    "review_types": tuple(REVIEW_DOCUMENT_TYPES),
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row else {}

    async def list_parcels(self, case_id: UUID):
        rows = (
            await self.session.execute(
                text("""SELECT parcel_id, district_code, section_name,
                               subsection_name, land_no, area_sqm,
                               land_use_zone, designated_use
                        FROM valuation.parcels WHERE case_id = :case_id
                        ORDER BY section_name, subsection_name, land_no"""),
                {"case_id": case_id},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def list_documents(self, case_id: UUID, scope: HistoryScope):
        allowed = []
        if scope.valuation:
            allowed.extend(VALUATION_DOCUMENT_TYPES)
        if scope.review:
            allowed.extend(REVIEW_DOCUMENT_TYPES)
        rows = (
            await self.session.execute(
                text("""SELECT document_id, case_id, document_type,
                               original_filename, mime_type, bucket_name,
                               object_key, document_group_id, version_no,
                               is_active, uploaded_at, file_size_bytes,
                               checksum_sha256
                        FROM valuation.documents
                        WHERE case_id = :case_id AND document_type IN :types
                        ORDER BY document_type, version_no DESC,
                                 uploaded_at DESC, document_id DESC""").bindparams(
                    bindparam("types", expanding=True)
                ),
                {"case_id": case_id, "types": tuple(allowed)},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def get_document(self, document_id: UUID, scope: HistoryScope):
        allowed = []
        if scope.valuation:
            allowed.extend(VALUATION_DOCUMENT_TYPES)
        if scope.review:
            allowed.extend(REVIEW_DOCUMENT_TYPES)
        row = (
            await self.session.execute(
                text("""SELECT document_id, case_id, document_type,
                               original_filename, mime_type, bucket_name,
                               object_key, document_group_id, version_no,
                               is_active, uploaded_at, file_size_bytes,
                               checksum_sha256
                        FROM valuation.documents
                        WHERE document_id = :document_id
                          AND document_type IN :types""").bindparams(
                    bindparam("types", expanding=True)
                ),
                {"document_id": document_id, "types": tuple(allowed)},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def valuation_data(self, case_id: UUID) -> dict:
        forms = await self._json_rows(
            """SELECT form_instance_id, form_code, version_no, form_status,
                      prepared_date, source_document_id,
                      output_document_id, created_at, updated_at
               FROM valuation.form_instances WHERE case_id = :case_id
               ORDER BY form_code, version_no DESC""",
            case_id,
        )
        valuations = await self._json_rows(
            """SELECT valuation_id, parcel_id, form_instance_id, valuation_type,
                      unit_price, total_value, currency_code,
                      calculation_snapshot, result_status, calculated_at
               FROM valuation.valuations WHERE case_id = :case_id
               ORDER BY calculated_at DESC""",
            case_id,
        )
        comparisons = await self._json_rows(
            """SELECT comparison_analysis_id, benchmark_land_id,
                      form_instance_id, valuation_base_date,
                      benchmark_comparison_price, benchmark_condition_notes,
                      notes, analysis_status, created_at, updated_at
               FROM valuation.comparison_analyses WHERE case_id = :case_id
               ORDER BY updated_at DESC""",
            case_id,
        )
        benchmark_valuations = await self._json_rows(
            """SELECT benchmark_valuation_id, benchmark_land_id,
                      comparison_analysis_id, form_instance_id,
                      valuation_base_date, comparison_price, comparison_weight,
                      income_price, income_weight, benchmark_land_price,
                      market_period_start, market_period_end, market_condition,
                      selection_scope_reason, decision_reason, version_no,
                      valuation_status, created_at, updated_at
               FROM valuation.benchmark_valuations WHERE case_id = :case_id
               ORDER BY benchmark_land_id, version_no DESC""",
            case_id,
        )
        parcel_valuations = await self._json_rows(
            """SELECT parcel_valuation_id, benchmark_valuation_id,
                      form_instance_id, valuation_base_date, price_zone_no,
                      version_no, valuation_status, created_at, updated_at
               FROM valuation.parcel_valuations WHERE case_id = :case_id
               ORDER BY benchmark_valuation_id, version_no DESC""",
            case_id,
        )
        validation_runs = await self._json_rows(
            """SELECT validation_run_id, form_instance_id, run_status,
                      passed_count, warning_count, failed_count,
                      started_at, completed_at
               FROM valuation.validation_runs
               WHERE case_id = :case_id
               ORDER BY started_at DESC""",
            case_id,
        )
        validation_ids = tuple(row["validation_run_id"] for row in validation_runs)
        validation_findings = await self._rows_for_ids(
            "valuation.validation_findings", "validation_run_id", validation_ids
        )
        return {
            "forms": forms,
            "valuations": valuations,
            "comparison_analyses": comparisons,
            "benchmark_valuations": benchmark_valuations,
            "parcel_valuations": parcel_valuations,
            "validation_runs": validation_runs,
            "validation_findings": validation_findings,
        }

    async def review_data(self, case_id: UUID) -> dict:
        reviews = await self._json_rows(
            """SELECT review_id, review_type, review_status,
                      received_at, started_at, completed_at,
                      form_instance_id, validation_run_id
               FROM review.reviews WHERE case_id = :case_id
               ORDER BY completed_at DESC NULLS LAST, received_at DESC, review_id DESC""",
            case_id,
        )
        if not reviews:
            return {"reviews": [], "findings": [], "risk_summaries": [], "decisions": []}
        review_ids = tuple(row["review_id"] for row in reviews)
        findings = await self._review_rows("review.findings", review_ids)
        risks = await self._review_rows("review.risk_summaries", review_ids)
        decisions = await self._review_rows("review.decisions", review_ids)
        return {
            "reviews": reviews,
            "findings": findings,
            "risk_summaries": risks,
            "decisions": decisions,
        }

    async def _json_rows(self, sql: str, case_id: UUID):
        rows = (
            await self.session.execute(text(sql), {"case_id": case_id})
        ).mappings().all()
        return [dict(row) for row in rows]

    async def _review_rows(self, table: str, review_ids: tuple[UUID, ...]):
        # table is selected only from hard-coded callers above.
        rows = (
            await self.session.execute(
                text(f"SELECT * FROM {table} WHERE review_id IN :review_ids").bindparams(
                    bindparam("review_ids", expanding=True)
                ),
                {"review_ids": review_ids},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def _rows_for_ids(
        self, table: str, column: str, ids: tuple[UUID, ...]
    ) -> list[dict]:
        if not ids:
            return []
        # table and column are selected only from hard-coded callers above.
        rows = (
            await self.session.execute(
                text(f"SELECT * FROM {table} WHERE {column} IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": ids},
            )
        ).mappings().all()
        return [dict(row) for row in rows]
