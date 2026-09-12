from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.review.correction_repository import CorrectionRepository
from app.review.repository import ReviewRepository
from app.review.schemas import ReviewCreate, ReviewUpdate
from app.review.schemas import CorrectionRequestItemRead, CorrectionRequestRead
from app.review.status_policy import (
    REVIEW_EXTERNAL_INPUT_MUTATION_STATUSES,
    REVIEW_STARTABLE_STATUSES,
    ensure_review_status_allowed,
)
from app.review.urgency import UrgencyThresholds, classify_urgency
from app.review.workbench_repository import EXTERNAL_REVIEW_CASE_TYPE, WorkbenchRepository
from app.review.workbench_schemas import (
    EligibleCaseRead,
    ExternalReviewCaseCreate,
    ExternalReviewCaseCreatedRead,
    FieldVersionDiffRead,
    WorkbenchCaseDetailRead,
    WorkbenchCaseList,
    WorkbenchCaseListItem,
    WorkbenchCompletenessRead,
    WorkbenchDocumentRead,
    WorkbenchFieldVersionRead,
    WorkbenchLatestRunRead,
    WorkbenchPreflightRead,
    WorkbenchRunRead,
    WorkbenchStartRead,
    WorkbenchSummaryRead,
)
from app.valuation.documents.schemas import DocumentCategory
from app.valuation.extraction.schemas import ExtractionConfirmRequest
from app.valuation.models import CaseRecord


EXTERNAL_REVIEW_DOCUMENT_CATEGORIES = {
    category
    for category in DocumentCategory
    if category != DocumentCategory.COMPLETE_VALUATION_REPORT
}


