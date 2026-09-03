from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.review.models import Review, ValidationRun
from app.valuation.models import (
    CaseEventRecord,
    CaseRecord,
    DocumentRecord,
    ExtractedFieldRecord,
    FormInstanceRecord,
    ReviewSubmissionRecord,
)
from app.valuation.report_packages.requirements import (
    REPORT_COMPARISON_COMMERCIAL,
    REPORT_ROOT_FORM_CODE,
)
from app.valuation.submissions.schemas import SubmitForReviewCommand


@dataclass(frozen=True)
class LockedReview:
    review: Review
    latest_submission: ReviewSubmissionRecord | None


@dataclass(frozen=True)
class SubmissionInputs:
    case_version: int | None
    authoritative_report_form: FormInstanceRecord | None
    source_validation_run: ValidationRun | None
    source_report_document: DocumentRecord | None
    report_form: FormInstanceRecord | None
    applied_fields: list[dict]
    calculations: dict
    documents: list[dict]
    validation: dict


class SubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_case(self, case_id: UUID) -> CaseRecord | None:
        return await self.session.scalar(
            select(CaseRecord)
            .where(CaseRecord.case_id == case_id)
            .with_for_update()
        )

    async def find_by_request(
        self, case_id: UUID, request_id: UUID
    ) -> ReviewSubmissionRecord | None:
        return await self.session.scalar(
            select(ReviewSubmissionRecord).where(
                ReviewSubmissionRecord.case_id == case_id,
                ReviewSubmissionRecord.request_id == request_id,
            )
        )

    async def lock_review_for_case(self, case_id: UUID) -> LockedReview | None:
        review = await self.session.scalar(
            select(Review).where(Review.case_id == case_id).with_for_update()
        )
        if review is None:
            return None
        latest_submission = None
        if review.latest_submission_id is not None:
            latest_submission = await self.session.scalar(
                select(ReviewSubmissionRecord).where(
                    ReviewSubmissionRecord.submission_id == review.latest_submission_id
                )
            )
        return LockedReview(review=review, latest_submission=latest_submission)

    async def load_submission_inputs(
        self, case_id: UUID, command: SubmitForReviewCommand
    ) -> SubmissionInputs:
        validation_run = await self.session.scalar(
            select(ValidationRun).where(
                ValidationRun.case_id == case_id,
                ValidationRun.validation_run_id == command.source_validation_run_id,
            )
        )
        report_document = await self.session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_id == command.source_report_document_id,
                DocumentRecord.document_type == "complete-valuation-report",
                DocumentRecord.is_active.is_(True),
            )
        )
        report_form = None
        if report_document is not None:
            statement = select(FormInstanceRecord).where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_code == REPORT_ROOT_FORM_CODE,
                FormInstanceRecord.output_document_id == report_document.document_id,
            )
            if validation_run is not None:
                statement = statement.where(
                    FormInstanceRecord.form_content["report_id"].astext
                    == str(validation_run.form_instance_id)
                )
            report_form = await self.session.scalar(statement)

        authoritative_report_form = await self.session.scalar(
            select(FormInstanceRecord)
            .where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_code == REPORT_ROOT_FORM_CODE,
                FormInstanceRecord.form_content["report_type"].astext
                == REPORT_COMPARISON_COMMERCIAL,
            )
            .order_by(
                FormInstanceRecord.version_no.desc(),
                FormInstanceRecord.created_at.desc(),
            )
            .limit(1)
        )

        applied_rows = list(
            (
                await self.session.scalars(
                    select(ExtractedFieldRecord)
                    .where(
                        ExtractedFieldRecord.case_id == case_id,
                        ExtractedFieldRecord.field_status == "APPLIED",
                    )
                    .order_by(
                        ExtractedFieldRecord.form_code,
                        ExtractedFieldRecord.field_name,
                        ExtractedFieldRecord.extracted_field_id,
                    )
                )
            ).all()
        )
        applied_fields = [
            {
                "extracted_field_id": row.extracted_field_id,
                "document_id": row.document_id,
                "form_code": row.form_code,
                "field_name": row.field_name,
                "confirmed_value": row.confirmed_value,
                "source_page": row.source_page,
                "source_text": row.source_text,
                "confidence": row.confidence,
                "field_status": row.field_status,
                "confirmed_by_user_id": row.confirmed_by_user_id,
                "confirmed_at": row.confirmed_at,
            }
            for row in applied_rows
        ]

        calculations = {}
        if report_form is not None:
            form_content = (
                report_form.form_content
                if isinstance(report_form.form_content, dict)
                else {}
            )
            form_data = form_content.get("data") or {}
            formal_snapshot = form_data.get("calculation_snapshot")
            if (
                form_data.get("calculation_status") == "CALCULATED"
                and isinstance(formal_snapshot, dict)
                and formal_snapshot
            ):
                calculations = {
                    "F02": {
                        "form_instance_id": report_form.form_instance_id,
                        "calculation_snapshot": formal_snapshot,
                        "benchmark_comparison_price": form_data.get(
                            "benchmark_comparison_price"
                        ),
                        "calculated_at": form_data.get("calculated_at"),
                    }
                }
        document_ids = {
            row.document_id
            for row in applied_rows
            if row.document_id is not None
        }
        if report_document is not None:
            document_ids.add(report_document.document_id)
        referenced_documents = []
        if document_ids:
            referenced_documents = list(
                (
                    await self.session.scalars(
                        select(DocumentRecord)
                        .where(
                            DocumentRecord.case_id == case_id,
                            DocumentRecord.document_id.in_(document_ids),
                        )
                        .order_by(
                            DocumentRecord.document_type,
                            DocumentRecord.version_no,
                            DocumentRecord.document_id,
                        )
                    )
                ).all()
            )
        documents = [
            {
                "document_id": document.document_id,
                "document_type": document.document_type,
                "original_filename": document.original_filename,
                "mime_type": document.mime_type,
                "version_no": document.version_no,
                "document_group_id": document.document_group_id,
                "checksum_sha256": document.checksum_sha256,
                "file_size_bytes": document.file_size_bytes,
                "uploaded_at": document.uploaded_at,
                "is_active": document.is_active,
            }
            for document in referenced_documents
        ]
        validation = {}
        if validation_run is not None:
            validation = {
                "validation_run_id": validation_run.validation_run_id,
                "form_instance_id": validation_run.form_instance_id,
                "run_status": validation_run.run_status,
                "passed_count": validation_run.passed_count,
                "warning_count": validation_run.warning_count,
                "failed_count": validation_run.failed_count,
                "rule_version_id": validation_run.rule_version_id,
                "ruleset_snapshot": validation_run.ruleset_snapshot,
                "completed_at": validation_run.completed_at,
            }
        return SubmissionInputs(
            case_version=(
                None
                if authoritative_report_form is None
                else authoritative_report_form.version_no
            ),
            authoritative_report_form=authoritative_report_form,
            source_validation_run=validation_run,
            source_report_document=report_document,
            report_form=report_form,
            applied_fields=applied_fields,
            calculations=calculations,
            documents=documents,
            validation=validation,
        )

    async def create_review(self, case_id: UUID, actor_id: UUID) -> LockedReview:
        review = Review(
            review_id=uuid4(),
            case_id=case_id,
            review_status="RECEIVED",
            started_by_user_id=actor_id,
            received_at=datetime.now(UTC),
        )
        self.session.add(review)
        return LockedReview(review=review, latest_submission=None)

    async def create_submission(
        self, record: ReviewSubmissionRecord
    ) -> ReviewSubmissionRecord:
        self.session.add(record)
        return record

    async def record_case_event(
        self, case_id: UUID, event_type: str, request_id: UUID, data: dict
    ) -> None:
        self.session.add(
            CaseEventRecord(
                case_id=case_id,
                event_type=event_type,
                event_data=data,
                request_id=request_id,
            )
        )
