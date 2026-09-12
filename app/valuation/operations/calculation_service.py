from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.valuation.models import CaseEventRecord, ValuationResultRecord
from app.valuation.operations.calculation import (
    FORMULA_VERSION,
    build_calculation_snapshot,
    calculate_f03_price,
)
from app.valuation.operations.repository import OperationsRepository
from app.valuation.operations.schemas import CalculationResponse
from app.valuation.rule_packs.coverage_service import RuleCoverageService
from app.valuation.rule_packs.repository import RulePackRepository
from app.valuation.service import ValuationService


class CalculationService:
    def __init__(
        self,
        session: AsyncSession,
        repository: OperationsRepository | None = None,
        rule_repository: RulePackRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or OperationsRepository(session)
        self.rule_coverage = RuleCoverageService(
            rule_repository or RulePackRepository(session)
        )
        self.valuation = ValuationService(session)

    async def run_f03(
        self,
        case_id: UUID,
        form_instance_id: UUID,
        user: User,
        request_id: UUID | None,
    ) -> CalculationResponse:
        case = await self.valuation._owned_editable_case(case_id, user)
        form = await self.repository.get_form(case_id, form_instance_id)
        if form is None:
            raise ResourceNotFoundError("估價表")
        if form.form_code != "F03":
            raise AppError("FORM_TYPE_MISMATCH", "此計算端點只接受 F03 表單", 422)
        if form.form_status not in {"DRAFT", "READY"}:
            raise AppError("FORM_STATE_CONFLICT", "只有 F03 草稿或 READY 狀態可以重新計算", 409)

        if not case.land_use_type:
            raise AppError(
                "LAND_USE_TYPE_REQUIRED",
                "正式計算前必須指定案件土地用途",
                409,
            )
        applicable_rule = await self.rule_coverage.require(
            district_code=case.district_code,
            land_use_type=case.land_use_type,
            valuation_date=case.valuation_base_date,
        )

        if request_id is not None:
            existing = await self.repository.calculation_for_request(
                case_id, form_instance_id, request_id
            )
            if existing is not None:
                return self.response(existing)

        draft = await self.repository.get_f03_draft(case_id, form_instance_id)
        if draft is None:
            raise ResourceNotFoundError("F03 草稿")
        benchmark_land = await self.repository.get_benchmark_land(
            case_id, draft.benchmark_land_id
        )
        if benchmark_land is None:
            raise AppError(
                "F03_BENCHMARK_CONFLICT",
                "F03 比準地不存在、已停用或不屬於此案件",
                422,
            )

        output = calculate_f03_price(
            comparison_price=draft.comparison_price,
            comparison_weight=draft.comparison_weight,
            income_price=draft.income_price,
            income_weight=draft.income_weight,
        )
        snapshot = build_calculation_snapshot(
            output=output,
            benchmark_valuation_id=str(draft.benchmark_valuation_id),
            benchmark_land_id=str(draft.benchmark_land_id),
            valuation_base_date=draft.valuation_base_date.isoformat(),
        )
        snapshot["rule_version_id"] = str(applicable_rule.rule_version_id)
        snapshot["rule_set_code"] = applicable_rule.rule_set_code
        snapshot["rule_version_no"] = applicable_rule.version_no
        record = await self.repository.create_calculation(
            ValuationResultRecord(
                case_id=case_id,
                parcel_id=benchmark_land.parcel_id,
                form_instance_id=form_instance_id,
                valuation_type="BENCHMARK",
                unit_price=output.result,
                currency_code="TWD",
                calculation_snapshot=snapshot,
                result_status="CALCULATED",
                calculated_by_user_id=user.user_id,
                request_id=request_id,
            )
        )
        draft.benchmark_land_price = output.result
        await self.repository.save_f03_draft(draft)
        await self.repository.create_event(
            CaseEventRecord(
                case_id=case_id,
                event_type="F03_CALCULATION_COMPLETED",
                event_data={
                    "calculation_id": str(record.valuation_id),
                    "form_instance_id": str(form_instance_id),
                    "formula_version": FORMULA_VERSION,
                    "rule_version_id": str(applicable_rule.rule_version_id),
                    "input_fingerprint": output.input_fingerprint,
                    "result": format(output.result, "f"),
                },
                occurred_by_user_id=user.user_id,
                request_id=request_id,
            )
        )
        return self.response(record)

    async def get(
        self, case_id: UUID, calculation_id: UUID, user: User
    ) -> CalculationResponse:
        await self.valuation.get_case(case_id, user)
        record = await self.repository.get_calculation(case_id, calculation_id)
        if record is None:
            raise ResourceNotFoundError("計算結果")
        return self.response(record)

    @staticmethod
    def response(record: ValuationResultRecord) -> CalculationResponse:
        snapshot = record.calculation_snapshot
        return CalculationResponse(
            calculation_id=record.valuation_id,
            case_id=record.case_id,
            form_instance_id=record.form_instance_id,
            benchmark_valuation_id=UUID(snapshot["benchmark_valuation_id"]),
            formula_version=str(snapshot["formula_version"]),
            result=record.unit_price,
            currency_code=record.currency_code,
            calculation_snapshot=snapshot,
            request_id=record.request_id,
            calculated_at=record.calculated_at,
        )
