from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import CaseRecord


EXTERNAL_REVIEW_CASE_TYPE = "EXTERNAL_REVIEW"


class WorkbenchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def case_no_exists(self, case_no: str) -> bool:
        result = await self.session.scalar(
            text("SELECT EXISTS(SELECT 1 FROM valuation.cases WHERE case_no = :case_no)"),
            {"case_no": case_no},
        )
        return bool(result)

    async def create_external_case(self, record: CaseRecord) -> CaseRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

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
                WHERE f.status IN ('OPEN', 'REQUIRES_SUPPLEMENT', 'EXPERT_REVIEW')
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
        *,
        case_source: str | None = None,
        district: str | None = None,
        urgency_level: str | None = None,
        urgency_now: datetime | None = None,
        urgent_days: int = 3,
        due_soon_days: int = 7,
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
        if case_source == "PLATFORM":
            clauses.append("c.case_type <> :external_review_case_type")
            parameters["external_review_case_type"] = EXTERNAL_REVIEW_CASE_TYPE
        elif case_source == "EXTERNAL":
            clauses.append("c.case_type = :external_review_case_type")
            parameters["external_review_case_type"] = EXTERNAL_REVIEW_CASE_TYPE
        if district:
            clauses.append("c.district_code = :district")
            parameters["district"] = district
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

        if urgency_level:
            if urgency_level == "NOT_SET":
                clauses.append("r.due_at IS NULL")
            elif urgency_now is not None:
                parameters.update(
                    {
                        "urgency_now": urgency_now,
                        "urgent_days": urgent_days,
                        "due_soon_days": due_soon_days,
                    }
                )
                remaining_days = (
                    "floor(extract(epoch from (r.due_at - :urgency_now)) / 86400)"
                )
                if urgency_level == "OVERDUE":
                    clauses.append("r.due_at IS NOT NULL AND r.due_at < :urgency_now")
                elif urgency_level == "URGENT":
                    clauses.append(
                        "r.due_at >= :urgency_now AND "
                        f"{remaining_days} <= :urgent_days"
                    )
                elif urgency_level == "DUE_SOON":
                    clauses.append(
                        "r.due_at >= :urgency_now AND "
                        f"{remaining_days} > :urgent_days AND "
                        f"{remaining_days} <= :due_soon_days"
                    )
                elif urgency_level == "NORMAL":
                    clauses.append(
                        "r.due_at >= :urgency_now AND "
                        f"{remaining_days} > :due_soon_days"
                    )
        return (" AND " + " AND ".join(clauses)) if clauses else "", parameters

    async def list_cases(
        self,
        q: str | None,
        status_filter: str | None,
        risk_level: str | None,
        status_group: str | None,
        limit: int,
        offset: int,
        *,
        case_source: str | None = None,
        district: str | None = None,
        urgency_level: str | None = None,
        urgency_now: datetime | None = None,
        urgent_days: int = 3,
        due_soon_days: int = 7,
        sort_by: str = "received_at",
        sort_direction: str = "desc",
    ) -> tuple[list[dict], int]:
        filters, parameters = self._case_filters(
            q,
            status_filter,
            risk_level,
            status_group,
            case_source=case_source,
            district=district,
            urgency_level=urgency_level,
            urgency_now=urgency_now,
            urgent_days=urgent_days,
            due_soon_days=due_soon_days,
        )
        order_columns = {
            "case_no": "c.case_no",
            "case_title": "c.case_title",
            "status": "r.review_status",
            "received_at": "r.received_at",
            "due_at": "r.due_at",
            "risk": "CASE r.current_risk_level WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0 END",
        }
        order_column = order_columns.get(sort_by, "r.received_at")
        direction = "ASC" if sort_direction == "asc" else "DESC"
        nulls = " NULLS LAST" if sort_by in {"due_at", "risk"} else ""
        order_by = f"{order_column} {direction}{nulls}, r.review_id ASC"
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
                           c.district_code,
                           CASE WHEN c.case_type = 'EXTERNAL_REVIEW'
                                THEN 'EXTERNAL' ELSE 'PLATFORM' END AS case_source,
                           r.review_status,
                           r.current_risk_level, r.missing_item_count,
                           r.high_count, r.medium_count, r.low_count,
                           r.manual_priority,
                           r.received_at, r.due_at,
                           u.display_name AS assigned_reviewer_display_name,
                           vr.validation_run_id, vr.run_no, vr.run_status,
                           coalesce((
                               SELECT max(cr.request_no)
                               FROM review.correction_requests cr
                               WHERE cr.review_id = r.review_id
                           ), 0) AS correction_round,
                           (
                               SELECT cr.status
                               FROM review.correction_requests cr
                               WHERE cr.review_id = r.review_id
                               ORDER BY cr.request_no DESC
                               LIMIT 1
                           ) AS latest_correction_status
                    FROM review.reviews r
                    JOIN valuation.cases c ON c.case_id = r.case_id
                    LEFT JOIN auth.users u ON u.user_id = r.assigned_reviewer_id
                    LEFT JOIN valuation.validation_runs vr
                      ON vr.validation_run_id = r.latest_validation_run_id
                    WHERE true
                    """
                    + filters
                    + f"""
                    ORDER BY r.manual_priority DESC, {order_by}
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
                    WHERE c.case_type <> 'EXTERNAL_REVIEW'
                      AND NOT EXISTS (
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
                    SELECT c.case_id, c.case_no, c.case_title, c.case_type, c.district_code,
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

    async def get_submission_provenance(self, review_id: UUID) -> dict | None:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT s.submission_id, s.submission_no,
                           s.submitted_at, s.input_fingerprint
                    FROM review.reviews r
                    JOIN valuation.review_submissions s
                      ON s.submission_id = r.latest_submission_id
                     AND s.review_id = r.review_id
                     AND s.case_id = r.case_id
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
                    SELECT document_id, document_group_id, document_type, original_filename,
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

    async def get_document_for_review(
        self, review_id: UUID, document_id: UUID
    ) -> dict | None:
        review = (
            await self.session.execute(
                text(
                    """
                    SELECT case_id, latest_submission_id
                    FROM review.reviews
                    WHERE review_id = :review_id
                    """
                ),
                {"review_id": review_id},
            )
        ).mappings().one_or_none()
        if review is None:
            return None

        if review["latest_submission_id"] is None:
            # Legacy standalone Reviews have no immutable handoff pointer and
            # intentionally retain the live case-document fallback.
            row = (
                await self.session.execute(
                    text(
                        """
                        SELECT d.document_id, d.original_filename, d.mime_type,
                               d.object_key
                        FROM valuation.documents d
                        WHERE d.case_id = :case_id
                          AND d.document_id = :document_id
                        """
                    ),
                    {"case_id": review["case_id"], "document_id": document_id},
                )
            ).mappings().one_or_none()
        else:
            # A submitted Review is bounded by the immutable list of document
            # IDs in its Snapshot.  The live row is used only to obtain the
            # current storage handle after that membership check succeeds.
            row = (
                await self.session.execute(
                    text(
                        """
                        SELECT d.document_id, d.original_filename, d.mime_type,
                               d.object_key
                        FROM valuation.review_submissions s
                        JOIN valuation.documents d
                          ON d.case_id = s.case_id
                         AND d.document_id = :document_id
                        CROSS JOIN LATERAL jsonb_array_elements(
                            CASE
                                WHEN jsonb_typeof(s.input_snapshot->'documents') = 'array'
                                THEN s.input_snapshot->'documents'
                                ELSE '[]'::jsonb
                            END
                        ) AS submitted_document(item)
                        WHERE s.submission_id = :submission_id
                          AND s.review_id = :review_id
                          AND s.case_id = :case_id
                          AND submitted_document.item->>'document_id'
                              = d.document_id::text
                        """
                    ),
                    {
                        "submission_id": review["latest_submission_id"],
                        "review_id": review_id,
                        "case_id": review["case_id"],
                        "document_id": document_id,
                    },
                )
            ).mappings().one_or_none()
        return dict(row) if row else None

    async def list_official_field_versions(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT d.document_id, d.document_group_id, d.version_no AS document_version,
                           ef.field_name AS field_code,
                           concat(ef.form_code, '.', ef.field_name) AS field_path,
                           ef.confirmed_value AS normalized_value,
                           coalesce(ef.source_text, '') AS raw_text,
                           ef.source_page AS page_number
                    FROM valuation.documents AS d
                    JOIN LATERAL (
                        SELECT extraction_id
                        FROM valuation.document_extractions
                        WHERE case_id = d.case_id
                          AND document_id = d.document_id
                          AND extraction_status = 'COMPLETED'
                        ORDER BY completed_at DESC NULLS LAST, created_at DESC, extraction_id DESC
                        LIMIT 1
                    ) AS de ON true
                    JOIN valuation.extracted_fields AS ef
                      ON ef.extraction_id = de.extraction_id
                     AND ef.field_status IN ('APPLIED', 'AUTO_APPLIED')
                    WHERE d.case_id = :case_id
                    ORDER BY d.document_group_id, ef.field_name, d.version_no;
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings()
        return [dict(row) for row in rows]
