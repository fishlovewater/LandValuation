from collections import defaultdict
from uuid import UUID

from app.core.exceptions import ResourceNotFoundError
from app.review.repository import ReviewRepository
from app.review.schemas import ReviewUpdate
from app.review.workbench_repository import WorkbenchRepository
from app.review.workbench_schemas import (
    EligibleCaseRead,
    FieldVersionDiffRead,
    WorkbenchCaseDetailRead,
    WorkbenchCaseList,
    WorkbenchCaseListItem,
    WorkbenchCompletenessRead,
    WorkbenchFieldVersionRead,
    WorkbenchLatestRunRead,
    WorkbenchStartRead,
    WorkbenchSummaryRead,
)


class WorkbenchService:
    def __init__(
        self,
        repository: WorkbenchRepository,
        review_repository: ReviewRepository,
    ) -> None:
        self.repository = repository
        self.review_repository = review_repository

    async def summary(self) -> WorkbenchSummaryRead:
        return WorkbenchSummaryRead(**(await self.repository.summary()))

    async def list_cases(
        self,
        q: str | None,
        status_filter: str | None,
        risk_level: str | None,
        status_group: str | None,
        limit: int,
        offset: int,
    ) -> WorkbenchCaseList:
        rows, total = await self.repository.list_cases(
            q, status_filter, risk_level, status_group, limit, offset
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
            items.append(WorkbenchCaseListItem(**row, latest_run=latest_run))
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

    async def detail(self, review_id: UUID) -> WorkbenchCaseDetailRead:
        review = await self.review_repository.get(review_id)
        case = await self.repository.get_case_summary(review_id)
        if review is None or case is None:
            raise ResourceNotFoundError("審查案件")
        runs = await self.review_repository.list_runs(review_id)
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
        documents = await self.repository.list_documents(review.case_id)
        field_versions = await self.repository.list_official_field_versions(
            review.case_id
        )
        return WorkbenchCaseDetailRead(
            case=case,
            review=review,
            documents=documents,
            missing_items=missing_items,
            runs=runs,
            findings=findings,
            risk_summary=risk_summary,
            decisions=decisions,
            version_diffs=self._version_diffs(field_versions),
            report_document=report_document,
        )

    async def start(self, review_id: UUID, actor_id: UUID) -> WorkbenchStartRead:
        from app.review.service import ReviewService

        review_service = ReviewService(self.review_repository)
        review = await review_service.get(review_id)
        is_rerun = review.latest_validation_run_id is not None
        if review.review_status in {"RETURNED_FOR_REVISION", "SUPPLEMENT_REQUIRED"}:
            await review_service.update(
                review_id, ReviewUpdate(review_status="PREPROCESSING")
            )
        result, review, items = await review_service.check_completeness(
            review_id, actor_id
        )
        completeness = WorkbenchCompletenessRead.from_result(result, review, items)
        if not result.ready:
            return WorkbenchStartRead(
                outcome="BLOCKED", completeness=completeness, run=None
            )
        if is_rerun:
            run, risk_summary = await review_service.rerun(review_id, actor_id)
        else:
            run, risk_summary = await review_service.create_run(review_id, actor_id)
        findings = await review_service.list_findings(run.validation_run_id)
        return WorkbenchStartRead(
            outcome="COMPLETED",
            completeness=completeness,
            run=run,
            findings=findings,
            risk_summary=risk_summary,
        )
