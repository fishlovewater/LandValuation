from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError


class CaseContextRepository:
    """Read-only queries against the existing Valuation and Review schemas."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def case_brief(self, case_id: UUID) -> dict:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT case_id, case_no, case_title, case_type, case_status,
                           valuation_base_date, city_code, district_code,
                           land_use_type, updated_at
                    FROM valuation.cases
                    WHERE case_id = :case_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().first()
        if row is None:
            raise ResourceNotFoundError("案件")
        return dict(row)

    async def latest_review(self, case_id: UUID) -> dict | None:
        review = (
            await self.session.execute(
                text(
                    """
                    SELECT r.review_id, r.review_type, r.review_status,
                           r.started_at, r.completed_at,
                           r.latest_validation_run_id,
                           rs.overall_risk_level, rs.risk_score, rs.summary,
                           COALESCE(rs.category_scores, '{}'::jsonb) AS category_scores
                    FROM review.reviews r
                    LEFT JOIN review.risk_summaries rs
                        ON rs.review_id = r.review_id
                       AND rs.validation_run_id = r.latest_validation_run_id
                    WHERE r.case_id = :case_id
                    ORDER BY r.started_at DESC, r.review_id DESC
                    LIMIT 1
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().first()
        if review is None:
            return None

        result = dict(review)
        review_id = result["review_id"]
        findings = (
            await self.session.execute(
                text(
                    """
                     SELECT f.finding_id, f.finding_code, f.finding_type, f.severity,
                            f.title, f.description, f.status, f.created_at
                     FROM review.findings f
                     WHERE f.review_id = :review_id
                       AND f.validation_run_id = :validation_run_id
                    ORDER BY CASE severity
                        WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                        created_at DESC
                    """
                ),
                {
                    "review_id": review_id,
                    "validation_run_id": result["latest_validation_run_id"],
                },
            )
        ).mappings().all()
        missing_items = (
            await self.session.execute(
                text(
                    """
                    SELECT missing_item_id, item_code, item_name, document_type,
                           severity, status, details
                    FROM review.missing_items
                    WHERE review_id = :review_id
                    ORDER BY CASE severity
                        WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                        item_code
                    """
                ),
                {"review_id": review_id},
            )
        ).mappings().all()
        result["findings"] = [dict(item) for item in findings]
        result["missing_items"] = [dict(item) for item in missing_items]
        return result
