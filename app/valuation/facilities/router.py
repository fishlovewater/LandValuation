from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.core.exceptions import AppError
from app.valuation.report_packages.repository import ReportPackageRepository
from app.valuation.service import ValuationService

from app.valuation.report_packages.page_service import ReportPageService

from .schemas import (
    FacilityOriginType,
    ManualWalkingDistanceRequest,
    ManualWalkingDistanceResponse,
    NearestFacilityRequest,
    NearestFacilityResponse,
)
from .service import FacilityService

router = APIRouter()

CaseReader = Annotated[User, Depends(require_permissions("case.read"))]
ValuationEditor = Annotated[User, Depends(require_permissions("valuation.update"))]


@router.post(
    "/cases/{case_id}/reports/{report_id}/facilities/manual-walking-distance",
    response_model=ManualWalkingDistanceResponse,
    summary="人工確認最短步行距離並依正式規則判定等級",
    description=(
        "使用者可依主辦單位資料或自行查詢地圖，輸入設施名稱與"
        "最短步行距離。後端驗證、儲存到 S01 form_instances，並依"
        "F02-RF 已選擇的正式規則級距轉換；不會呼叫 Google Maps。"
    ),
)
async def confirm_manual_walking_distance(
    case_id: UUID,
    report_id: UUID,
    payload: ManualWalkingDistanceRequest,
    session: DbSession,
    user: ValuationEditor,
) -> ManualWalkingDistanceResponse:
    level = await ReportPageService(session).confirm_manual_walking_distance(
        case_id,
        report_id,
        item_code=payload.item_code,
        facility_name=payload.facility_name,
        walking_distance_m=payload.walking_distance_m,
        source_notes=payload.source_notes,
        origin_type=payload.origin_type.value,
        origin_reference_id=payload.origin_reference_id,
        user=user,
    )
    return ManualWalkingDistanceResponse(
        case_id=case_id,
        report_id=report_id,
        item_code=payload.item_code,
        facility_name=payload.facility_name,
        walking_distance_m=payload.walking_distance_m,
        resolved_level=level,
        source_notes=payload.source_notes,
        confirmed_by_user=True,
        calculation_status="NOT_CALCULATED",
    )


@router.post(
    "/cases/{case_id}/facilities/nearest",
    response_model=NearestFacilityResponse,
    summary="取得最短步行距離候選（尚未寫入表單）",
)
async def get_nearest_facility(
    case_id: UUID,
    request: NearestFacilityRequest,
    session: DbSession,
    user: CaseReader,
) -> NearestFacilityResponse:
    valuation = ValuationService(session)
    await valuation.get_case(case_id, user)

    resolved_lat: Decimal | None = None
    resolved_lng: Decimal | None = None
    if request.origin_type == FacilityOriginType.BENCHMARK_LAND_ENTRANCE:
        benchmark = await ReportPackageRepository(session).get_benchmark_land(
            case_id, request.origin_reference_id
        )
        if benchmark is None:
            raise AppError(
                "CROSS_CASE_REFERENCE",
                "比準地起點不存在、已停用或不屬於此案件",
                422,
            )
        resolved_lat = request.origin_lat or benchmark.latitude
        resolved_lng = request.origin_lng or benchmark.longitude
    elif request.origin_type == FacilityOriginType.SUBJECT_PARCEL_ENTRANCE:
        parcel = await valuation.repository.get_parcel(
            case_id, request.origin_reference_id
        )
        if parcel is None:
            raise AppError(
                "CROSS_CASE_REFERENCE",
                "宗地起點不存在或不屬於此案件",
                422,
            )

    facility_service = FacilityService()
    try:
        result = await facility_service.find_nearest_facility(
            request,
            resolved_lat=resolved_lat,
            resolved_lng=resolved_lng,
        )
    finally:
        await facility_service.close()

    if result is None:
        raise AppError(
            "FACILITY_CANDIDATE_NOT_FOUND",
            "找不到可計算步行路線的設施候選；尚未寫入 S01",
            404,
        )
    return NearestFacilityResponse.model_validate(result)
