from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class F01DraftData(StrictDraft):
    price_zone_no: str | None = Field(default=None, max_length=80)
    land_category: str | None = Field(default=None, max_length=100)
    transaction_type: str | None = Field(default=None, max_length=100)
    transaction_no: str | None = Field(default=None, max_length=80)
    transaction_date: date | None = None
    location: str | None = Field(default=None, max_length=500)
    land_area_sqm: Decimal | None = Field(default=None, gt=0, decimal_places=4)
    building_area_sqm: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    transaction_total_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    land_transaction_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    building_transaction_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    parking_transaction_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    price_information_source: str | None = Field(default=None, max_length=1000)
    transaction_conditions: str | None = Field(default=None, max_length=3000)
    rights_scope: str | None = Field(default=None, max_length=300)
    ownership_type: str | None = Field(default=None, max_length=100)
    land_use_zone: str | None = Field(default=None, max_length=300)
    designated_use: str | None = Field(default=None, max_length=100)
    current_use: str | None = Field(default=None, max_length=1000)
    building_status: str | None = Field(default=None, max_length=2000)
    encumbrance_status: str | None = Field(default=None, max_length=1000)
    road_condition: str | None = Field(default=None, max_length=1000)
    building_price_deduction: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    parking_price_deduction: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    special_transaction_adjustment: Decimal = Field(
        default=Decimal("0"), gt=Decimal("-1"), decimal_places=6
    )
    special_adjustment_confirmed_by_user: bool = False
    special_adjustment_source_notes: str | None = Field(default=None, max_length=1000)
    normal_land_total_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    normal_land_unit_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    normalization_notes: str | None = Field(default=None, max_length=3000)
    filled_date: date | None = None
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)
    calculation_status: Literal["NOT_CALCULATED", "CALCULATED"] = "NOT_CALCULATED"
    calculation_snapshot: dict = Field(default_factory=dict)
    calculation_history: list[dict] = Field(default_factory=list)
    calculated_at: datetime | None = None
    calculated_by_user_id: UUID | None = None

    @model_validator(mode="after")
    def validate_adjustment(self):
        if self.special_transaction_adjustment != 0 and (
            not self.special_adjustment_confirmed_by_user
            or not self.special_adjustment_source_notes
        ):
            raise ValueError("非零特殊交易修正必須由使用者確認並說明來源")
        if (
            self.transaction_total_price is not None
            and self.building_price_deduction > self.transaction_total_price
        ):
            raise ValueError("建物價格扣除不可超過交易總價")
        return self


class F01DraftUpdate(StrictDraft):
    price_zone_no: str | None = Field(default=None, max_length=80)
    land_category: str | None = Field(default=None, max_length=100)
    transaction_type: str | None = Field(default=None, max_length=100)
    transaction_no: str | None = Field(default=None, max_length=80)
    transaction_date: date | None = None
    location: str | None = Field(default=None, max_length=500)
    land_area_sqm: Decimal | None = Field(default=None, gt=0, decimal_places=4)
    building_area_sqm: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    transaction_total_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    land_transaction_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    building_transaction_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    parking_transaction_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    price_information_source: str | None = Field(default=None, max_length=1000)
    transaction_conditions: str | None = Field(default=None, max_length=3000)
    rights_scope: str | None = Field(default=None, max_length=300)
    ownership_type: str | None = Field(default=None, max_length=100)
    land_use_zone: str | None = Field(default=None, max_length=300)
    designated_use: str | None = Field(default=None, max_length=100)
    current_use: str | None = Field(default=None, max_length=1000)
    building_status: str | None = Field(default=None, max_length=2000)
    encumbrance_status: str | None = Field(default=None, max_length=1000)
    road_condition: str | None = Field(default=None, max_length=1000)
    building_price_deduction: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    parking_price_deduction: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    special_transaction_adjustment: Decimal | None = Field(
        default=None, gt=Decimal("-1"), decimal_places=6
    )
    special_adjustment_confirmed_by_user: bool | None = None
    special_adjustment_source_notes: str | None = Field(default=None, max_length=1000)
    normalization_notes: str | None = Field(default=None, max_length=3000)
    filled_date: date | None = None
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個 F01 欄位")
        return self


class F04ParcelDraft(StrictDraft):
    parcel_id: UUID
    parcel_adjustment_rate: Decimal = Field(
        default=Decimal("0"), gt=Decimal("-1"), decimal_places=6
    )
    adjustment_confirmed_by_user: bool = False
    adjustment_source_notes: str | None = Field(default=None, max_length=1000)
    parcel_unit_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    parcel_total_value: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_adjustment(self):
        if self.parcel_adjustment_rate != 0 and (
            not self.adjustment_confirmed_by_user or not self.adjustment_source_notes
        ):
            raise ValueError("非零宗地修正率必須由使用者確認並說明正式規則來源")
        return self


class F04DraftData(StrictDraft):
    benchmark_valuation_id: UUID | None = None
    valuation_base_date: date | None = None
    price_zone_no: str | None = Field(default=None, max_length=80)
    rule_version_id: UUID | None = None
    benchmark_land_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    parcel_rows: list[F04ParcelDraft] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=3000)
    filled_date: date | None = None
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)
    calculation_status: Literal["NOT_CALCULATED", "CALCULATED"] = "NOT_CALCULATED"
    calculation_snapshot: dict = Field(default_factory=dict)
    calculation_history: list[dict] = Field(default_factory=list)
    calculated_at: datetime | None = None
    calculated_by_user_id: UUID | None = None

    @model_validator(mode="after")
    def unique_parcels(self):
        ids = [item.parcel_id for item in self.parcel_rows]
        if len(ids) != len(set(ids)):
            raise ValueError("F04 宗地不可重複")
        return self


class F04DraftUpdate(StrictDraft):
    benchmark_valuation_id: UUID | None = None
    valuation_base_date: date | None = None
    price_zone_no: str | None = Field(default=None, max_length=80)
    rule_version_id: UUID | None = None
    parcel_rows: list[F04ParcelDraft] | None = None
    notes: str | None = Field(default=None, max_length=3000)
    filled_date: date | None = None
    handler_name: str | None = Field(default=None, max_length=100)
    section_head_name: str | None = Field(default=None, max_length=100)
    director_name: str | None = Field(default=None, max_length=100)
    appraiser_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一個 F04 欄位")
        if "parcel_rows" in self.model_fields_set and self.parcel_rows is None:
            raise ValueError("F04 宗地清單不可設為 null")
        return self


class OfficialFormDataResponse(BaseModel):
    form_instance_id: UUID
    case_id: UUID
    form_code: Literal["F01", "F04"]
    version_no: int
    form_status: str
    data: F01DraftData | F04DraftData


class OfficialFormValidationResponse(BaseModel):
    form_instance_id: UUID
    form_code: Literal["F01", "F04"]
    valid: bool
    missing_fields: list[str]
    errors: list[str]
