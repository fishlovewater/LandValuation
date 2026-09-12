from datetime import date
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.document_types import REVIEW_DOCUMENT_TYPES, VALUATION_DOCUMENT_TYPES
from app.history.permissions import HistoryScope
from app.history.schemas import HistorySearchParams


_NEW_TAIPEI_CITY_CODES = ("31", "65000", "65000000", "NWT")
_NEW_TAIPEI_DISTRICT_PAIRS = {
    "3101": "65000010",  # 板橋區
    "3102": "65000020",  # 三重區
    "3103": "65000040",  # 永和區
    "3104": "65000030",  # 中和區
    "3105": "65000060",  # 新店區
    "3106": "65000050",  # 新莊區
    "3107": "65000070",
    "3108": "65000080",
    "3109": "65000090",
    "3110": "65000100",
    "3111": "65000110",
    "3112": "65000120",
    "3113": "65000130",
    "3114": "65000140",
    "3115": "65000150",
    "3116": "65000160",
    "3117": "65000170",
    "3118": "65000180",
    "3119": "65000190",
    "3120": "65000200",
    "3121": "65000210",
    "3122": "65000220",
    "3123": "65000230",
    "3124": "65000240",
    "3125": "65000250",
    "3126": "65000260",
    "3127": "65000270",
    "3128": "65000280",
    "3129": "65000290",
}
_NEW_TAIPEI_DISTRICT_ALIASES = {
    **_NEW_TAIPEI_DISTRICT_PAIRS,
    **{official: legacy for legacy, official in _NEW_TAIPEI_DISTRICT_PAIRS.items()},
}


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
                          AND (
                              rs.validation_run_id = r.latest_validation_run_id
                              OR (
                                  r.latest_validation_run_id IS NULL
                                  AND rs.validation_run_id IS NULL
                              )
                          )
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
        if params.city_code:
            if params.city_code in _NEW_TAIPEI_CITY_CODES:
                filters.append(
                    "(city_code = :city_code OR city_code = :city_code_alias_1 "
                    "OR city_code = :city_code_alias_2 OR city_code = :city_code_alias_3)"
                )
                values["city_code"] = _NEW_TAIPEI_CITY_CODES[0]
                values["city_code_alias_1"] = _NEW_TAIPEI_CITY_CODES[1]
                values["city_code_alias_2"] = _NEW_TAIPEI_CITY_CODES[2]
                values["city_code_alias_3"] = _NEW_TAIPEI_CITY_CODES[3]
            else:
                filters.append("city_code = :city_code")
                values["city_code"] = params.city_code
        if params.district_code:
            district_alias = _NEW_TAIPEI_DISTRICT_ALIASES.get(params.district_code)
            if district_alias:
                filters.append("(district_code = :district_code OR district_code = :district_code_alias)")
                values["district_code"] = params.district_code
                values["district_code_alias"] = district_alias
            else:
                filters.append("district_code = :district_code")
                values["district_code"] = params.district_code
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
            return {
                "reviews": [],
                "validation_runs": [],
                "input_snapshots": [],
                "findings": [],
                "risk_summaries": [],
                "decisions": [],
            }
        review_ids = tuple(row["review_id"] for row in reviews)
        validation_runs = (
            await self.session.execute(
                text(
                    """SELECT validation_run_id, review_id, run_no, run_status,
                              passed_count, warning_count, failed_count,
                              started_at, completed_at, submission_id,
                              external_input_snapshot_id
                       FROM valuation.validation_runs
                       WHERE review_id IN :review_ids
                       ORDER BY run_no DESC, started_at DESC,
                                validation_run_id DESC"""
                ).bindparams(bindparam("review_ids", expanding=True)),
                {"review_ids": review_ids},
            )
        ).mappings().all()
        platform_snapshots = (
            await self.session.execute(
                text(
                    """SELECT 'PLATFORM' AS source, s.review_id,
                              s.submission_id, NULL::uuid AS external_input_snapshot_id,
                              s.submission_no AS input_version,
                              s.submitted_at AS frozen_at,
                              s.input_fingerprint AS fingerprint,
                              CASE
                                  WHEN jsonb_typeof(s.input_snapshot -> 'documents') = 'array'
                                  THEN jsonb_array_length(s.input_snapshot -> 'documents')
                                  ELSE 0
                              END AS document_count,
                              primary_document.document_row ->> 'original_filename'
                                  AS primary_document_name,
                              CASE
                                  WHEN primary_document.document_row ->> 'version_no' ~ '^[0-9]+$'
                                  THEN (primary_document.document_row ->> 'version_no')::integer
                                  ELSE NULL
                              END AS primary_document_version,
                              primary_document.document_row ->> 'checksum_sha256'
                                  AS primary_document_checksum,
                              CASE
                                  WHEN jsonb_typeof(s.input_snapshot -> 'documents') = 'array'
                                  THEN (
                                      SELECT array_to_string(
                                          ARRAY(
                                              SELECT concat(
                                                  coalesce(document_row ->> 'original_filename', '未命名文件'),
                                                  ' · v',
                                                  coalesce(document_row ->> 'version_no', '?')
                                              )
                                              FROM jsonb_array_elements(s.input_snapshot -> 'documents') AS document_row
                                              ORDER BY document_row ->> 'document_type',
                                                       document_row ->> 'original_filename'
                                          ),
                                          '； '
                                      )
                                  )
                                  ELSE NULL
                              END AS document_versions
                       FROM valuation.review_submissions s
                       LEFT JOIN LATERAL (
                           SELECT document_row
                           FROM jsonb_array_elements(
                               CASE
                                   WHEN jsonb_typeof(s.input_snapshot -> 'documents') = 'array'
                                   THEN s.input_snapshot -> 'documents'
                                   ELSE '[]'::jsonb
                               END
                           ) AS document_row
                           WHERE document_row ->> 'document_id' = s.source_report_document_id::text
                           LIMIT 1
                       ) AS primary_document ON true
                       WHERE s.review_id IN :review_ids
                       ORDER BY s.submission_no DESC, s.submitted_at DESC"""
                ).bindparams(bindparam("review_ids", expanding=True)),
                {"review_ids": review_ids},
            )
        ).mappings().all()
        external_snapshots = (
            await self.session.execute(
                text(
                    """SELECT 'EXTERNAL' AS source, s.review_id,
                              NULL::uuid AS submission_id,
                              s.external_input_snapshot_id,
                              s.snapshot_no AS input_version,
                              s.created_at AS frozen_at,
                              s.input_fingerprint AS fingerprint,
                              CASE
                                  WHEN jsonb_typeof(s.input_snapshot -> 'documents') = 'array'
                                  THEN jsonb_array_length(s.input_snapshot -> 'documents')
                                  ELSE 0
                              END AS document_count,
                              NULL::text AS primary_document_name,
                              NULL::integer AS primary_document_version,
                              NULL::text AS primary_document_checksum,
                              CASE
                                  WHEN jsonb_typeof(s.input_snapshot -> 'documents') = 'array'
                                  THEN (
                                      SELECT array_to_string(
                                          ARRAY(
                                              SELECT concat(
                                                  coalesce(document_row ->> 'original_filename', '未命名文件'),
                                                  ' · v',
                                                  coalesce(document_row ->> 'version_no', '?')
                                              )
                                              FROM jsonb_array_elements(s.input_snapshot -> 'documents') AS document_row
                                              ORDER BY document_row ->> 'document_type',
                                                       document_row ->> 'original_filename'
                                          ),
                                          '； '
                                      )
                                  )
                                  ELSE NULL
                              END AS document_versions
                       FROM review.external_input_snapshots s
                       WHERE s.review_id IN :review_ids
                       ORDER BY s.snapshot_no DESC, s.created_at DESC"""
                ).bindparams(bindparam("review_ids", expanding=True)),
                {"review_ids": review_ids},
            )
        ).mappings().all()
        findings = await self._review_rows("review.findings", review_ids)
        risks = await self._risk_summary_rows(review_ids)
        decisions = await self._review_rows("review.decisions", review_ids)
        return {
            "reviews": reviews,
            "validation_runs": [dict(row) for row in validation_runs],
            "input_snapshots": [
                dict(row) for row in (*platform_snapshots, *external_snapshots)
            ],
            "findings": findings,
            "risk_summaries": risks,
            "decisions": decisions,
        }

    async def list_case_versions(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """SELECT cv.version_no, cv.change_summary, cv.created_at,
                              u.display_name AS created_by
                       FROM history.case_versions cv
                       LEFT JOIN auth.users u ON u.user_id = cv.created_by_user_id
                       WHERE cv.case_id = :case_id
                       ORDER BY cv.version_no DESC"""
                ),
                {"case_id": case_id},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def list_changes(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """SELECT cl.entity_type, cl.field_name, cl.old_value, cl.new_value,
                              cl.change_reason, cl.changed_at,
                              u.display_name AS changed_by
                       FROM history.change_logs cl
                       LEFT JOIN auth.users u ON u.user_id = cl.changed_by_user_id
                       WHERE cl.case_id = :case_id
                       ORDER BY cl.changed_at DESC, cl.change_log_id DESC
                       LIMIT 200"""
                ),
                {"case_id": case_id},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def list_official_field_versions(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """SELECT d.document_group_id, d.version_no AS document_version,
                              ef.field_name AS field_code,
                              concat(ef.form_code, '.', ef.field_name) AS field_path,
                              ef.confirmed_value AS normalized_value,
                              coalesce(ef.source_text, '') AS raw_text,
                              ef.source_page AS page_number
                       FROM valuation.documents d
                       JOIN LATERAL (
                           SELECT extraction_id
                           FROM valuation.document_extractions
                           WHERE case_id = d.case_id
                             AND document_id = d.document_id
                             AND extraction_status = 'COMPLETED'
                           ORDER BY completed_at DESC NULLS LAST, created_at DESC, extraction_id DESC
                           LIMIT 1
                       ) de ON true
                       JOIN valuation.extracted_fields ef
                         ON ef.extraction_id = de.extraction_id
                        AND ef.field_status = 'APPLIED'
                       WHERE d.case_id = :case_id
                       ORDER BY d.document_group_id, ef.field_name, d.version_no"""
                ),
                {"case_id": case_id},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

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

    async def _risk_summary_rows(self, review_ids: tuple[UUID, ...]):
        rows = (
            await self.session.execute(
                text(
                    """SELECT rs.*
                       FROM review.risk_summaries rs
                       JOIN review.reviews r ON r.review_id = rs.review_id
                       WHERE rs.review_id IN :review_ids
                         AND (
                             rs.validation_run_id = r.latest_validation_run_id
                             OR (
                                 r.latest_validation_run_id IS NULL
                                 AND rs.validation_run_id IS NULL
                             )
                         )
                       ORDER BY rs.generated_at DESC, rs.risk_summary_id DESC"""
                ).bindparams(bindparam("review_ids", expanding=True)),
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
