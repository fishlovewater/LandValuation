from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select, text
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
from app.review.schemas import ReviewCreate, ReviewListQuery, RunCreate


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
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

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
        self, review: Review, payload: RunCreate, actor_id: UUID
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
            rule_version_id=payload.rule_version_id,
            ruleset_snapshot={"rule_version_id": str(payload.rule_version_id)},
            input_snapshot={
                **payload.input_snapshot,
                "adjustment_checks": [
                    check.model_dump(mode="json")
                    for check in payload.adjustment_checks
                ],
                "expert_checks": [
                    check.model_dump(mode="json") for check in payload.expert_checks
                ],
            },
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

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
        return int(
            await self.session.scalar(
                select(func.count()).select_from(Finding).where(
                    Finding.review_id == review_id,
                    Finding.severity.in_(["HIGH", "CRITICAL"]),
                    Finding.status.in_(["OPEN", "REQUIRES_SUPPLEMENT", "EXPERT_REVIEW"]),
                )
            )
            or 0
        )

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
                        :document_id, :case_id, 'review-report', :original_filename,
                        'application/pdf', :bucket_name, :object_key,
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
