from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.auth.dependencies import DbSession, require_permissions
from app.auth.service import permission_codes
from app.review.repository import ReviewRepository
from app.review.schemas import (
    ReviewAssign,
    ReviewCreate,
    ReviewList,
    ReviewListQuery,
    CompletenessResponse,
    CaseDecisionRequest,
    DecisionRead,
    FindingRead,
    FindingDecisionRequest,
    MissingItemRead,
    ReviewPriority,
    ReportDocumentRead,
    ReviewRead,
    ReviewStatus,
    ReviewUpdate,
    RiskLevel,
    RiskSummaryRead,
    RunCreate,
    SupplementRequest,
    ValidationRunRead,
)
from app.review.service import ReviewService
from app.review.pdf_reports import build_review_pdf
from app.review.reports import ReviewReport
from app.storage.dependencies import Storage

router = APIRouter(prefix="/review", tags=["review"])


def service_for(session: DbSession) -> ReviewService:
    return ReviewService(ReviewRepository(session))


def audit_request_id(request: Request) -> UUID:
    try:
        return UUID(request.state.request_id)
    except (AttributeError, TypeError, ValueError):
        return uuid4()


@router.post("/cases", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review_case(
    payload: ReviewCreate,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).create(payload, user.user_id)


@router.get("/cases", response_model=ReviewList)
async def list_review_cases(
    session: DbSession,
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    assigned_reviewer_id: UUID | None = None,
    risk_level: RiskLevel | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_permissions("review.execute")),
) -> ReviewList:
    query = ReviewListQuery(
        status=status_filter,
        assigned_reviewer_id=assigned_reviewer_id,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )
    items, total = await service_for(session).list(query)
    return ReviewList(items=items, total=total, limit=limit, offset=offset)


@router.get("/cases/{review_id}", response_model=ReviewRead)
async def get_review_case(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).get(review_id)


@router.patch("/cases/{review_id}", response_model=ReviewRead)
async def update_review_case(
    review_id: UUID,
    payload: ReviewUpdate,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).update(review_id, payload)


@router.post("/cases/{review_id}/assign", response_model=ReviewRead)
async def assign_review_case(
    review_id: UUID,
    payload: ReviewAssign,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).assign(review_id, payload.reviewer_id)


