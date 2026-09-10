from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.valuation.report_packages.factor_catalog import (
    INDIVIDUAL_FACTOR_CODES,
    TEMPLATE_FACTOR_CODES,
)


class DraftModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ReportPageCode(StrEnum):
    S01 = "S01"
    F02_RF = "F02-RF"
    F02 = "F02"


class DraftSourceType(StrEnum):
    MANUAL_DRAFT = "MANUAL_DRAFT"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"
    DOCUMENT_CONFIRMED = "DOCUMENT_CONFIRMED"
    ROUTE_PROVIDER_CONFIRMED = "ROUTE_PROVIDER_CONFIRMED"


class WalkingOriginType(StrEnum):
    SUBJECT_PARCEL_ENTRANCE = "SUBJECT_PARCEL_ENTRANCE"
    BENCHMARK_LAND_ENTRANCE = "BENCHMARK_LAND_ENTRANCE"
    DISTRICT_REPRESENTATIVE = "DISTRICT_REPRESENTATIVE"
    MANUAL_COORDINATE = "MANUAL_COORDINATE"


class S01Observation(DraftModel):
    item_code: str = Field(min_length=1, max_length=80)
    raw_value: str | Decimal | bool | None = None
    facility_name: str | None = Field(default=None, max_length=200)
    walking_distance_m: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    distance_type: Literal["WALKING"] | None = None
    origin_type: WalkingOriginType | None = None
    origin_reference_id: UUID | None = None
    origin_latitude: Decimal | None = Field(
        default=None, ge=Decimal("-90"), le=Decimal("90"), decimal_places=7
    )
    origin_longitude: Decimal | None = Field(
        default=None, ge=Decimal("-180"), le=Decimal("180"), decimal_places=7
    )
    destination_latitude: Decimal | None = Field(
        default=None, ge=Decimal("-90"), le=Decimal("90"), decimal_places=7
    )
    destination_longitude: Decimal | None = Field(
        default=None, ge=Decimal("-180"), le=Decimal("180"), decimal_places=7
    )
    destination_place_id: str | None = Field(default=None, max_length=500)
    walking_duration_seconds: int | None = Field(default=None, ge=0)
    route_provider: str | None = Field(default=None, max_length=100)
    route_method: str | None = Field(default=None, max_length=100)
    route_reference: str | None = Field(default=None, max_length=1000)
    search_radius_m: int | None = Field(default=None, gt=0)
    candidate_count: int | None = Field(default=None, ge=1)
    source_type: DraftSourceType = DraftSourceType.MANUAL_DRAFT
    source_document_id: UUID | None = None
    source_notes: str | None = Field(default=None, max_length=1000)
    measured_at: datetime | None = None
    confirmed_by_user: bool = False

    @model_validator(mode="after")
    def validate_source_and_distance(self):
        if self.item_code not in TEMPLATE_FACTOR_CODES:
            raise ValueError("項目代碼不屬於使用者提供的三頁範本")

        distance_values = (
            self.facility_name,
            self.walking_distance_m,
            self.distance_type,
            self.origin_type,
        )
        if any(value is not None for value in distance_values):
            if any(value is None for value in distance_values):
                raise ValueError("距離資料必須同時提供設施名稱、步行距離與起算點")
            if not self.source_notes:
                raise ValueError("人工步行距離必須說明可驗證的資料來源")
            if not self.confirmed_by_user:
                raise ValueError("步行距離必須先由使用者確認")

        if self.source_type in {
            DraftSourceType.MANUAL_CONFIRMED,
            DraftSourceType.DOCUMENT_CONFIRMED,
            DraftSourceType.ROUTE_PROVIDER_CONFIRMED,
        }:
            if not self.confirmed_by_user or not self.source_notes:
                raise ValueError("已確認資料必須包含來源說明與使用者確認")
        if (
            self.source_type == DraftSourceType.DOCUMENT_CONFIRMED
            and self.source_document_id is None
        ):
            raise ValueError("文件確認資料必須提供來源文件")

        route_values = (
            self.origin_latitude,
            self.origin_longitude,
            self.destination_latitude,
            self.destination_longitude,
            self.walking_duration_seconds,
            self.route_provider,
            self.route_method,
            self.search_radius_m,
            self.candidate_count,
        )
        if any(value is not None for value in route_values):
            if self.source_type != DraftSourceType.ROUTE_PROVIDER_CONFIRMED:
                raise ValueError("外部路線資料必須使用 ROUTE_PROVIDER_CONFIRMED 來源類型")
            if any(value is None for value in route_values):
                raise ValueError("外部路線資料必須完整保存起訖座標、方法與候選數")
            if not self.confirmed_by_user:
                raise ValueError("外部路線候選必須由使用者確認後才能寫入 S01")
        return self


