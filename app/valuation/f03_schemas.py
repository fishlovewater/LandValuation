from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.valuation.schemas import RequestModel


class BenchmarkLandCreate(RequestModel):
    parcel_id: UUID
    benchmark_land_no: str = Field(min_length=1, max_length=30)
    price_zone_no: str = Field(min_length=1, max_length=30)
    land_consolidation_serial: str | None = Field(default=None, max_length=30)
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class BenchmarkLandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    benchmark_land_id: UUID
    case_id: UUID
    parcel_id: UUID
    benchmark_land_no: str
    price_zone_no: str
    land_consolidation_serial: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class F03DraftUpdate(RequestModel):
    benchmark_land_id: UUID | None = None
    comparison_analysis_id: UUID | None = None
    valuation_base_date: date | None = None
    comparison_price: Decimal | None = Field(
        default=None, ge=0, max_digits=20, decimal_places=2
    )
    comparison_weight: Decimal | None = Field(
        default=None, ge=0, le=1, max_digits=9, decimal_places=6
    )
    income_price: Decimal | None = Field(
        default=None, ge=0, max_digits=20, decimal_places=2
    )
    income_weight: Decimal | None = Field(
        default=None, ge=0, le=1, max_digits=9, decimal_places=6
    )
    market_period_start: date | None = None
    market_period_end: date | None = None
    market_condition: str | None = None
    selection_scope_reason: str | None = None
    decision_reason: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個 F03 欄位")
        required_if_supplied = {
            "benchmark_land_id",
            "valuation_base_date",
            "comparison_weight",
            "income_weight",
        }
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in required_if_supplied
        ):
            raise ValueError("F03 必填欄位與權重不可設為 null")
        if (
            self.market_period_start is not None
            and self.market_period_end is not None
            and self.market_period_end < self.market_period_start
        ):
            raise ValueError("市場期間結束日不可早於開始日")
        return self


class F03DraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    benchmark_valuation_id: UUID
    case_id: UUID
    benchmark_land_id: UUID
    comparison_analysis_id: UUID | None
    form_instance_id: UUID | None
    valuation_base_date: date
    comparison_price: Decimal | None
    comparison_weight: Decimal
    income_price: Decimal | None
    income_weight: Decimal
    benchmark_land_price: Decimal | None
    market_period_start: date | None
    market_period_end: date | None
    market_condition: str | None
    selection_scope_reason: str | None
    decision_reason: str | None
    version_no: int
    valuation_status: str
    created_at: datetime
    updated_at: datetime