@router.post("/cases/{review_id}/priority", response_model=ReviewRead)
async def prioritize_review_case(
    review_id: UUID,
    payload: ReviewPriority,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewRead:
    return await service_for(session).set_priority(
        review_id, payload.priority, payload.reason, user.user_id
    )


@router.post(
    "/cases/{review_id}/completeness-check", response_model=CompletenessResponse
)
async def check_review_completeness(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> CompletenessResponse:
    result, review, items = await service_for(session).check_completeness(
        review_id, user.user_id
    )
    return CompletenessResponse(
        ready=result.ready,
        review_status=review.review_status,
        missing_item_count=review.missing_item_count,
        blocked_rule_codes=sorted(result.blocked_rule_codes),
        items=items,
    )


@router.get("/cases/{review_id}/missing-items", response_model=list[MissingItemRead])
async def list_review_missing_items(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[MissingItemRead]:
    return await service_for(session).list_missing_items(review_id)


@router.post(
    "/cases/{review_id}/supplement-request", response_model=list[MissingItemRead]
)
async def request_review_supplement(
    review_id: UUID,
    payload: SupplementRequest,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[MissingItemRead]:
    return await service_for(session).request_supplement(review_id, payload.due_at)


@router.post(
    "/cases/{review_id}/runs",
    response_model=ValidationRunRead,
    status_code=status.HTTP_200_OK,
)
async def create_review_run(
    review_id: UUID,
    payload: RunCreate,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ValidationRunRead:
    del payload
    run, _summary = await service_for(session).create_run(review_id, user.user_id)
    return run


@router.get("/cases/{review_id}/runs", response_model=list[ValidationRunRead])
async def list_review_runs(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[ValidationRunRead]:
    return await service_for(session).list_runs(review_id)


@router.get("/runs/{validation_run_id}", response_model=ValidationRunRead)
async def get_review_run(
    validation_run_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ValidationRunRead:
    return await service_for(session).get_run(validation_run_id)


@router.get("/runs/{validation_run_id}/findings", response_model=list[FindingRead])
async def list_run_findings(
    validation_run_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> list[FindingRead]:
    return await service_for(session).list_findings(validation_run_id)


@router.get("/findings/{finding_id}", response_model=FindingRead)
async def get_review_finding(
    finding_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> FindingRead:
    return await service_for(session).get_finding(finding_id)


@router.get(
    "/runs/{validation_run_id}/risk-summary", response_model=RiskSummaryRead
)
async def get_run_risk_summary(
    validation_run_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> RiskSummaryRead:
    return await service_for(session).get_risk_summary(validation_run_id)


@router.post(
    "/findings/{finding_id}/decisions",
    response_model=DecisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def decide_review_finding(
    finding_id: UUID,
    payload: FindingDecisionRequest,
    request: Request,
    session: DbSession,
    user=Depends(require_permissions("review.decide")),
) -> DecisionRead:
    return await service_for(session).decide_finding(
        finding_id,
        payload,
        user.user_id,
        audit_request_id(request),
    )


@router.post(
    "/cases/{review_id}/decision",
    response_model=DecisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def decide_review_case(
    review_id: UUID,
    payload: CaseDecisionRequest,
    request: Request,
    session: DbSession,
    user=Depends(require_permissions("review.decide")),
) -> DecisionRead:
    return await service_for(session).decide_case(
        review_id,
        payload,
        user.user_id,
        audit_request_id(request),
        "review.override_high_risk" in permission_codes(user),
    )


@router.get("/cases/{review_id}/decisions", response_model=list[DecisionRead])
async def list_review_decisions(
    review_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.decide")),
) -> list[DecisionRead]:
    return await service_for(session).list_decisions(review_id)


@router.post(
    "/cases/{review_id}/rerun",
    response_model=ValidationRunRead,
    status_code=status.HTTP_200_OK,
)
async def rerun_review_case(
    review_id: UUID,
    payload: RunCreate,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ValidationRunRead:
    del payload
    run, _summary = await service_for(session).rerun(review_id, user.user_id)
    return run


@router.get("/runs/{validation_run_id}/report", response_model=ReviewReport)
async def get_structured_review_report(
    validation_run_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("review.execute")),
) -> ReviewReport:
    return await service_for(session).build_report(validation_run_id)


@router.post(
    "/runs/{validation_run_id}/report/pdf",
    response_model=ReportDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_review_report_pdf(
    validation_run_id: UUID,
    session: DbSession,
    storage: Storage,
    user=Depends(require_permissions("review.execute")),
) -> ReportDocumentRead:
    service = service_for(session)
    run = await service.get_run(validation_run_id)
    report = await service.build_report(validation_run_id)
    content = build_review_pdf(report)
    document_id = uuid4()
    version = await service.repository.next_report_version(run.case_id)
    object_key = (
        f"cases/{run.case_id}/generated/{document_id}/v{version}/review-report.pdf"
    )
    uploaded = await storage.upload(
        object_key,
        BytesIO(content),
        len(content),
        content_type="application/pdf",
    )
    try:
        metadata = await service.repository.save_report_document(
            document_id=document_id,
            case_id=run.case_id,
            original_filename=f"review-report-{validation_run_id}.pdf",
            bucket_name=uploaded["bucket_name"],
            object_key=uploaded["object_key"],
            checksum_sha256=uploaded["checksum_sha256"],
            file_size_bytes=uploaded["file_size_bytes"],
            version_no=version,
            uploaded_by_user_id=user.user_id,
            storage_etag=uploaded.get("etag"),
        )
    except Exception:
        await storage.delete(object_key)
        raise
    return ReportDocumentRead(**metadata)


@router.get("/runs/{validation_run_id}/report/pdf/download")
async def download_review_report_pdf(
    validation_run_id: UUID,
    session: DbSession,
    storage: Storage,
    user=Depends(require_permissions("review.execute")),
) -> Response:
    service = service_for(session)
    await service.get_run(validation_run_id)
    metadata = await service.repository.get_report_document(validation_run_id)
    if metadata is None:
        from app.core.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError("審查報告 PDF")
    downloaded = await storage.download(metadata["object_key"])
    try:
        content = await run_in_threadpool(downloaded.read)
    finally:
        await run_in_threadpool(downloaded.close)
        await run_in_threadpool(downloaded.release_conn)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{metadata["original_filename"]}"'
            )
        },
    )