class S01DraftData(DraftModel):
    district_name: str | None = Field(default=None, max_length=200)
    district_boundary: str | None = Field(default=None, max_length=2000)
    survey_date: date | None = None
    urban_plan_status: str | None = Field(default=None, max_length=100)
    land_use_zone: str | None = Field(default=None, max_length=100)
    building_coverage_rate: Decimal | None = Field(
        default=None, ge=0, max_digits=9, decimal_places=4
    )
    floor_area_ratio: Decimal | None = Field(
        default=None, ge=0, max_digits=9, decimal_places=4
    )
    prohibited_building: str | None = Field(default=None, max_length=500)
    restricted_building: str | None = Field(default=None, max_length=1000)
    main_road_name: str | None = Field(default=None, max_length=200)
    main_road_width_m: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    average_road_width_m: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    observations: list[S01Observation] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=5000)
    site_opinion: str = Field(default="", max_length=5000)
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def unique_observation_codes(self):
        codes = [item.item_code for item in self.observations]
        if len(codes) != len(set(codes)):
            raise ValueError("同一 S01 項目不可重複")
        return self


class S01DraftUpdate(DraftModel):
    district_name: str | None = Field(default=None, max_length=200)
    district_boundary: str | None = Field(default=None, max_length=2000)
    survey_date: date | None = None
    urban_plan_status: str | None = Field(default=None, max_length=100)
    land_use_zone: str | None = Field(default=None, max_length=100)
    building_coverage_rate: Decimal | None = Field(
        default=None, ge=0, max_digits=9, decimal_places=4
    )
    floor_area_ratio: Decimal | None = Field(
        default=None, ge=0, max_digits=9, decimal_places=4
    )
    prohibited_building: str | None = Field(default=None, max_length=500)
    restricted_building: str | None = Field(default=None, max_length=1000)
    main_road_name: str | None = Field(default=None, max_length=200)
    main_road_width_m: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    average_road_width_m: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    observations: list[S01Observation] | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)
    site_opinion: str | None = Field(default=None, max_length=5000)
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個 S01 欄位")
        required_collections = {"observations", "notes", "site_opinion"}
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in required_collections
        ):
            raise ValueError("清單或文字欄位不可設為 null")
        return self


class F02RFTargetLevelDraft(DraftModel):
    comparison_target_id: UUID
    display_order: int = Field(ge=1, le=3)
    reported_level: str | None = Field(default=None, max_length=100)
    confirmed_level: str | None = Field(default=None, max_length=100)
    source_notes: str | None = Field(default=None, max_length=1000)
    confirmed_by_user: bool = False
    calculated_adjustment_rate: Decimal | None = Field(
        default=None,
        max_digits=9,
        decimal_places=6,
    )

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.confirmed_level is not None and (
            not self.confirmed_by_user or not self.source_notes
        ):
            raise ValueError("比較標的確認等級必須有人工確認與來源說明")
        return self


