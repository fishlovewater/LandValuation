from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.valuation.f03_repository import F03Repository
from app.valuation.f03_schemas import BenchmarkLandCreate, F03DraftUpdate
from app.valuation.models import (
    BenchmarkLandRecord,
    BenchmarkValuationRecord,
    FormInstanceRecord,
)
from app.valuation.service import ValuationService


class F03Service:
    def __init__(
        self,
        session: AsyncSession,
        repository: F03Repository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or F03Repository(session)
        self.valuation = ValuationService(session)

    async def create_benchmark_land(
        self, case_id: UUID, payload: BenchmarkLandCreate, user: User
    ) -> BenchmarkLandRecord:
        await self.valuation._owned_editable_case(case_id, user)
        if await self.repository.get_parcel(case_id, payload.parcel_id) is None:
            raise ResourceNotFoundError("同案件宗地")
        record = BenchmarkLandRecord(case_id=case_id, **payload.model_dump())
        return await self.repository.create_benchmark_land(record)

    async def list_benchmark_lands(
        self, case_id: UUID, user: User
    ) -> list[BenchmarkLandRecord]:
        await self.valuation.get_case(case_id, user)
        return await self.repository.list_benchmark_lands(case_id)

    async def get_draft(
        self, case_id: UUID, form_id: UUID, user: User
    ) -> BenchmarkValuationRecord:
        await self.valuation.get_case(case_id, user)
        await self._require_f03_form(case_id, form_id)
        record = await self.repository.get_draft_for_form(case_id, form_id)
        if record is None:
            raise ResourceNotFoundError("F03 草稿")
        return record

    async def update_draft(
        self,
        case_id: UUID,
        form_id: UUID,
        payload: F03DraftUpdate,
        user: User,
    ) -> BenchmarkValuationRecord:
        await self.valuation._owned_editable_case(case_id, user)
        form = await self._require_f03_form(case_id, form_id)
        if form.form_status != "DRAFT":
            raise AppError("FORM_STATE_CONFLICT", "只有 F03 草稿可以修改", 409)

        record = await self.repository.get_draft_for_form(case_id, form_id)
        values = payload.model_dump(exclude_unset=True)
        if record is None:
            benchmark_land_id = values.get("benchmark_land_id")
            valuation_base_date = values.get("valuation_base_date")
            if benchmark_land_id is None or valuation_base_date is None:
                raise AppError(
                    "F03_REQUIRED_FIELDS",
                    "建立 F03 草稿時必須提供 benchmark_land_id 與 valuation_base_date",
                    422,
                )
            await self._require_benchmark_land(case_id, benchmark_land_id)
            await self._validate_analysis(case_id, values.get("comparison_analysis_id"))
            comparison_weight = values.pop(
                "comparison_weight", Decimal("1.000000")
            )
            income_weight = values.pop("income_weight", Decimal("0.000000"))
            record = BenchmarkValuationRecord(
                case_id=case_id,
                form_instance_id=form_id,
                version_no=await self.repository.next_version(benchmark_land_id),
                valuation_status="DRAFT",
                comparison_weight=comparison_weight,
                income_weight=income_weight,
                **values,
            )
        else:
            if (
                "benchmark_land_id" in values
                and values["benchmark_land_id"] != record.benchmark_land_id
            ):
                raise AppError(
                    "F03_BENCHMARK_CONFLICT",
                    "已建立的 F03 草稿不可更換比準地，請建立新表單版本",
                    409,
                )
            await self._validate_analysis(case_id, values.get("comparison_analysis_id"))
            for field, value in values.items():
                setattr(record, field, value)

        self._validate_weights(record)
        self._validate_market_period(record)
        return await self.repository.save(record)

    async def _require_f03_form(
        self, case_id: UUID, form_id: UUID
    ) -> FormInstanceRecord:
        form = await self.session.scalar(
            select(FormInstanceRecord).where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_instance_id == form_id,
            )
        )
        if form is None:
            raise ResourceNotFoundError("估價表")
        if form.form_code != "F03":
            raise AppError("FORM_TYPE_MISMATCH", "此端點只接受 F03 表單", 422)
        return form

    async def _require_benchmark_land(
        self, case_id: UUID, benchmark_land_id: UUID
    ) -> BenchmarkLandRecord:
        record = await self.repository.get_benchmark_land(case_id, benchmark_land_id)
        if record is None:
            raise AppError(
                "CROSS_CASE_REFERENCE",
                "比準地不存在、已停用或不屬於此案件",
                422,
            )
        return record

    async def _validate_analysis(
        self, case_id: UUID, comparison_analysis_id: UUID | None
    ) -> None:
        if comparison_analysis_id is None:
            return
        if not await self.repository.comparison_analysis_belongs_to_case(
            case_id, comparison_analysis_id
        ):
            raise AppError(
                "CROSS_CASE_REFERENCE",
                "比較分析不存在或不屬於此案件",
                422,
            )

    @staticmethod
    def _validate_weights(record: BenchmarkValuationRecord) -> None:
        comparison = Decimal(record.comparison_weight)
        income = Decimal(record.income_weight)
        if abs((comparison + income) - Decimal("1")) > Decimal("0.000001"):
            raise AppError(
                "F03_WEIGHT_SUM",
                "比較法與收益法權重合計必須等於 1",
                422,
            )

    @staticmethod
    def _validate_market_period(record: BenchmarkValuationRecord) -> None:
        if (
            record.market_period_start is not None
            and record.market_period_end is not None
            and record.market_period_end < record.market_period_start
        ):
            raise AppError(
                "F03_MARKET_PERIOD",
                "市場期間結束日不可早於開始日",
                422,
            )
