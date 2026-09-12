from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.storage.dependencies import Storage
from app.valuation.operations.calculation_service import CalculationService
from app.valuation.operations.report_service import ReportService
from app.valuation.operations.schemas import (
    CalculationRequest,
    CalculationResponse,
    ReportRequest,
    ReportResponse,
    ValidationRequest,
    ValidationResponse,
)
from app.valuation.operations.validation_service import ValidationService

router = APIRouter()

ValuationReader = Annotated[User, Depends(require_permissions("valuation.read"))]
ValuationEditor = Annotated[User, Depends(require_permissions("valuation.update"))]
ReportDownloader = Annotated[User, Depends(require_permissions("document.download"))]


def request_uuid(request: Request) -> UUID | None:
    try:
        return UUID(str(request.state.request_id))
    except (ValueError, TypeError, AttributeError):
        return None


@router.post(
    "/cases/{case_id}/calculations",
    response_model=CalculationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_f03_calculation(
    case_id: UUID,
    payload: CalculationRequest,
    request: Request,
    session: DbSession,
    user: ValuationEditor,
) -> CalculationResponse:
    return await CalculationService(session).run_f03(
        case_id, payload.form_instance_id, user, request_uuid(request)
    )


@router.get(
    "/cases/{case_id}/calculations/{calculation_id}",
    response_model=CalculationResponse,
)
async def get_f03_calculation(
    case_id: UUID,
    calculation_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> CalculationResponse:
    return await CalculationService(session).get(case_id, calculation_id, user)


@router.post(
    "/cases/{case_id}/validations",
    response_model=ValidationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_f03_validation(
    case_id: UUID,
    payload: ValidationRequest,
    request: Request,
    session: DbSession,
    storage: Storage,
    user: ValuationEditor,
) -> ValidationResponse:
    return await ValidationService(session, storage).run_f03(
        case_id, payload.form_instance_id, user, request_uuid(request)
    )


@router.get(
    "/cases/{case_id}/validations/{validation_run_id}",
    response_model=ValidationResponse,
)
async def get_f03_validation(
    case_id: UUID,
    validation_run_id: UUID,
    session: DbSession,
    storage: Storage,
    user: ValuationReader,
) -> ValidationResponse:
    return await ValidationService(session, storage).get(
        case_id, validation_run_id, user
    )


@router.post(
    "/cases/{case_id}/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_f03_report(
    case_id: UUID,
    payload: ReportRequest,
    request: Request,
    session: DbSession,
    storage: Storage,
    user: ValuationEditor,
) -> ReportResponse:
    return await ReportService(session, storage).generate_f03(
        case_id, payload.form_instance_id, user, request_uuid(request)
    )


@router.get("/cases/{case_id}/reports/{document_id}/download")
async def download_f03_report(
    case_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    session: DbSession,
    storage: Storage,
    user: ReportDownloader,
):
    service = ReportService(session, storage)
    document = await service.get_document(case_id, document_id, user)
    response = await storage.download(document.object_key)

    def close_response() -> None:
        response.close()
        response.release_conn()

    background_tasks.add_task(close_response)
    encoded = quote(document.original_filename)
    return StreamingResponse(
        response.stream(64 * 1024),
        media_type=document.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        background=background_tasks,
    )
