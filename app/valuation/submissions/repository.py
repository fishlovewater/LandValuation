from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ResourceNotFoundError
from app.review.models import Review, ValidationRun
from app.review.repository import ReviewRepository
from app.review.rule_selection import (
    RuleCandidate,
    rule_versions_are_handoff_compatible,
    select_effective_rule,
)
from app.valuation.models import (
    CaseEventRecord,
    CaseRecord,
    DocumentRecord,
    DocumentExtractionRecord,
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
    source_template_documents: list[DocumentRecord]
    report_form: FormInstanceRecord | None
    applied_fields: list[dict]
    calculations: dict
    documents: list[dict]
    validation: dict
    execution_context: dict | None = None


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
        source_document_ids = list(dict.fromkeys(command.source_template_document_ids))
        if source_document_ids:
            report_document = await self.session.scalar(
                select(DocumentRecord).where(
                    DocumentRecord.case_id == case_id,
                    DocumentRecord.document_id == command.source_report_document_id,
                    DocumentRecord.document_type == "generated-template-xlsx",
                    DocumentRecord.is_active.is_(True),
                )
            )
        else:
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
            statement = statement.order_by(
                FormInstanceRecord.version_no.desc(),
                FormInstanceRecord.created_at.desc(),
                FormInstanceRecord.form_instance_id.desc(),
            ).limit(1)
            report_form = await self.session.scalar(statement)

        source_template_documents: list[DocumentRecord] = []
        if source_document_ids:
            source_template_documents = list(
                (
                    await self.session.scalars(
                        select(DocumentRecord).where(
                            DocumentRecord.case_id == case_id,
                            DocumentRecord.document_id.in_(source_document_ids),
                            DocumentRecord.document_type == "generated-template-xlsx",
                            DocumentRecord.is_active.is_(True),
                        )
                    )
                ).all()
            )

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
                FormInstanceRecord.form_instance_id.desc(),
            )
            .limit(1)
        )

        if source_document_ids:
            if report_document is None and source_template_documents:
                report_document = source_template_documents[0]
            # Excel handoff uses the authoritative form only as case/version
            # context; it deliberately does not require F02 FINAL or a PDF.
            report_form = authoritative_report_form

        active_document_rows = list(
            (
                await self.session.scalars(
                    select(DocumentRecord)
                    .where(
                        DocumentRecord.case_id == case_id,
                        DocumentRecord.is_active.is_(True),
                    )
                    .order_by(
                        DocumentRecord.document_group_id,
                        DocumentRecord.version_no.desc(),
                        DocumentRecord.uploaded_at.desc(),
                        DocumentRecord.document_id.desc(),
                    )
                )
            ).all()
        )
        active_documents_by_group = {}
        for document in active_document_rows:
            active_documents_by_group.setdefault(document.document_group_id, document)
        active_documents = list(active_documents_by_group.values())
        active_documents_by_id = {
            document.document_id: document for document in active_documents
        }

        latest_extractions_by_document = {}
        if active_documents:
            latest_extraction_rows = list(
                (
                    await self.session.scalars(
                        select(DocumentExtractionRecord)
                        .where(
                            DocumentExtractionRecord.case_id == case_id,
                            DocumentExtractionRecord.document_id.in_(
                                list(active_documents_by_id)
                            ),
                            DocumentExtractionRecord.extraction_status == "COMPLETED",
                        )
                        .order_by(
                            DocumentExtractionRecord.document_id,
                            DocumentExtractionRecord.completed_at.desc().nulls_last(),
                            DocumentExtractionRecord.created_at.desc(),
                            DocumentExtractionRecord.extraction_id.desc(),
                        )
                    )
                ).all()
            )
            for extraction in latest_extraction_rows:
                latest_extractions_by_document.setdefault(
                    extraction.document_id, extraction
                )

        latest_extraction_ids = [
            extraction.extraction_id
            for extraction in latest_extractions_by_document.values()
        ]
        applied_rows = []
        if latest_extraction_ids:
            applied_rows = list(
                (
                    await self.session.scalars(
                        select(ExtractedFieldRecord)
                        .where(
                            ExtractedFieldRecord.case_id == case_id,
                            ExtractedFieldRecord.extraction_id.in_(
                                latest_extraction_ids
                            ),
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
        document_ids.update(source_document_ids)
        referenced_documents = []
        if document_ids:
            referenced_documents = [
                document
                for document in active_documents
                if document.document_id in document_ids
            ]
            missing_document_ids = document_ids - {
                document.document_id for document in referenced_documents
            }
            if missing_document_ids:
                # The explicitly selected report document may be active but not
                # part of the latest-per-group set when old data has multiple
                # active rows.  Keep its metadata in the immutable Snapshot.
                referenced_documents.extend(
                    document
                    for document in active_document_rows
                    if document.document_id in missing_document_ids
                )
            referenced_documents.sort(
                key=lambda document: (
                    document.document_type,
                    str(document.document_group_id),
                    document.version_no,
                    str(document.document_id),
                )
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
                "input_snapshot": validation_run.input_snapshot,
            }
        execution_context = await self._build_execution_context(
            case_id=case_id,
            validation_run=validation_run,
            report_document=report_document,
            report_form=report_form,
            authoritative_report_form=authoritative_report_form,
            source_template_documents=source_template_documents,
        )
        return SubmissionInputs(
            case_version=(
                None
                if authoritative_report_form is None
                else authoritative_report_form.version_no
            ),
            authoritative_report_form=authoritative_report_form,
            source_validation_run=validation_run,
            source_report_document=report_document,
            source_template_documents=source_template_documents,
            report_form=report_form,
            applied_fields=applied_fields,
            calculations=calculations,
            documents=documents,
            validation=validation,
            execution_context=execution_context,
        )

    async def _build_execution_context(
        self,
        *,
        case_id: UUID,
        validation_run: ValidationRun | None,
        report_document: DocumentRecord | None,
        report_form: FormInstanceRecord | None,
        authoritative_report_form: FormInstanceRecord | None,
        source_template_documents: list[DocumentRecord] | None = None,
    ) -> dict | None:
        """Freeze the minimum Valuation context needed by Review execution.

        The public submit command carries only source IDs.  This method is the
        server-side handoff boundary: all Review rule inputs are selected and
        copied while the caller still holds the case lock.
        """
        if source_template_documents:
            return {
                "schema_version": "excel-template-handoff-v1",
                "source_document_ids": [str(item.document_id) for item in source_template_documents],
                "form_instance_id": None if authoritative_report_form is None else str(authoritative_report_form.form_instance_id),
            }

        if (
            validation_run is None
            or report_document is None
            or report_form is None
            or authoritative_report_form is None
        ):
            return None

        if not isinstance(validation_run.input_snapshot, dict) or not validation_run.input_snapshot:
            raise AppError(
                "SUBMISSION_VALIDATION_SNAPSHOT_REQUIRED",
                "送審前來源檢核必須保存不可變輸入快照",
                422,
            )
        if validation_run.rule_version_id is None:
            raise AppError(
                "SUBMISSION_RULE_VERSION_REQUIRED",
                "送審前來源檢核必須保存規則版本",
                422,
            )

        review_repository = ReviewRepository(self.session)
        case_context = await review_repository.get_case_rule_context(case_id)
        if case_context is None:
            raise ResourceNotFoundError("估價案件")
        candidates = await review_repository.list_rule_candidates()
        selection = select_effective_rule(
            (
                RuleCandidate(
                    rule_version_id=str(candidate["rule_version_id"]),
                    status=candidate["status"],
                    effective_from=candidate["effective_from"],
                    effective_to=candidate["effective_to"],
                    case_type=candidate["applicable_case_type"],
                    district_code=candidate["applicable_district_code"],
                    priority=candidate["selection_priority"],
                )
                for candidate in candidates
            ),
            case_context["valuation_base_date"],
            case_context["case_type"],
            case_context["district_code"],
            case_context["form_codes"],
        )
        if selection.rule is None:
            raise AppError(
                "SUBMISSION_RULE_SELECTION_REQUIRED",
                "送審前找不到案件適用的正式規則版本",
                422,
            )
        candidates_by_id = {
            str(candidate["rule_version_id"]): candidate for candidate in candidates
        }
        rule_version = candidates_by_id[selection.rule.rule_version_id]
        source_rule_version = candidates_by_id.get(str(validation_run.rule_version_id))
        if not rule_versions_are_handoff_compatible(
            source_rule_version,
            rule_version,
        ):
            raise AppError(
                "SUBMISSION_RULE_VERSION_CONFLICT",
                "來源檢核規則版本與案件適用規則不一致",
                422,
            )
        rule_source = await review_repository.get_rule_source(
            UUID(str(rule_version["source_document_id"])),
            case_context["valuation_base_date"],
        ) if rule_version.get("source_document_id") is not None else None
        if rule_source is None:
            raise AppError(
                "RULE_SOURCE_UNAVAILABLE",
                "正式規則版本缺少適用且可用的法規來源",
                422,
            )
        validation_rules = await review_repository.list_active_rules(
            UUID(selection.rule.rule_version_id),
            case_context["form_codes"],
        )
        # The immutable Valuation formal-validation snapshot is authoritative
        # for this handoff.  Legacy submissions without that snapshot still
        # require Review-specific field rules, but a completed formal report
        # may legitimately have no additional F01-only Review rules.
        if not validation_rules and not validation_run.input_snapshot:
            raise AppError(
                "SUBMISSION_VALIDATION_RULES_REQUIRED",
                "送審前正式規則版本必須有啟用的審查規則",
                422,
            )

        def form_snapshot(form: FormInstanceRecord) -> dict:
            return {
                "form_instance_id": form.form_instance_id,
                "case_id": form.case_id,
                "form_code": form.form_code,
                "version_no": form.version_no,
                "form_status": form.form_status,
                "output_document_id": form.output_document_id,
                "form_content": form.form_content,
            }

        def document_snapshot(document: DocumentRecord) -> dict:
            return {
                "document_id": document.document_id,
                "case_id": document.case_id,
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

        return {
            "schema_version": "valuation-review-execution-v1",
            "case": {
                "case_id": case_id,
                "case_no": case_context["case_no"],
                "case_title": case_context["case_title"],
                "case_type": case_context["case_type"],
                "district_code": case_context["district_code"],
                "valuation_base_date": case_context["valuation_base_date"],
                "form_codes": sorted(case_context["form_codes"]),
            },
            "source_validation_run": {
                "validation_run_id": validation_run.validation_run_id,
                "case_id": validation_run.case_id,
                "form_instance_id": validation_run.form_instance_id,
                "run_status": validation_run.run_status,
                "passed_count": validation_run.passed_count,
                "warning_count": validation_run.warning_count,
                "failed_count": validation_run.failed_count,
                "rule_version_id": validation_run.rule_version_id,
                "input_snapshot": validation_run.input_snapshot,
                "ruleset_snapshot": validation_run.ruleset_snapshot,
                "completed_at": validation_run.completed_at,
            },
            "report": {
                "form": form_snapshot(report_form),
                "authoritative_form": form_snapshot(authoritative_report_form),
                "document": document_snapshot(report_document),
            },
            "rule_selection": {
                "source_rule_version": source_rule_version,
                "rule_version": rule_version,
                "rule_source": rule_source,
                "validation_rules": validation_rules,
            },
        }

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
