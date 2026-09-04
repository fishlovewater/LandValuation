from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.review.completeness import CaseInputSnapshot, DocumentSnapshot, MissingRequirement
from app.review.models import (
    Decision,
    Finding,
    MissingItem,
    Review,
    RiskSummary,
    ValidationFinding,
    ValidationRun,
)
from app.review.schemas import ReviewCreate, ReviewListQuery
from app.review.risks import EXPERT_MINIMUM_MEDIUM_TYPE, HIGH_RISK_FINDING_TYPES
from app.valuation.models import CaseRecord, ReviewSubmissionRecord


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: ReviewCreate, started_by_user_id: UUID) -> Review:
        values = payload.model_dump(exclude_none=True)
        review = Review(
            **values,
            review_status="RECEIVED",
            started_by_user_id=started_by_user_id,
        )
        self.session.add(review)
        await self.session.flush()
        await self.session.refresh(review)
        return review

    async def get(self, review_id: UUID, for_update: bool = False) -> Review | None:
        statement = select(Review).where(Review.review_id == review_id)
        if for_update:
            # A caller may have read the row without a lock to discover its
            # case_id.  Populate the identity-map instance again while taking
            # the lock so state checks use the current database row.
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return await self.session.scalar(statement)

    async def get_case(
        self, case_id: UUID, for_update: bool = False
    ) -> CaseRecord | None:
        statement = select(CaseRecord).where(CaseRecord.case_id == case_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_submission_snapshot(self, submission_id: UUID) -> dict | None:
        snapshot = await self.session.scalar(
            select(ReviewSubmissionRecord.input_snapshot).where(
                ReviewSubmissionRecord.submission_id == submission_id
            )
        )
        return dict(snapshot) if isinstance(snapshot, dict) else None

    async def get_submission_snapshot_record(
        self,
        submission_id: UUID,
        *,
        review_id: UUID | None = None,
        case_id: UUID | None = None,
    ) -> dict | None:
        """Load the immutable snapshot together with its stored fingerprint.

        The optional ownership filters let Review fail closed if a corrupted
        pointer ever targets a submission belonging to another Review/case.
        """
        statement = select(
            ReviewSubmissionRecord.input_snapshot,
            ReviewSubmissionRecord.input_fingerprint,
        ).where(ReviewSubmissionRecord.submission_id == submission_id)
        if review_id is not None:
            statement = statement.where(ReviewSubmissionRecord.review_id == review_id)
        if case_id is not None:
            statement = statement.where(ReviewSubmissionRecord.case_id == case_id)
        row = (await self.session.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        return {
            "input_snapshot": row["input_snapshot"],
            "input_fingerprint": row["input_fingerprint"],
        }

    async def get_submission_provenance_by_id(
        self,
        submission_id: UUID,
        *,
        review_id: UUID,
        case_id: UUID,
    ) -> dict | None:
        row = (
            await self.session.execute(
                select(
                    ReviewSubmissionRecord.submission_id,
                    ReviewSubmissionRecord.submission_no,
                    ReviewSubmissionRecord.submitted_at,
                    ReviewSubmissionRecord.input_fingerprint,
                ).where(
                    ReviewSubmissionRecord.submission_id == submission_id,
                    ReviewSubmissionRecord.review_id == review_id,
                    ReviewSubmissionRecord.case_id == case_id,
                )
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def get_submission_provenance_by_ids(
        self,
        submission_ids: set[UUID],
        *,
        review_id: UUID,
        case_id: UUID,
    ) -> dict[UUID, dict]:
        if not submission_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    ReviewSubmissionRecord.submission_id,
                    ReviewSubmissionRecord.submission_no,
                    ReviewSubmissionRecord.submitted_at,
                    ReviewSubmissionRecord.input_fingerprint,
                ).where(
                    ReviewSubmissionRecord.submission_id.in_(submission_ids),
                    ReviewSubmissionRecord.review_id == review_id,
                    ReviewSubmissionRecord.case_id == case_id,
                )
            )
        ).mappings()
        return {
            row["submission_id"]: dict(row)
            for row in rows
        }

    async def list(self, query: ReviewListQuery) -> tuple[list[Review], int]:
        filters = []
        if query.status is not None:
            filters.append(Review.review_status == query.status)
        if query.assigned_reviewer_id is not None:
            filters.append(Review.assigned_reviewer_id == query.assigned_reviewer_id)
        if query.risk_level is not None:
            filters.append(Review.current_risk_level == query.risk_level)

        total = await self.session.scalar(
            select(func.count()).select_from(Review).where(*filters)
        )
        now = datetime.now(UTC)
        risk_rank = case(
            (Review.current_risk_level == "CRITICAL", 4),
            (Review.current_risk_level == "HIGH", 3),
            (Review.current_risk_level == "MEDIUM", 2),
            (Review.current_risk_level == "LOW", 1),
            else_=0,
        )
        overdue_rank = case(
            (Review.due_at.is_not(None) & (Review.due_at < now), 1), else_=0
        )
        statement = (
            select(Review)
            .where(*filters)
            .order_by(
                Review.manual_priority.desc(),
                overdue_rank.desc(),
                risk_rank.desc(),
                Review.due_at.asc().nulls_last(),
                Review.received_at.asc(),
                Review.review_id.asc(),
            )
            .limit(query.limit)
            .offset(query.offset)
        )
        reviews = list((await self.session.scalars(statement)).all())
        return reviews, int(total or 0)

    async def assign(self, review_id: UUID, reviewer_id: UUID) -> Review:
        review = await self.get(review_id, for_update=True)
        if review is None:
            raise LookupError(review_id)
        review.assigned_reviewer_id = reviewer_id
        await self.session.flush()
        return review

    async def set_priority(
        self,
        review_id: UUID,
        priority: int,
        reason: str,
        actor_id: UUID,
    ) -> Review:
        del actor_id  # reserved for the append-only audit event in the decision slice
        review = await self.get(review_id, for_update=True)
        if review is None:
            raise LookupError(review_id)
        review.manual_priority = priority
        review.manual_priority_reason = reason
        await self.session.flush()
        return review

    async def load_case_snapshot(self, case_id: UUID) -> CaseInputSnapshot:
        case_row = (
            await self.session.execute(
                text(
                    """
                    SELECT c.case_no, c.valuation_base_date, c.district_code,
                           (SELECT sum(p.area_sqm) FROM valuation.parcels p
                            WHERE p.case_id = c.case_id) AS parcel_area
                    FROM valuation.cases c
                    WHERE c.case_id = :case_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().one()
        document_rows = (
            await self.session.execute(
                text(
                    """
                    SELECT document_type, version_no, is_active
                    FROM valuation.documents
                    WHERE case_id = :case_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings()
        return CaseInputSnapshot(
            documents=tuple(
                DocumentSnapshot(
                    category=row["document_type"],
                    version=row["version_no"],
                    is_active=row["is_active"],
                )
                for row in document_rows
            ),
            normalized_fields=dict(case_row),
        )

    async def get_latest_original_document(self, case_id: UUID):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, case_id, document_type, version_no,
                           document_group_id, object_key, checksum_sha256
                    FROM valuation.documents
                    WHERE case_id = :case_id
                      AND document_type = 'original'
                      AND is_active = true
                    ORDER BY version_no DESC, uploaded_at DESC, document_id DESC
                    LIMIT 1
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def list_applied_confirmed_extracted_fields(self, case_id: UUID):
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT ef.extracted_field_id, ef.document_id,
                           ef.form_code, ef.field_name,
                           ef.confirmed_value, ef.source_page, ef.source_text,
                           ef.confidence, ef.field_status,
                           ef.confirmed_by_user_id, ef.confirmed_at
                    FROM valuation.extracted_fields AS ef
                    JOIN valuation.documents AS d
                      ON d.case_id = ef.case_id
                     AND d.document_id = ef.document_id
                    WHERE ef.case_id = :case_id
                      AND d.document_type = 'original'
                      AND d.is_active = true
                      AND d.document_id = (
                          SELECT current_document.document_id
                          FROM valuation.documents AS current_document
                          WHERE current_document.case_id = :case_id
                            AND current_document.document_type = 'original'
                            AND current_document.is_active = true
                          ORDER BY current_document.version_no DESC,
                                   current_document.uploaded_at DESC,
                                   current_document.document_id DESC
                          LIMIT 1
                      )
                      AND ef.extraction_id = (
                          SELECT de.extraction_id
                          FROM valuation.document_extractions AS de
                          WHERE de.case_id = ef.case_id
                            AND de.document_id = ef.document_id
                            AND de.extraction_status = 'COMPLETED'
                          ORDER BY de.completed_at DESC NULLS LAST,
                                   de.created_at DESC,
                                   de.extraction_id DESC
                          LIMIT 1
                      )
                      AND ef.field_status = 'APPLIED'
                      AND ef.confirmed_value IS NOT NULL
                    ORDER BY ef.form_code, ef.field_name, ef.extracted_field_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings()
        return [dict(row) for row in rows]

    async def get_case_rule_context(self, case_id: UUID):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT c.case_id, c.case_no, c.case_title,
                           c.case_type, c.district_code, c.valuation_base_date,
                           coalesce(
                               array_agg(DISTINCT fi.form_code)
                                   FILTER (
                                       WHERE fi.form_code IS NOT NULL
                                         AND fi.form_status <> 'VOID'
                                   ),
                               ARRAY[]::varchar[]
                           ) AS form_codes
                    FROM valuation.cases c
                    LEFT JOIN valuation.form_instances fi ON fi.case_id = c.case_id
                    WHERE c.case_id = :case_id
                    GROUP BY c.case_id, c.case_no, c.case_title
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        context = dict(row)
        context["form_codes"] = frozenset(context["form_codes"] or ())
        return context

    async def list_rule_candidates(self):
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT rule_version_id, rule_set_code, version_no, version_name,
                           status, effective_from, effective_to,
                           applicable_case_type, applicable_district_code,
                           selection_priority, source_document_id
                    FROM valuation.rule_versions
                    ORDER BY selection_priority DESC, rule_version_id
                    """
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    async def list_active_rules(
        self, rule_version_id: UUID, form_codes: frozenset[str]
    ):
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT validation_rule_id, rule_version_id, rule_code,
                           rule_name, target_form_code, target_table,
                           target_field_code, severity, rule_expression,
                           message_template, is_active
                    FROM valuation.validation_rules
                    WHERE rule_version_id = :rule_version_id
                      AND is_active = true
                      AND (
                          target_form_code IS NULL
                          OR target_form_code = ANY(
                              CAST(:form_codes AS varchar[])
                          )
                      )
                    ORDER BY rule_code, validation_rule_id
                    """
                ),
                {
                    "rule_version_id": rule_version_id,
                    "form_codes": sorted(form_codes),
                },
            )
        ).mappings()
        return [dict(row) for row in rows]

    async def get_rule_source(self, document_id: UUID, valuation_base_date: date):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, checksum_sha256, version_no,
                           effective_from, effective_to
                    FROM knowledge.documents
                    WHERE document_id = :document_id
                      AND extraction_status = 'COMPLETED'
                      AND publication_status = 'PUBLISHED'
                      AND (effective_from IS NULL
                           OR effective_from <= :valuation_base_date)
                      AND (effective_to IS NULL
                           OR effective_to >= :valuation_base_date)
                    """
                ),
                {
                    "document_id": document_id,
                    "valuation_base_date": valuation_base_date,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def sync_missing_items(
        self,
        review_id: UUID,
        requirements: tuple[MissingRequirement, ...],
        actor_id: UUID,
    ) -> list[MissingItem]:
        open_items = list(
            (
                await self.session.scalars(
                    select(MissingItem).where(
                        MissingItem.review_id == review_id,
                        MissingItem.status == "OPEN",
                    )
                )
            ).all()
        )
        by_code = {item.item_code: item for item in open_items}
        current_codes = {item.item_code for item in requirements}
        resolved_at = datetime.now(UTC)
        for item in open_items:
            if item.item_code not in current_codes:
                item.status = "RESOLVED"
                item.resolved_by_user_id = actor_id
                item.resolved_at = resolved_at

        current: list[MissingItem] = []
        for requirement in requirements:
            item = by_code.get(requirement.item_code)
            if item is None:
                item = MissingItem(
                    review_id=review_id,
                    item_code=requirement.item_code,
                    item_name=requirement.item_name,
                    document_type=requirement.document_category,
                    field_path=requirement.field_path,
                    reason="必要文件或欄位尚未提供",
                    affected_rule_codes=sorted(requirement.blocked_rule_codes),
                    severity="HIGH" if requirement.blocked_rule_codes else "MEDIUM",
                    status="OPEN",
                )
                self.session.add(item)
            current.append(item)
        await self.session.flush()
        for item in current:
            await self.session.refresh(item)
        return current

    async def list_missing_items(
        self, review_id: UUID, open_only: bool = True
    ) -> list[MissingItem]:
        statement = select(MissingItem).where(MissingItem.review_id == review_id)
        if open_only:
            statement = statement.where(MissingItem.status == "OPEN")
        statement = statement.order_by(MissingItem.created_at, MissingItem.missing_item_id)
        return list((await self.session.scalars(statement)).all())

    async def request_supplement(
        self, review_id: UUID, due_at: datetime
    ) -> list[MissingItem]:
        items = await self.list_missing_items(review_id, open_only=True)
        for item in items:
            item.due_at = due_at
            item.notification_status = "PENDING"
        await self.session.flush()
        return items

    async def active_run_exists(self, review_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count()).select_from(ValidationRun).where(
                    ValidationRun.review_id == review_id,
                    ValidationRun.run_status == "RUNNING",
                )
            )
        )

    async def create_run(
        self,
        review: Review,
        actor_id: UUID,
        rule_version_id: UUID,
        input_snapshot: dict,
        submission_id: UUID | None = None,
    ) -> ValidationRun:
        run_no = (
            await self.session.scalar(
                select(func.coalesce(func.max(ValidationRun.run_no), 0)).where(
                    ValidationRun.review_id == review.review_id
                )
            )
        ) + 1
        run = ValidationRun(
            case_id=review.case_id,
            review_id=review.review_id,
            run_no=run_no,
            run_status="RUNNING",
            triggered_by_user_id=actor_id,
            rule_version_id=rule_version_id,
            ruleset_snapshot={
                "rule_version_id": str(rule_version_id),
                "validation_rule_ids": input_snapshot["validation_rule_ids"],
            },
            input_snapshot=input_snapshot,
            submission_id=submission_id,
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def get_effective_rule(
        self,
        case_id: UUID,
        rule_version_id: UUID,
        validation_rule_id: UUID,
    ):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT vr.validation_rule_id, vr.rule_code, vr.severity,
                           vr.rule_expression, rv.rule_version_id,
                           rv.source_reference
                    FROM valuation.cases c
                    JOIN valuation.rule_versions rv
                      ON rv.rule_version_id = :rule_version_id
                     AND rv.status = 'PUBLISHED'
                     AND rv.effective_from <= c.valuation_base_date
                     AND (rv.effective_to IS NULL
                          OR rv.effective_to >= c.valuation_base_date)
                    JOIN valuation.validation_rules vr
                      ON vr.rule_version_id = rv.rule_version_id
                     AND vr.validation_rule_id = :validation_rule_id
                     AND vr.is_active = true
                    WHERE c.case_id = :case_id
                    """
                ),
                {
                    "case_id": case_id,
                    "rule_version_id": rule_version_id,
                    "validation_rule_id": validation_rule_id,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def get_case_document(
        self, case_id: UUID, document_id: UUID, version_no: int
    ):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, case_id, document_type, version_no,
                           object_key, checksum_sha256
                    FROM valuation.documents
                    WHERE case_id = :case_id
                      AND document_id = :document_id
                      AND version_no = :version_no
                      AND is_active = true
                    """
                ),
                {
                    "case_id": case_id,
                    "document_id": document_id,
                    "version_no": version_no,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def create_validation_finding(self, **values) -> ValidationFinding:
        finding = ValidationFinding(**values)
        self.session.add(finding)
        await self.session.flush()
        await self.session.refresh(finding)
        return finding

    async def create_finding(self, **values) -> Finding:
        finding = Finding(**values)
        self.session.add(finding)
        await self.session.flush()
        await self.session.refresh(finding)
        return finding

    async def create_risk_summary(self, **values) -> RiskSummary:
        summary = RiskSummary(**values)
        self.session.add(summary)
        await self.session.flush()
        await self.session.refresh(summary)
        return summary

    async def list_runs(self, review_id: UUID) -> list[ValidationRun]:
        statement = (
            select(ValidationRun)
            .where(ValidationRun.review_id == review_id)
            .order_by(ValidationRun.run_no, ValidationRun.validation_run_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_run(self, validation_run_id: UUID) -> ValidationRun | None:
        return await self.session.scalar(
            select(ValidationRun).where(
                ValidationRun.validation_run_id == validation_run_id
            )
        )

    async def list_findings(self, validation_run_id: UUID) -> list[Finding]:
        statement = (
            select(Finding)
            .where(Finding.validation_run_id == validation_run_id)
            .order_by(Finding.created_at, Finding.finding_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_finding_rule_links(
        self, review_id: UUID, validation_run_id: UUID
    ):
        rows = await self.session.execute(
            select(Finding.finding_id, ValidationFinding.validation_rule_id)
            .join(
                ValidationFinding,
                Finding.source_validation_finding_id
                == ValidationFinding.finding_id,
            )
            .join(
                ValidationRun,
                Finding.validation_run_id == ValidationRun.validation_run_id,
            )
            .where(
                Finding.review_id == review_id,
                Finding.validation_run_id == validation_run_id,
                ValidationRun.review_id == review_id,
            )
            .order_by(Finding.created_at.desc(), Finding.finding_id.desc())
        )
        return list(rows)

    async def get_finding(self, finding_id: UUID) -> Finding | None:
        return await self.session.scalar(
            select(Finding).where(Finding.finding_id == finding_id)
        )

    async def get_risk_summary(self, validation_run_id: UUID) -> RiskSummary | None:
        return await self.session.scalar(
            select(RiskSummary).where(
                RiskSummary.validation_run_id == validation_run_id
            )
        )

    async def get_finding_for_review(
        self, finding_id: UUID, review_id: UUID, for_update: bool = False
    ) -> Finding | None:
        statement = select(Finding).where(
            Finding.finding_id == finding_id,
            Finding.review_id == review_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def create_decision(self, **values) -> Decision:
        decision = Decision(**values)
        self.session.add(decision)
        await self.session.flush()
        await self.session.refresh(decision)
        return decision

    async def list_decisions(self, review_id: UUID) -> list[Decision]:
        statement = (
            select(Decision)
            .where(Decision.review_id == review_id)
            .order_by(Decision.decided_at, Decision.decision_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def unresolved_high_count(self, review_id: UUID) -> int:
        latest_run_id = select(Review.latest_validation_run_id).where(
            Review.review_id == review_id
        ).scalar_subquery()
        return int(
            await self.session.scalar(
                select(func.count()).select_from(Finding).where(
                    Finding.review_id == review_id,
                    Finding.validation_run_id == latest_run_id,
                    or_(
                        Finding.severity.in_(["HIGH", "CRITICAL"]),
                        Finding.finding_type.in_(HIGH_RISK_FINDING_TYPES),
                    ),
                    Finding.status.in_(
                        [
                            "OPEN",
                            "REQUIRES_SUPPLEMENT",
                            "EXPERT_REVIEW",
                            "CONFIRMED_ISSUE",
                        ]
                    ),
                )
            )
            or 0
        )

    async def current_risk_counts(self, review_id: UUID) -> dict[str, int]:
        latest_run_id = select(Review.latest_validation_run_id).where(
            Review.review_id == review_id
        ).scalar_subquery()
        normalized_severity = case(
            (
                Finding.finding_type.in_(HIGH_RISK_FINDING_TYPES)
                & Finding.severity.not_in(["HIGH", "CRITICAL"]),
                "HIGH",
            ),
            (
                (Finding.finding_type == EXPERT_MINIMUM_MEDIUM_TYPE)
                & (Finding.severity == "LOW"),
                "MEDIUM",
            ),
            else_=Finding.severity,
        )
        rows = (
            await self.session.execute(
                select(normalized_severity, func.count())
                .where(
                    Finding.review_id == review_id,
                    Finding.validation_run_id == latest_run_id,
                    Finding.status.in_(
                        [
                            "OPEN",
                            "REQUIRES_SUPPLEMENT",
                            "EXPERT_REVIEW",
                            "CONFIRMED_ISSUE",
                        ]
                    ),
                )
                .group_by(normalized_severity)
            )
        ).all()
        by_severity = {severity: int(count) for severity, count in rows}
        return {
            "high": by_severity.get("HIGH", 0)
            + by_severity.get("CRITICAL", 0),
            "medium": by_severity.get("MEDIUM", 0),
            "low": by_severity.get("LOW", 0),
            "critical": by_severity.get("CRITICAL", 0),
        }

    async def get_case_report_data(self, case_id: UUID):
        return (
            await self.session.execute(
                text(
                    """
                    SELECT case_id, case_no, case_title,
                           valuation_base_date::text AS valuation_base_date,
                           district_code
                    FROM valuation.cases
                    WHERE case_id = :case_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().one()

    async def next_report_version(self, case_id: UUID) -> int:
        value = await self.session.scalar(
            text(
                """
                SELECT coalesce(max(version_no), 0) + 1
                FROM valuation.documents
                WHERE case_id = :case_id AND document_type = 'review-report'
                """
            ),
            {"case_id": case_id},
        )
        return int(value)

    async def save_report_document(self, **values):
        """Persist generated-report metadata.

        `document_type` and `mime_type` are explicit so the same numbering and
        storage discipline covers PDF, XLSX, and DOCX artifacts. The returned
        dict keeps bucket/object key for repository-internal use only; public
        responses must be serialized through GeneratedReportRead.
        """
        values.setdefault("document_type", "review-report")
        values.setdefault("mime_type", "application/pdf")
        row = (
            await self.session.execute(
                text(
                    """
                    INSERT INTO valuation.documents (
                        document_id, case_id, document_type, original_filename,
                        mime_type, bucket_name, object_key, checksum_sha256,
                        file_size_bytes, version_no, uploaded_by_user_id,
                        storage_etag
                    ) VALUES (
                        :document_id, :case_id, :document_type, :original_filename,
                        :mime_type, :bucket_name, :object_key,
                        :checksum_sha256, :file_size_bytes, :version_no,
                        :uploaded_by_user_id, :storage_etag
                    )
                    RETURNING document_id, case_id, document_type,
                              original_filename, mime_type, bucket_name,
                              object_key, checksum_sha256, file_size_bytes,
                              version_no
                    """
                ),
                values,
            )
        ).mappings().one()
        return dict(row)

    async def next_generated_version(self, case_id: UUID, document_type: str) -> int:
        value = await self.session.scalar(
            text(
                """
                SELECT coalesce(max(version_no), 0) + 1
                FROM valuation.documents
                WHERE case_id = :case_id AND document_type = :document_type
                """
            ),
            {"case_id": case_id, "document_type": document_type},
        )
        return int(value)

    async def get_report_document_for_review(
        self, document_id: UUID, review_id: UUID
    ):
        """Return internal storage metadata only if the Review owns the case."""
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT d.document_id, d.case_id, d.document_type,
                           d.original_filename, d.mime_type, d.bucket_name,
                           d.object_key, d.checksum_sha256, d.file_size_bytes,
                           d.version_no
                    FROM valuation.documents d
                    JOIN review.reviews r ON r.case_id = d.case_id
                    WHERE d.document_id = :document_id
                      AND r.review_id = :review_id
                    """
                ),
                {"document_id": document_id, "review_id": review_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def get_generated_document_for_case(
        self, document_id: UUID, case_id: UUID
    ):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, case_id, document_type,
                           original_filename, mime_type, bucket_name,
                           object_key, checksum_sha256, file_size_bytes,
                           version_no
                    FROM valuation.documents
                    WHERE document_id = :document_id AND case_id = :case_id
                    """
                ),
                {"document_id": document_id, "case_id": case_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def list_generated_reports(self, case_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, case_id, document_type,
                           original_filename, mime_type, checksum_sha256,
                           file_size_bytes, version_no
                    FROM valuation.documents
                    WHERE case_id = :case_id
                      AND document_type IN (
                          'review-report', 'correction-request'
                      )
                    ORDER BY document_type, version_no DESC, uploaded_at DESC
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings()
        return [dict(row) for row in rows]

    async def get_generated_document(self, document_id: UUID):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT document_id, case_id, document_type,
                           original_filename, mime_type, bucket_name,
                           object_key, checksum_sha256, file_size_bytes,
                           version_no
                    FROM valuation.documents
                    WHERE document_id = :document_id
                      AND document_type IN (
                          'review-report', 'correction-request'
                      )
                    """
                ),
                {"document_id": document_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    async def get_report_document(self, validation_run_id: UUID):
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT d.document_id, d.case_id, d.document_type,
                           d.original_filename, d.mime_type, d.bucket_name,
                           d.object_key, d.checksum_sha256, d.file_size_bytes,
                           d.version_no
                    FROM valuation.validation_runs r
                    JOIN valuation.documents d ON d.case_id = r.case_id
                    WHERE r.validation_run_id = :validation_run_id
                      AND d.document_type = 'review-report'
                      AND d.original_filename = :original_filename
                      AND d.is_active = true
                    ORDER BY d.version_no DESC, d.uploaded_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "validation_run_id": validation_run_id,
                    "original_filename": f"review-report-{validation_run_id}.pdf",
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row else None
