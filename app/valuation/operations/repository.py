from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import F03_DEMO_RULE_SET_CODES, get_settings
from app.valuation.models import (
    BenchmarkLandRecord,
    BenchmarkValuationRecord,
    CaseEventRecord,
    CaseRecord,
    DocumentRecord,
    FormInstanceRecord,
    ParcelRecord,
    RuleVersionRecord,
    ValidationFindingRecord,
    ValidationRuleRecord,
    ValidationRunRecord,
    ValuationResultRecord,
)


class OperationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_case(self, case_id: UUID) -> CaseRecord | None:
        return await self.session.scalar(
            select(CaseRecord).where(CaseRecord.case_id == case_id)
        )

    async def get_form(
        self, case_id: UUID, form_instance_id: UUID
    ) -> FormInstanceRecord | None:
        return await self.session.scalar(
            select(FormInstanceRecord).where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_instance_id == form_instance_id,
            )
        )

    async def get_f03_draft(
        self, case_id: UUID, form_instance_id: UUID
    ) -> BenchmarkValuationRecord | None:
        return await self.session.scalar(
            select(BenchmarkValuationRecord).where(
                BenchmarkValuationRecord.case_id == case_id,
                BenchmarkValuationRecord.form_instance_id == form_instance_id,
            )
        )

    async def get_benchmark_land(
        self, case_id: UUID, benchmark_land_id: UUID
    ) -> BenchmarkLandRecord | None:
        return await self.session.scalar(
            select(BenchmarkLandRecord).where(
                BenchmarkLandRecord.case_id == case_id,
                BenchmarkLandRecord.benchmark_land_id == benchmark_land_id,
                BenchmarkLandRecord.is_active.is_(True),
            )
        )

    async def save_benchmark_land(self, record: BenchmarkLandRecord) -> BenchmarkLandRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_parcel(
        self, case_id: UUID, parcel_id: UUID
    ) -> ParcelRecord | None:
        return await self.session.scalar(
            select(ParcelRecord).where(
                ParcelRecord.case_id == case_id,
                ParcelRecord.parcel_id == parcel_id,
            )
        )

    async def list_parcels(self, case_id: UUID) -> list[ParcelRecord]:
        return list(
            (
                await self.session.scalars(
                    select(ParcelRecord)
                    .where(ParcelRecord.case_id == case_id)
                    .order_by(ParcelRecord.parcel_id)
                )
            ).all()
        )

    async def create_calculation(
        self, record: ValuationResultRecord
    ) -> ValuationResultRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_calculation(
        self, case_id: UUID, calculation_id: UUID
    ) -> ValuationResultRecord | None:
        return await self.session.scalar(
            select(ValuationResultRecord).where(
                ValuationResultRecord.case_id == case_id,
                ValuationResultRecord.valuation_id == calculation_id,
                ValuationResultRecord.valuation_type == "BENCHMARK",
            )
        )

    async def latest_calculation(
        self, case_id: UUID, form_instance_id: UUID
    ) -> ValuationResultRecord | None:
        return await self.session.scalar(
            select(ValuationResultRecord)
            .where(
                ValuationResultRecord.case_id == case_id,
                ValuationResultRecord.form_instance_id == form_instance_id,
                ValuationResultRecord.valuation_type == "BENCHMARK",
                ValuationResultRecord.result_status == "CALCULATED",
            )
            .order_by(
                ValuationResultRecord.calculated_at.desc(),
                ValuationResultRecord.valuation_id.desc(),
            )
            .limit(1)
        )

    async def calculation_for_request(
        self,
        case_id: UUID,
        form_instance_id: UUID,
        request_id: UUID,
    ) -> ValuationResultRecord | None:
        return await self.session.scalar(
            select(ValuationResultRecord).where(
                ValuationResultRecord.case_id == case_id,
                ValuationResultRecord.form_instance_id == form_instance_id,
                ValuationResultRecord.valuation_type == "BENCHMARK",
                ValuationResultRecord.request_id == request_id,
            )
        )

    async def save_f03_draft(
        self, record: BenchmarkValuationRecord
    ) -> BenchmarkValuationRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def save_form(self, record: FormInstanceRecord) -> FormInstanceRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def active_documents(self, case_id: UUID) -> list[DocumentRecord]:
        return list(
            (
                await self.session.scalars(
                    select(DocumentRecord).where(
                        DocumentRecord.case_id == case_id,
                        DocumentRecord.is_active.is_(True),
                    )
                )
            ).all()
        )

    async def get_rule_version(self) -> RuleVersionRecord | None:
        settings = get_settings()
        rule_set_codes = [settings.resolved_f03_validation_rule_set_code]
        # Local Demo databases historically contain the fixed Demo rule under
        # DEMO-F03-FORMAL-VALIDATION while the default development setting is
        # F03_MVP_VALIDATION.  Use the explicitly configured code first, then
        # the approved Demo code so validation can consume the same fixed rule
        # that formal calculation selected.  Production never uses this path.
        if settings.app_env.lower() in {"development", "test"}:
            rule_set_codes.extend(
                code for code in F03_DEMO_RULE_SET_CODES if code not in rule_set_codes
            )
        for rule_set_code in rule_set_codes:
            rule = await self.session.scalar(
                select(RuleVersionRecord).where(
                    RuleVersionRecord.rule_set_code == rule_set_code,
                    RuleVersionRecord.version_no == 1,
                    RuleVersionRecord.status == "PUBLISHED",
                )
            )
            if rule is not None:
                return rule
        return None

    async def list_validation_rules(
        self, rule_version_id: UUID
    ) -> list[ValidationRuleRecord]:
        return list(
            (
                await self.session.scalars(
                    select(ValidationRuleRecord)
                    .where(
                        ValidationRuleRecord.rule_version_id == rule_version_id,
                        ValidationRuleRecord.is_active.is_(True),
                    )
                    .order_by(ValidationRuleRecord.rule_code)
                )
            ).all()
        )

    async def create_validation_run(
        self, record: ValidationRunRecord
    ) -> ValidationRunRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def save_validation_run(
        self, record: ValidationRunRecord
    ) -> ValidationRunRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def add_validation_findings(
        self, records: list[ValidationFindingRecord]
    ) -> None:
        self.session.add_all(records)
        await self.session.flush()

    async def get_validation_run(
        self, case_id: UUID, validation_run_id: UUID
    ) -> ValidationRunRecord | None:
        return await self.session.scalar(
            select(ValidationRunRecord).where(
                ValidationRunRecord.case_id == case_id,
                ValidationRunRecord.validation_run_id == validation_run_id,
            )
        )

    async def validation_for_request(
        self,
        case_id: UUID,
        form_instance_id: UUID,
        request_id: UUID,
    ) -> ValidationRunRecord | None:
        return await self.session.scalar(
            select(ValidationRunRecord).where(
                ValidationRunRecord.case_id == case_id,
                ValidationRunRecord.form_instance_id == form_instance_id,
                ValidationRunRecord.request_id == request_id,
            )
        )

    async def latest_validation_run(
        self, case_id: UUID, form_instance_id: UUID
    ) -> ValidationRunRecord | None:
        return await self.session.scalar(
            select(ValidationRunRecord)
            .where(
                ValidationRunRecord.case_id == case_id,
                ValidationRunRecord.form_instance_id == form_instance_id,
                ValidationRunRecord.run_status == "COMPLETED",
            )
            .order_by(
                ValidationRunRecord.completed_at.desc(),
                ValidationRunRecord.validation_run_id.desc(),
            )
            .limit(1)
        )

    async def list_validation_findings(
        self, validation_run_id: UUID
    ) -> list[ValidationFindingRecord]:
        return list(
            (
                await self.session.scalars(
                    select(ValidationFindingRecord)
                    .where(
                        ValidationFindingRecord.validation_run_id
                        == validation_run_id
                    )
                    .order_by(
                        ValidationFindingRecord.severity.desc(),
                        ValidationFindingRecord.created_at,
                    )
                )
            ).all()
        )

    async def create_event(self, record: CaseEventRecord) -> CaseEventRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def event_for_request(
        self, case_id: UUID, event_type: str, request_id: UUID
    ) -> CaseEventRecord | None:
        return await self.session.scalar(
            select(CaseEventRecord).where(
                CaseEventRecord.case_id == case_id,
                CaseEventRecord.event_type == event_type,
                CaseEventRecord.request_id == request_id,
            )
        )