class F02RFFactorDraft(DraftModel):
    factor_code: str = Field(min_length=1, max_length=80)
    benchmark_reported_level: str | None = Field(default=None, max_length=100)
    benchmark_confirmed_level: str | None = Field(default=None, max_length=100)
    source_notes: str | None = Field(default=None, max_length=1000)
    confirmed_by_user: bool = False
    targets: list[F02RFTargetLevelDraft] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_factor(self):
        if self.factor_code not in TEMPLATE_FACTOR_CODES:
            raise ValueError("因素代碼不屬於使用者提供的三頁範本")
        if self.benchmark_confirmed_level is not None and (
            not self.confirmed_by_user or not self.source_notes
        ):
            raise ValueError("比準地確認等級必須有人工確認與來源說明")
        orders = [item.display_order for item in self.targets]
        ids = [item.comparison_target_id for item in self.targets]
        if len(orders) != len(set(orders)) or len(ids) != len(set(ids)):
            raise ValueError("同一因素的比較標的 ID 與順序不可重複")
        return self


class F02RFDraftData(DraftModel):
    benchmark_land_id: UUID | None = None
    comparison_analysis_id: UUID | None = None
    rule_version_id: UUID | None = None
    factor_rows: list[F02RFFactorDraft] = Field(default_factory=list, max_length=100)
    other_influences: str = Field(default="", max_length=5000)
    notes: str = Field(default="", max_length=5000)
    appraiser_name: str | None = Field(default=None, max_length=100)
    regional_adjustment_rates: dict[str, Decimal] = Field(default_factory=dict)
    calculation_status: Literal["NOT_CALCULATED", "CALCULATED"] = "NOT_CALCULATED"
    calculation_snapshot: dict = Field(default_factory=dict)
    calculated_at: datetime | None = None
    calculated_by_user_id: UUID | None = None

    @model_validator(mode="after")
    def unique_factor_codes(self):
        codes = [item.factor_code for item in self.factor_rows]
        if len(codes) != len(set(codes)):
            raise ValueError("同一 F02-RF 因素不可重複")
        return self


class F02RFDraftUpdate(DraftModel):
    benchmark_land_id: UUID | None = None
    comparison_analysis_id: UUID | None = None
    rule_version_id: UUID | None = None
    factor_rows: list[F02RFFactorDraft] | None = Field(default=None, max_length=100)
    other_influences: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)
    appraiser_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個 F02-RF 欄位")
        for field in ("factor_rows", "other_influences", "notes"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("清單或文字欄位不可設為 null")
        return self


class F02TargetSelection(DraftModel):
    comparison_target_id: UUID
    display_order: int = Field(ge=1, le=3)
    individual_condition_notes: str = Field(default="", max_length=3000)
    time_adjustment_rate: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("-0.999999"),
        max_digits=9,
        decimal_places=6,
    )
    time_adjustment_source_notes: str | None = Field(default=None, max_length=1000)
    time_adjustment_confirmed_by_user: bool = False
    individual_factors: list["F02IndividualFactorDraft"] = Field(
        default_factory=list,
        max_length=100,
    )
    weight: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=9,
        decimal_places=6,
    )
    weight_reason: str | None = Field(default=None, max_length=1000)
    weight_confirmed_by_user: bool = False
    regional_adjustment_rate: Decimal | None = Field(
        default=None,
        max_digits=9,
        decimal_places=6,
    )
    individual_adjustment_rate: Decimal | None = Field(
        default=None,
        max_digits=9,
        decimal_places=6,
    )
    total_adjustment_absolute: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=9,
        decimal_places=6,
    )
    trial_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
    )
    normal_unit_price_snapshot: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
    )
    transaction_date_snapshot: date | None = None
    date_adjusted_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
    )
    regional_adjusted_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
    )

    @model_validator(mode="after")
    def validate_professional_confirmations(self):
        if self.time_adjustment_rate != 0 and (
            not self.time_adjustment_confirmed_by_user
            or not self.time_adjustment_source_notes
        ):
            raise ValueError("非零價格日期調整必須有人工確認與來源說明")
        if self.weight is not None and (
            not self.weight_confirmed_by_user or not self.weight_reason
        ):
            raise ValueError("比較標的權重必須有人工確認與理由")
        codes = [item.factor_code for item in self.individual_factors]
        if len(codes) != len(set(codes)):
            raise ValueError("同一比較標的的個別因素不可重複")
        return self


