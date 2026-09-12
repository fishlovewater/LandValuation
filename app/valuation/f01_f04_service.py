from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.valuation.f01_f04_calculation import calculate_f01, calculate_f04
from app.valuation.f01_f04_schemas import (
    F01DraftData,
    F01DraftUpdate,
    F04DraftData,
    F04DraftUpdate,
    OfficialFormDataResponse,
    OfficialFormValidationResponse,
)
from app.valuation.repository import ValuationRepository
from app.valuation.service import ValuationService


class F01F04Service:
    def __init__(
        self,
        session: AsyncSession,
        repository: ValuationRepository | None = None,
        valuation: ValuationService | None = None,
    ) -> None:
        self.repository = repository or ValuationRepository(session)
        self.valuation = valuation or ValuationService(session, self.repository)

    async def get(self, case_id: UUID, form_id: UUID, code: str, user: User):
        await self.valuation.get_case(case_id, user)
        record = await self._form(case_id, form_id, code)
        return self._response(record, code)

    async def update(self, case_id: UUID, form_id: UUID, code: str, payload, user: User):
        await self.valuation._owned_editable_case(case_id, user)
        record = await self._form(case_id, form_id, code)
        if record.form_status != "DRAFT":
            raise AppError("FORM_STATE_CONFLICT", "只有草稿狀態可修改", 409)
        model = F01DraftData if code == "F01" else F04DraftData
        current = self._data(record, model)
        merged = current.model_dump()
        merged.update(payload.model_dump(exclude_unset=True))
        updated = model.model_validate(merged)
        self._invalidate(updated)
        self._save_data(record, updated, user)
        await self.repository.save_form(record)
        return self._response(record, code)

    async def calculate(self, case_id: UUID, form_id: UUID, code: str, user: User):
        await self.valuation._owned_editable_case(case_id, user)
        record = await self._form(case_id, form_id, code)
        now = datetime.now(timezone.utc)
        if code == "F01":
            data = self._data(record, F01DraftData)
            missing = self._missing_f01(data)
            if missing:
                raise AppError("F01_REQUIRED_FIELDS", "F01 資料不完整", 422, {"missing_fields": missing})
            result = calculate_f01(
                data.transaction_total_price,
                data.building_price_deduction,
                data.special_transaction_adjustment,
                data.land_area_sqm,
            )
            snapshot = {
                "formula_code": "NTPC_F01_NORMAL_LAND_PRICE_V1",
                "inputs": {
                    "transaction_total_price": str(data.transaction_total_price),
                    "building_price_deduction": str(data.building_price_deduction),
                    "special_transaction_adjustment": str(data.special_transaction_adjustment),
                    "land_area_sqm": str(data.land_area_sqm),
                },
                "normal_land_total_price": str(result.normal_land_total_price),
                "normal_land_unit_price": str(result.normal_land_unit_price),
                "calculated_at": now.isoformat(),
            }
            data.normal_land_total_price = result.normal_land_total_price
            data.normal_land_unit_price = result.normal_land_unit_price
        else:
            data = self._data(record, F04DraftData)
            missing = await self._missing_f04(case_id, data)
            if missing:
                raise AppError("F04_REQUIRED_FIELDS", "F04 資料不完整", 422, {"missing_fields": missing})
            rows = []
            for row in data.parcel_rows:
                parcel = await self.repository.get_parcel(case_id, row.parcel_id)
                if parcel is None:
                    raise AppError("F04_PARCEL_NOT_FOUND", "F04 宗地不存在或不屬於案件", 422)
                if row.factor_rows:
                    row.parcel_adjustment_rate = sum(
                        (item.difference_rate or Decimal("0") for item in row.factor_rows),
                        Decimal("0"),
                    )
                    row.adjustment_confirmed_by_user = all(
                        item.difference_rate in (None, Decimal("0")) or item.confirmed_by_user
                        for item in row.factor_rows
                    )
                    if not row.adjustment_source_notes:
                        row.adjustment_source_notes = "依表6已確認個別因素差異率合計"
                value = calculate_f04(
                    data.benchmark_land_price,
                    row.parcel_adjustment_rate,
                    parcel.area_sqm,
                    parcel.ownership_numerator,
                    parcel.ownership_denominator,
                )
                row.parcel_unit_price = value.parcel_unit_price
                row.parcel_total_value = value.parcel_total_value
                rows.append({
                    "parcel_id": str(row.parcel_id),
                    "parcel_adjustment_rate": str(row.parcel_adjustment_rate),
                    "factor_rows": [
                        item.model_dump(mode="json") for item in row.factor_rows
                    ],
                    "trial_unit_price": str(value.trial_unit_price),
                    "parcel_unit_price": str(value.parcel_unit_price),
                    "parcel_total_value": str(value.parcel_total_value),
                })
            snapshot = {
                "formula_code": "NTPC_F04_PARCEL_MARKET_VALUE_V2",
                "rounding_code": "ARTICLE_21_ROUND_UP_BY_MAGNITUDE",
                "benchmark_valuation_id": str(data.benchmark_valuation_id),
                "rule_version_id": str(data.rule_version_id),
                "benchmark_land_price": str(data.benchmark_land_price),
                "rows": rows,
                "calculated_at": now.isoformat(),
            }
        data.calculation_status = "CALCULATED"
        data.calculation_snapshot = snapshot
        data.calculation_history = [*data.calculation_history, snapshot]
        data.calculated_at = now
        data.calculated_by_user_id = user.user_id
        self._save_data(record, data, user)
        await self.repository.save_form(record)
        return self._response(record, code)

    async def validate(self, case_id: UUID, form_id: UUID, code: str, user: User):
        await self.valuation.get_case(case_id, user)
        record = await self._form(case_id, form_id, code)
        if code == "F01":
            data = self._data(record, F01DraftData)
            missing = self._missing_f01(data)
        else:
            data = self._data(record, F04DraftData)
            missing = await self._missing_f04(case_id, data)
        errors = []
        if data.calculation_status != "CALCULATED":
            errors.append(f"{code}_CALCULATION_REQUIRED")
        return OfficialFormValidationResponse(
            form_instance_id=form_id,
            form_code=code,
            valid=not missing and not errors,
            missing_fields=missing,
            errors=errors,
        )

    async def _form(self, case_id: UUID, form_id: UUID, code: str):
        record = await self.repository.get_form(case_id, form_id)
        if record is None:
            raise ResourceNotFoundError(f"{code} 表單")
        if record.form_code != code:
            raise AppError("FORM_TYPE_MISMATCH", f"此端點只接受 {code} 表單", 422)
        return record

    @staticmethod
    def _data(record, model):
        content = record.form_content if isinstance(record.form_content, dict) else {}
        try:
            return model.model_validate(content.get("data") or {})
        except ValueError as exc:
            raise AppError("FORM_CONTENT_INVALID", "表單內容不符合官方 Schema", 409) from exc

    @staticmethod
    def _save_data(record, data, user):
        content = dict(record.form_content or {})
        content["data"] = data.model_dump(mode="json")
        record.form_content = content
        record.updated_by_user_id = user.user_id

    @staticmethod
    def _invalidate(data):
        data.calculation_status = "NOT_CALCULATED"
        data.calculation_snapshot = {}
        data.calculated_at = None
        data.calculated_by_user_id = None
        if isinstance(data, F01DraftData):
            data.normal_land_total_price = None
            data.normal_land_unit_price = None
        else:
            for row in data.parcel_rows:
                row.parcel_unit_price = None
                row.parcel_total_value = None

    @staticmethod
    def _missing_f01(data: F01DraftData) -> list[str]:
        names = ("transaction_no", "transaction_date", "location", "land_area_sqm", "transaction_total_price")
        return [name for name in names if getattr(data, name) is None]

    async def _missing_f04(self, case_id: UUID, data: F04DraftData) -> list[str]:
        missing = [
            name for name in (
                "benchmark_valuation_id", "valuation_base_date", "price_zone_no",
                "rule_version_id", "benchmark_land_price",
            ) if getattr(data, name) is None
        ]
        if not data.parcel_rows:
            missing.append("parcel_rows")
        if data.benchmark_valuation_id is not None:
            valuation = await self.repository.get_benchmark_valuation(
                case_id, data.benchmark_valuation_id
            )
            if valuation is None or valuation.valuation_status not in {
                "CALCULATED", "CHECKED", "FINAL"
            }:
                missing.append("benchmark_valuation_id:calculated_result_required")
            elif (
                data.benchmark_land_price is not None
                and valuation.benchmark_land_price != data.benchmark_land_price
            ):
                missing.append("benchmark_land_price:must_match_f03")
        if data.rule_version_id is not None:
            rule = await self.repository.get_formal_rule(data.rule_version_id)
            if rule is None:
                missing.append("rule_version_id:published_verified_rule_required")
        for index, row in enumerate(data.parcel_rows):
            if await self.repository.get_parcel(case_id, row.parcel_id) is None:
                missing.append(f"parcel_rows[{index}].parcel_id")
        return missing

    def _response(self, record, code: str):
        model = F01DraftData if code == "F01" else F04DraftData
        return OfficialFormDataResponse(
            form_instance_id=record.form_instance_id,
            case_id=record.case_id,
            form_code=code,
            version_no=record.version_no,
            form_status=record.form_status,
            data=self._data(record, model),
        )
