from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FacilityOriginType(StrEnum):
    SUBJECT_PARCEL_ENTRANCE = "SUBJECT_PARCEL_ENTRANCE"
    BENCHMARK_LAND_ENTRANCE = "BENCHMARK_LAND_ENTRANCE"
    DISTRICT_REPRESENTATIVE = "DISTRICT_REPRESENTATIVE"
    MANUAL_COORDINATE = "MANUAL_COORDINATE"


class NearestFacilityRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    facility_type: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Places 設施類型代碼；只能使用已確認的類型代碼",
    )
    origin_type: FacilityOriginType = FacilityOriginType.MANUAL_COORDINATE
    origin_address: str | None = Field(default=None, min_length=1, max_length=500)
    origin_lat: Decimal | None = Field(
        default=None, ge=Decimal("-90"), le=Decimal("90"), decimal_places=7
    )
    origin_lng: Decimal | None = Field(
        default=None, ge=Decimal("-180"), le=Decimal("180"), decimal_places=7
    )
    origin_reference_id: UUID | None = None
    confirm_lookup: bool = Field(
        default=False,
        description="必須明確設為 true 才會呼叫外部地圖服務",
    )

    @model_validator(mode="after")
    def validate_origin_and_confirmation(self):
        if not self.confirm_lookup:
            raise ValueError("呼叫外部地圖服務前必須將 confirm_lookup 設為 true")
        if (self.origin_lat is None) != (self.origin_lng is None):
            raise ValueError("起點經緯度必須成對提供")
        if (
            self.origin_address is None
            and self.origin_lat is None
            and self.origin_reference_id is None
        ):
            raise ValueError("必須提供起點地址、成對經緯度或案件內起點參照 ID")
        if self.origin_type in {
            FacilityOriginType.SUBJECT_PARCEL_ENTRANCE,
            FacilityOriginType.BENCHMARK_LAND_ENTRANCE,
        } and self.origin_reference_id is None:
            raise ValueError("宗地或比準地起點必須提供 origin_reference_id")
        return self


class NearestFacilityResponse(BaseModel):
    facility_type: str
    facility_name: str
    distance_type: Literal["WALKING"]
    walking_distance_m: Decimal
    walking_duration_seconds: int
    origin_type: FacilityOriginType
    origin_reference_id: UUID | None = None
    origin_latitude: Decimal
    origin_longitude: Decimal
    destination_latitude: Decimal
    destination_longitude: Decimal
    destination_place_id: str | None = None
    provider: Literal["MAPBOX"]
    route_method: Literal["MAPBOX_DIRECTIONS_WALKING"]
    route_reference: str | None = None
    search_radius_m: int
    candidate_count: int
    measured_at: datetime
    confirmed_by_user: Literal[False]


class ManualWalkingDistanceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    item_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="F02-RF 設施距離因素代碼",
    )
    facility_name: str = Field(min_length=1, max_length=200)
    walking_distance_m: Decimal = Field(
        gt=0,
        le=Decimal("100000"),
        max_digits=12,
        decimal_places=2,
    )
    source_notes: str = Field(
        min_length=1,
        max_length=1000,
        description="例如主辦單位資料名稱、查詢日期或人工查詢說明",
    )
    origin_type: FacilityOriginType = FacilityOriginType.DISTRICT_REPRESENTATIVE
    origin_reference_id: UUID | None = None
    confirm_distance: bool = False

    @model_validator(mode="after")
    def validate_confirmation(self):
        if not self.confirm_distance:
            raise ValueError("儲存最短步行距離前必須由使用者明確確認")
        if self.origin_type in {
            FacilityOriginType.SUBJECT_PARCEL_ENTRANCE,
            FacilityOriginType.BENCHMARK_LAND_ENTRANCE,
        } and self.origin_reference_id is None:
            raise ValueError("宗地或比準地起點必須提供 origin_reference_id")
        return self


class ManualWalkingDistanceResponse(BaseModel):
    case_id: UUID
    report_id: UUID
    item_code: str
    facility_name: str
    walking_distance_m: Decimal
    resolved_level: str
    source_notes: str
    confirmed_by_user: Literal[True]
    calculation_status: Literal["NOT_CALCULATED"]