class F02IndividualFactorDraft(DraftModel):
    factor_code: str = Field(min_length=1, max_length=80)
    benchmark_reported_level: str | None = Field(default=None, max_length=100)
    benchmark_confirmed_level: str | None = Field(default=None, max_length=100)
    comparable_reported_level: str | None = Field(default=None, max_length=100)
    comparable_confirmed_level: str | None = Field(default=None, max_length=100)
    source_notes: str | None = Field(default=None, max_length=1000)
    confirmed_by_user: bool = False
    calculated_adjustment_rate: Decimal | None = Field(
        default=None,
        max_digits=9,
        decimal_places=6,
    )

    @model_validator(mode="after")
    def validate_factor(self):
        if self.factor_code not in INDIVIDUAL_FACTOR_CODES:
            raise ValueError("因素代碼不屬於正式手冊的 F02 個別因素清單")
        if (
            self.benchmark_confirmed_level is not None
            or self.comparable_confirmed_level is not None
        ) and (not self.confirmed_by_user or not self.source_notes):
            raise ValueError("個別因素確認等級必須有人工確認與來源說明")
        return self


class F02DraftData(DraftModel):
    comparison_workflow_enabled: bool = True
    benchmark_land_id: UUID | None = None
    comparison_analysis_id: UUID | None = None
    comparison_targets: list[F02TargetSelection] = Field(
        default_factory=list,
        max_length=3,
    )
    benchmark_notes: str = Field(default="", max_length=5000)
    notes: str = Field(default="", max_length=5000)
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)
    benchmark_comparison_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=2,
    )
    calculation_status: Literal["NOT_CALCULATED", "CALCULATED"] = "NOT_CALCULATED"
    calculation_snapshot: dict = Field(default_factory=dict)
    calculated_at: datetime | None = None
    calculated_by_user_id: UUID | None = None

    @model_validator(mode="after")
    def unique_targets(self):
        ids = [item.comparison_target_id for item in self.comparison_targets]
        orders = [item.display_order for item in self.comparison_targets]
        if len(ids) != len(set(ids)) or len(orders) != len(set(orders)):
            raise ValueError("比較標的 ID 與顯示順序不可重複")
        return self


class F02DraftUpdate(DraftModel):
    comparison_workflow_enabled: bool | None = None
    benchmark_land_id: UUID | None = None
    comparison_analysis_id: UUID | None = None
    comparison_targets: list[F02TargetSelection] | None = Field(
        default=None,
        max_length=3,
    )
    benchmark_notes: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個 F02 欄位")
        for field in ("comparison_targets", "benchmark_notes", "notes"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("清單或文字欄位不可設為 null")
        return self


class ReportParcelContext(BaseModel):
    parcel_id: UUID
    district_code: str
    section_name: str
    subsection_name: str
    land_no: str
    area_sqm: Decimal
    land_use_zone: str | None
    designated_use: str | None


class ReportBenchmarkContext(BaseModel):
    benchmark_land_id: UUID
    parcel_id: UUID
    benchmark_land_no: str
    price_zone_no: str


class ReportPageContext(BaseModel):
    case_id: UUID
    case_no: str
    case_title: str
    valuation_base_date: date
    city_code: str
    district_code: str
    land_use_type: str | None
    parcels: list[ReportParcelContext]
    benchmark_lands: list[ReportBenchmarkContext]


class ReportPageResponseBase(BaseModel):
    report_id: UUID
    form_instance_id: UUID
    case_id: UUID
    page_code: ReportPageCode
    version_no: int
    form_status: str
    page_schema_version: str
    context: ReportPageContext
    warnings: list[str]


class S01PageResponse(ReportPageResponseBase):
    page_code: Literal[ReportPageCode.S01]
    data: S01DraftData


class F02RFPageResponse(ReportPageResponseBase):
    page_code: Literal[ReportPageCode.F02_RF]
    data: F02RFDraftData


class F02PageResponse(ReportPageResponseBase):
    page_code: Literal[ReportPageCode.F02]
    data: F02DraftData
