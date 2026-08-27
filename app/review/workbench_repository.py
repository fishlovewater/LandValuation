from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class WorkbenchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self) -> dict:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT
                        count(*) FILTER (WHERE review_status IN
                            ('RECEIVED', 'PREPROCESSING', 'READY_FOR_REVIEW')) AS pending,
                        count(*) FILTER (WHERE review_status IN
                            ('ANALYZING', 'REVIEW_REQUIRED', 'EXPERT_REVIEW')) AS in_progress,
                        count(*) FILTER (WHERE review_status IN
                            ('PENDING_MATERIALS', 'RETURNED_FOR_REVISION',
                             'SUPPLEMENT_REQUIRED')) AS needs_input,
                        count(*) FILTER (WHERE review_status IN
                            ('APPROVED', 'REVIEW_COMPLETED')) AS completed,
                        count(*) FILTER (WHERE current_risk_level IN
                            ('HIGH', 'CRITICAL')) AS high_risk_count,
                        coalesce(sum(missing_item_count), 0) AS missing_item_count
                    FROM review.reviews
                    """
                )
            )
        ).mappings().one()
        open_finding_count = await self.session.scalar(
            text(
                """
                SELECT count(*)
                FROM review.findings f
                JOIN review.reviews r
                  ON r.review_id = f.review_id
                 AND r.latest_validation_run_id = f.validation_run_id
                WHERE f.status IN ('OPEN', 'PARTIALLY_ACCEPTED',
                                   'REQUIRES_SUPPLEMENT', 'EXPERT_REVIEW')
                """
            )
        )
        return {
            "status_counts": {
                "pending": int(row["pending"] or 0),
                "in_progress": int(row["in_progress"] or 0),
                "needs_input": int(row["needs_input"] or 0),
                "completed": int(row["completed"] or 0),
            },
            "high_risk_count": int(row["high_risk_count"] or 0),
            "open_finding_count": int(open_finding_count or 0),
            "missing_item_count": int(row["missing_item_count"] or 0),
        }

    @staticmethod
    def _case_filters(
        q: str | None,
        status_filter: str | None,
        risk_level: str | None,
        status_group: str | None,
    ):
        clauses = []
        parameters: dict[str, object] = {}
        if q:
            clauses.append("(c.case_no ILIKE :q OR c.case_title ILIKE :q)")
            parameters["q"] = f"%{q}%"
        if status_filter:
            clauses.append("r.review_status = :status")
            parameters["status"] = status_filter
        if risk_level:
            clauses.append("r.current_risk_level = :risk_level")
            parameters["risk_level"] = risk_level
        status_groups = {
            "pending": ("RECEIVED", "PREPROCESSING", "READY_FOR_REVIEW"),
            "in_progress": ("ANALYZING", "REVIEW_REQUIRED", "EXPERT_REVIEW"),
            "needs_input": (
                "PENDING_MATERIALS",
                "RETURNED_FOR_REVISION",
                "SUPPLEMENT_REQUIRED",
            ),
            "completed": ("APPROVED", "REVIEW_COMPLETED"),
        }
        if status_group == "risk":
            clauses.append("r.current_risk_level IN ('HIGH', 'CRITICAL')")
        elif status_group in status_groups:
            clauses.append("r.review_status = ANY(:group_statuses)")
            parameters["group_statuses"] = list(status_groups[status_group])
        return (" AND " + " AND ".join(clauses)) if clauses else "", parameters

    async def list_cases(
        self,
        q: str | None,
        status_filter: str | None,
        risk_level: str | None,
        status_group: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        filters, parameters = self._case_filters(
            q, status_filter, risk_level, status_group
        )
        total = await self.session.scalar(
            text(
                """
                SELECT count(*)
                FROM review.reviews r
                JOIN valuation.cases c ON c.case_id = r.case_id
                WHERE true
                """
                + filters
            ),
            parameters,
        )
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT r.review_id, r.case_id, c.case_no, c.case_title,
                           c.district_code, r.review_status,
                           r.current_risk_level, r.missing_item_count,
                           r.received_at, r.due_at,
                           u.display_name AS assigned_reviewer_display_name,
                           vr.validation_run_id, vr.run_no, vr.run_status
                    FROM review.reviews r
                    JOIN valuation.cases c ON c.case_id = r.case_id
                    LEFT JOIN auth.users u ON u.user_id = r.assigned_reviewer_id
                    LEFT JOIN valuation.validation_runs vr
                      ON vr.validation_run_id = r.latest_validation_run_id
                    WHERE true
                    """
                    + filters
                    + """
                    ORDER BY r.manual_priority DESC,
                             r.due_at ASC NULLS LAST,
                             r.received_at ASC,
                             r.review_id ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {**parameters, "limit": limit, "offset": offset},
            )
        ).mappings()
        return [dict(row) for row in rows], int(total or 0)

    async def list_eligible_cases(self, q: str | None, limit: int) -> list[dict]:
        parameters: dict[str, object] = {"limit": limit}
        search = ""
        if q:
            search = "AND (c.case_no ILIKE :q OR c.case_title ILIKE :q)"
            parameters["q"] = f"%{q}%"
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT c.case_id, c.case_no, c.case_title, c.district_code,
                           c.valuation_base_date, c.case_status
                    FROM valuation.cases c
                    WHERE NOT EXISTS (
                        SELECT 1 FROM review.reviews r WHERE r.case_id = c.case_id
                    )
                    """
                    + search
                    + """
                    ORDER BY c.case_no, c.case_id
                    LIMIT :limit
                    """
                ),
                parameters,
            )
        ).mappings()
        return [dict(row) for row in rows]

    async def get_case_summary(self, review_id: UUID) -> dict | None:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT c.case_id, c.case_no, c.case_title, c.district_code,
                           c.valuation_base_date, c.case_status
                    FROM review.reviews r
                    JOIN valuation.cases c ON c.case_id = r.case_id
                    WHERE r.review_id = :review_id
                    """
                ),
                {"review_id": review_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def list_documents(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, document_type, original_filename,
                           mime_type, version_no, is_active, uploaded_at
                    FROM valuation.documents
                    WHERE case_id = :case_id
                    ORDER BY document_type, version_no, uploaded_at, document_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings()
        return [dict(row) for row in rows]

    async def list_official_field_versions(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT d.document_id, d.document_group_id,
                           d.version_no AS document_version,
                           ef.field_code, ef.field_path, ef.normalized_value,
                           ef.raw_text, ef.page_number
                    FROM valuation.documents d
                    JOIN LATERAL (
                        SELECT extraction_run_id
                        FROM valuation.extraction_runs
                        WHERE document_id = d.document_id
                          AND document_version = d.version_no
                          AND status = 'COMPLETED'
                        ORDER BY run_no DESC, completed_at DESC,
                                 extraction_run_id DESC
                        LIMIT 1
                    ) er ON true
                    JOIN valuation.extracted_fields ef
                      ON ef.extraction_run_id = er.extraction_run_id
                     AND ef.is_official = true
                    WHERE d.case_id = :case_id
                      AND d.document_type = 'original'
                    ORDER BY d.document_group_id, ef.field_code, ef.field_path,
                             d.version_no,
                             ef.extracted_field_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings()
        return [dict(row) for row in rows]
