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

    async def active_documents(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, document_type,
                           original_filename AS file_name,
                           mime_type AS content_type, version_no,
                           uploaded_at, file_size_bytes
                    FROM valuation.documents
                    WHERE case_id = :case_id
                      AND is_active = true
                    ORDER BY uploaded_at DESC, version_no DESC, document_id DESC
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def latest_review(self, case_id: UUID) -> dict | None:
        review = (
            await self.session.execute(
                text(
                    """
                    SELECT r.review_id, r.review_type, r.review_status,
                           r.started_at, r.completed_at,
                           r.latest_validation_run_id,
                           risk.overall_risk_level, risk.risk_score, risk.summary,
                           COALESCE(risk.category_scores, '{}'::jsonb) AS category_scores
                    FROM review.reviews r
                    LEFT JOIN LATERAL (
                        SELECT rs.overall_risk_level, rs.risk_score, rs.summary,
                               rs.category_scores
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
                       AND f.validation_run_id IS NOT DISTINCT FROM :validation_run_id
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