class WorkbenchService:
    def __init__(
        self,
        repository: WorkbenchRepository,
        review_repository: ReviewRepository,
        corrections: CorrectionRepository | None = None,
    ) -> None:
        self.repository = repository
        self.review_repository = review_repository
        self.corrections = corrections

    async def summary(self) -> WorkbenchSummaryRead:
        return WorkbenchSummaryRead(**(await self.repository.summary()))

    async def create_external_case(
        self,
        payload: ExternalReviewCaseCreate,
        actor_id: UUID,
    ) -> ExternalReviewCaseCreatedRead:
        case_no = (payload.case_no or "").strip()
        if not case_no:
            case_no = (
                f"EXT-{payload.valuation_base_date:%Y%m%d}-"
                f"{uuid4().hex[:6].upper()}"
            )
        if await self.repository.case_no_exists(case_no):
            raise AppError(
                "EXTERNAL_REVIEW_CASE_NO_CONFLICT",
                "案件編號已存在，請改用其他案件編號或留空由系統產生",
                409,
            )

        record = await self.repository.create_external_case(
            CaseRecord(
                case_no=case_no,
                case_title=payload.case_title.strip(),
                case_type=EXTERNAL_REVIEW_CASE_TYPE,
                requesting_agency=(
                    payload.source_organization.strip()
                    if payload.source_organization
                    else None
                ),
                valuation_base_date=payload.valuation_base_date,
                valuation_due_date=None,
                city_code="65000000",
                district_code=payload.district_code,
                land_use_type=None,
                case_status="IN_REVIEW",
                created_by_user_id=actor_id,
                updated_by_user_id=actor_id,
            )
        )
        review = await self.review_repository.create(
            ReviewCreate(
                case_id=record.case_id,
                received_at=payload.received_at,
                due_at=payload.due_at,
            ),
            actor_id,
        )
        review.assigned_reviewer_id = actor_id
        await self.review_repository.session.flush()
        return ExternalReviewCaseCreatedRead(
            review_id=review.review_id,
            case_id=record.case_id,
            case_no=record.case_no,
            review_status=review.review_status,
        )

    async def _external_case(self, review_id: UUID) -> tuple[object, dict]:
        review = await self.review_repository.get(review_id)
        case = await self.repository.get_case_summary(review_id)
        if review is None or case is None:
            raise ResourceNotFoundError("審查案件")
        if case["case_type"] != EXTERNAL_REVIEW_CASE_TYPE:
            raise AppError(
                "EXTERNAL_REVIEW_OPERATION_NOT_ALLOWED",
                "此操作僅適用於外部審查案件",
                409,
            )
        return review, case

    async def _external_case_for_input_mutation(
        self, review_id: UUID, *, action: str
    ) -> tuple[object, dict]:
        review, case = await self._external_case(review_id)
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_EXTERNAL_INPUT_MUTATION_STATUSES,
            action=action,
        )
        return review, case

    async def upload_external_document(
        self,
        review_id: UUID,
        category: DocumentCategory,
        file: UploadFile,
        user: User,
        storage,
        document_group_id: UUID | None = None,
    ) -> WorkbenchDocumentRead:
        _review, case = await self._external_case_for_input_mutation(
            review_id, action="上傳或更新外部審查來源文件"
        )
        if category not in EXTERNAL_REVIEW_DOCUMENT_CATEGORIES:
            raise AppError(
                "EXTERNAL_REVIEW_DOCUMENT_CATEGORY_INVALID",
                "外部審查案件不可上傳系統產出的正式報告類型",
                422,
            )
        from app.valuation.documents.service import DocumentService

        record = await DocumentService(self.repository.session, storage).upload(
            case["case_id"],
            category,
            file,
            user,
            document_group_id,
            _skip_case_access=True,
        )
        return WorkbenchDocumentRead.model_validate(record)

    async def start_external_document_extraction(
        self,
        review_id: UUID,
        document_id: UUID,
        user: User,
        storage,
    ):
        _review, case = await self._external_case_for_input_mutation(
            review_id, action="重新辨識外部審查來源文件"
        )
        from app.valuation.extraction.service import ExtractionService

        return await ExtractionService(self.repository.session, storage).start(
            case["case_id"],
            document_id,
            user,
            _skip_case_access=True,
        )

    async def get_external_document_extraction(
        self,
        review_id: UUID,
        document_id: UUID,
        user: User,
        storage,
    ):
        _review, case = await self._external_case(review_id)
        from app.valuation.extraction.service import ExtractionService

        return await ExtractionService(self.repository.session, storage).get_latest(
            case["case_id"],
            document_id,
            user,
            _skip_case_access=True,
        )

    async def confirm_external_document_extraction(
        self,
        review_id: UUID,
        document_id: UUID,
        payload: ExtractionConfirmRequest,
        user: User,
        storage,
    ):
        _review, case = await self._external_case_for_input_mutation(
            review_id, action="確認外部審查文件辨識欄位"
        )
        from app.valuation.extraction.service import ExtractionService

        return await ExtractionService(self.repository.session, storage).confirm(
            case["case_id"],
            document_id,
            payload,
            user,
            _skip_case_access=True,
            _apply_for_review=True,
        )

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
        sort_by: str = "received_at",
        sort_direction: str = "desc",
    ) -> WorkbenchCaseList:
        # One settings snapshot per request; urgency is never persisted on rows.
        thresholds = (
            await self.corrections.urgency_thresholds()
            if self.corrections is not None
            else UrgencyThresholds()
        )
        now = datetime.now(UTC)
        rows, total = await self.repository.list_cases(
            q,
            status_filter,
            risk_level,
            status_group,
            limit,
            offset,
            case_source=case_source,
            district=district,
            urgency_level=urgency_level,
            urgency_now=now,
            urgent_days=thresholds.urgent_days,
            due_soon_days=thresholds.due_soon_days,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
        items = []
        for row in rows:
            latest_run = None
            if row["validation_run_id"] is not None:
                latest_run = WorkbenchLatestRunRead(
                    validation_run_id=row["validation_run_id"],
                    run_no=row["run_no"],
                    run_status=row["run_status"],
                )
            urgency = classify_urgency(row["due_at"], now, thresholds)
            fields = {
                key: value
                for key, value in row.items()
                if key not in {"validation_run_id", "run_no", "run_status",
                               "manual_priority"}
            }
            items.append(
                WorkbenchCaseListItem(
                    **fields,
                    latest_run=latest_run,
                    urgency_level=urgency.level,
                    remaining_days=urgency.remaining_days,
                )
            )
        return WorkbenchCaseList(
            items=items, total=total, limit=limit, offset=offset
        )

    async def eligible_cases(self, q: str | None, limit: int) -> list[EligibleCaseRead]:
        return [
            EligibleCaseRead(**row)
            for row in await self.repository.list_eligible_cases(q, limit)
        ]

    @staticmethod
    def _version_diffs(rows: list[dict]) -> list[FieldVersionDiffRead]:
        grouped: dict[
            tuple[UUID, str, str | None], list[WorkbenchFieldVersionRead]
        ] = (
            defaultdict(list)
        )
        for row in rows:
            item = WorkbenchFieldVersionRead(**row)
            grouped[
                (item.document_group_id, item.field_code, item.field_path)
            ].append(item)
        diffs = []
        for (document_group_id, field_code, field_path), versions in sorted(
            grouped.items(),
            key=lambda item: (
                str(item[0][0]),
                item[0][1],
                item[0][2] or "",
            ),
        ):
            if len(versions) < 2:
                continue
            previous, current = versions[-2:]
            if previous.normalized_value == current.normalized_value:
                continue
            diffs.append(
                FieldVersionDiffRead(
                    document_group_id=document_group_id,
                    field_code=field_code,
                    field_path=field_path,
                    previous=previous,
                    current=current,
                )
            )
        return diffs

    def _run_projection(
        self,
        run,
        provenance_by_submission_id: dict[UUID, dict],
        external_snapshot_by_id: dict[UUID, dict] | None = None,
    ) -> WorkbenchRunRead:
        run_submission_id = getattr(run, "submission_id", None)
        submission = (
            provenance_by_submission_id.get(run_submission_id)
            if run_submission_id is not None
            else None
        )
        values = {
            field: getattr(run, field)
            for field in (
                "validation_run_id",
                "case_id",
                "review_id",
                "run_no",
                "run_status",
                "passed_count",
                "warning_count",
                "failed_count",
                "started_at",
                "completed_at",
                "triggered_by_user_id",
                "rule_version_id",
                "model_id",
                "prompt_version",
                "error_code",
                "error_message",
            )
        }
        if submission is not None:
            values.update(
                {
                    "submission_id": submission["submission_id"],
                    "submission_no": submission["submission_no"],
                    "submitted_at": submission["submitted_at"],
                    "input_fingerprint": submission["input_fingerprint"],
                }
            )
        external_snapshot_id = getattr(run, "external_input_snapshot_id", None)
        external_snapshot = (
            (external_snapshot_by_id or {}).get(external_snapshot_id)
            if external_snapshot_id is not None
            else None
        )
        if external_snapshot is not None:
            values.update(
                {
                    "external_input_snapshot_id": external_snapshot_id,
                    "external_input_snapshot_no": external_snapshot["snapshot_no"],
                    "external_input_snapshot_created_at": external_snapshot["created_at"],
                    "external_input_fingerprint": external_snapshot["input_fingerprint"],
                }
            )
        return WorkbenchRunRead(**values)

    async def _submitted_snapshot(self, review) -> dict | None:
        if review.latest_submission_id is None:
            return None
        from app.review.service import ReviewService

        submission = await self.review_repository.get_submission_snapshot_record(
            review.latest_submission_id,
            review_id=review.review_id,
            case_id=review.case_id,
        )
        if submission is None:
            raise ReviewService._invalid_submission_snapshot()
        snapshot = submission.get("input_snapshot")
        ReviewService._snapshot_trusted_inputs(
            snapshot,
            input_fingerprint=submission.get("input_fingerprint"),
        )
        return snapshot

    async def detail(self, review_id: UUID) -> WorkbenchCaseDetailRead:
        review = await self.review_repository.get(review_id)
        case = await self.repository.get_case_summary(review_id)
        if review is None or case is None:
            raise ResourceNotFoundError("審查案件")
        submission = await self.repository.get_submission_provenance(review_id)
        submitted_snapshot = await self._submitted_snapshot(review)
        raw_runs = await self.review_repository.list_runs(review_id)
        provenance_by_submission_id = (
            await self.review_repository.get_submission_provenance_by_ids(
                {
                    run.submission_id
                    for run in raw_runs
                    if run.submission_id is not None
                },
                review_id=review.review_id,
                case_id=review.case_id,
            )
        )
        external_snapshot_by_id = (
            await self.review_repository.get_external_input_snapshot_metadata_by_ids(
                {
                    run.external_input_snapshot_id
                    for run in raw_runs
                    if getattr(run, "external_input_snapshot_id", None) is not None
                },
                review_id=review.review_id,
                case_id=review.case_id,
            )
        )
        missing_items = await self.review_repository.list_missing_items(
            review_id, open_only=False
        )
        decisions = await self.review_repository.list_decisions(review_id)
        findings = []
        risk_summary = None
        report_document = None
        if review.latest_validation_run_id is not None:
            findings = await self.review_repository.list_findings(
                review.latest_validation_run_id
            )
            risk_summary = await self.review_repository.get_risk_summary(
                review.latest_validation_run_id
            )
            report_document = await self.review_repository.get_report_document(
                review.latest_validation_run_id
            )
        if submitted_snapshot is None:
            documents = await self.repository.list_documents(review.case_id)
            field_versions = await self.repository.list_official_field_versions(
                review.case_id
            )
            version_diffs = self._version_diffs(field_versions)
        else:
            documents = [
                WorkbenchDocumentRead(**document)
                for document in submitted_snapshot["documents"]
            ]
            version_diffs = []
        correction_requests = []
        if self.corrections is not None:
            for request in await self.corrections.list_requests(review_id):
                correction_requests.append(
                    CorrectionRequestRead(
                        **{
                            key: value
                            for key, value in vars(request).items()
                            if not key.startswith("_")
                        },
                        items=[
                            CorrectionRequestItemRead.model_validate(item)
                            for item in await self.corrections.list_items(
                                request.correction_request_id
                            )
                        ],
                    )
                )
        runs = [
            self._run_projection(
                run,
                provenance_by_submission_id,
                external_snapshot_by_id,
            )
            for run in raw_runs
        ]
        return WorkbenchCaseDetailRead(
            case=case,
            review=review,
            case_source=("EXTERNAL" if case["case_type"] == EXTERNAL_REVIEW_CASE_TYPE else "PLATFORM"),
            submission_id=(
                None if submission is None else submission["submission_id"]
            ),
            submission_no=(
                None if submission is None else submission["submission_no"]
            ),
            submitted_at=(
                None if submission is None else submission["submitted_at"]
            ),
            input_fingerprint=(
                None if submission is None else submission["input_fingerprint"]
            ),
            documents=documents,
            missing_items=missing_items,
            runs=runs,
            findings=findings,
            risk_summary=risk_summary,
            decisions=decisions,
            version_diffs=version_diffs,
            report_document=report_document,
            generated_reports=await self.review_repository.list_generated_reports(
                review.case_id
            ),
            correction_requests=correction_requests,
        )

    async def start(self, review_id: UUID, actor_id: UUID) -> WorkbenchStartRead:
        from app.review.service import ReviewService

        review_service = ReviewService(self.review_repository)
        review = await review_service.get(review_id)
        is_rerun = review.latest_validation_run_id is not None
        preflight = await self.preflight(review_id, actor_id)
        if preflight.outcome == "BLOCKED":
            return WorkbenchStartRead(
                outcome="BLOCKED",
                completeness=preflight.completeness,
                run=None,
            )
        if is_rerun:
            run, risk_summary = await review_service.rerun(review_id, actor_id)
        else:
            run, risk_summary = await review_service.create_run(review_id, actor_id)
        findings = await review_service.list_findings(run.validation_run_id)
        submission = await self.repository.get_submission_provenance(review_id)
        provenance_by_submission_id = (
            {} if submission is None else {submission["submission_id"]: submission}
        )
        external_snapshot_by_id = (
            await self.review_repository.get_external_input_snapshot_metadata_by_ids(
                {run.external_input_snapshot_id}
                if getattr(run, "external_input_snapshot_id", None) is not None
                else set(),
                review_id=review.review_id,
                case_id=review.case_id,
            )
        )
        return WorkbenchStartRead(
            outcome="COMPLETED",
            completeness=preflight.completeness,
            run=self._run_projection(
                run,
                provenance_by_submission_id,
                external_snapshot_by_id,
            ),
            findings=findings,
            risk_summary=risk_summary,
        )

    async def preflight(
        self, review_id: UUID, actor_id: UUID
    ) -> WorkbenchPreflightRead:
        from app.review.service import ReviewService

        review_service = ReviewService(self.review_repository)
        review = await review_service.get(review_id)
        ensure_review_status_allowed(
            review.review_status,
            REVIEW_STARTABLE_STATUSES,
            action="執行智慧審查前置檢查",
        )
        if review.review_status == "READY_FOR_REVIEW":
            await review_service.update(
                review_id, ReviewUpdate(review_status="PREPROCESSING")
            )
        result, review, items = await review_service.check_completeness(
            review_id, actor_id
        )
        completeness = WorkbenchCompletenessRead.from_result(result, review, items)
        if not result.ready:
            return WorkbenchPreflightRead(
                outcome="BLOCKED", completeness=completeness
            )
        return WorkbenchPreflightRead(
            outcome="READY", completeness=completeness
        )
