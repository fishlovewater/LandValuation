from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import (
    BenchmarkLandRecord,
    CaseEventRecord,
    ComparisonAnalysisRecord,
    ComparisonFactorValueRecord,
    ComparisonTargetRecord,
    DocumentRecord,
    FactorDefinitionRecord,
    FactorLevelRecord,
    FormInstanceRecord,
    RuleVersionRecord,
    ValidationRunRecord,
)
from app.valuation.report_packages.requirements import (
    REPORT_COMPARISON_COMMERCIAL,
    REPORT_ROOT_FORM_CODE,
)


class ReportPackageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_version(self, case_id: UUID, form_codes: tuple[str, ...]) -> int:
        latest = await self.session.scalar(
            select(func.max(FormInstanceRecord.version_no)).where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_code.in_(form_codes),
            )
        )
        return (latest or 0) + 1

    async def create_forms(
        self, records: list[FormInstanceRecord]
    ) -> list[FormInstanceRecord]:
        self.session.add_all(records)
        await self.session.flush()
        for record in records:
            await self.session.refresh(record)
        return records

    async def get_form(
        self, case_id: UUID, form_instance_id: UUID
    ) -> FormInstanceRecord | None:
        return await self.session.scalar(
            select(FormInstanceRecord).where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_instance_id == form_instance_id,
            )
        )

    async def get_forms(
        self, case_id: UUID, form_instance_ids: set[UUID]
    ) -> list[FormInstanceRecord]:
        if not form_instance_ids:
            return []
        return list(
            (
                await self.session.scalars(
                    select(FormInstanceRecord).where(
                        FormInstanceRecord.case_id == case_id,
                        FormInstanceRecord.form_instance_id.in_(form_instance_ids),
                    )
                )
            ).all()
        )

    async def latest_root(self, case_id: UUID) -> FormInstanceRecord | None:
        return await self.session.scalar(
            select(FormInstanceRecord)
            .where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_code == REPORT_ROOT_FORM_CODE,
                FormInstanceRecord.form_content["report_type"].astext
                == REPORT_COMPARISON_COMMERCIAL,
            )
            .order_by(
                FormInstanceRecord.version_no.desc(),
                FormInstanceRecord.created_at.desc(),
            )
            .limit(1)
        )

    async def active_document_types(self, case_id: UUID) -> set[str]:
        values = await self.session.scalars(
            select(DocumentRecord.document_type).where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.is_active.is_(True),
            )
        )
        return set(values.all())

    async def active_documents_by_types(
        self, case_id: UUID, document_types: set[str]
    ) -> dict[str, DocumentRecord]:
        if not document_types:
            return {}
        values = await self.session.scalars(
            select(DocumentRecord)
            .where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_type.in_(document_types),
                DocumentRecord.is_active.is_(True),
            )
            .order_by(
                DocumentRecord.document_type,
                DocumentRecord.uploaded_at.desc(),
                DocumentRecord.version_no.desc(),
            )
        )
        selected: dict[str, DocumentRecord] = {}
        for record in values.all():
            selected.setdefault(record.document_type, record)
        return selected

    async def save_form(self, record: FormInstanceRecord) -> FormInstanceRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def list_benchmark_lands(
        self, case_id: UUID
    ) -> list[BenchmarkLandRecord]:
        values = await self.session.scalars(
            select(BenchmarkLandRecord)
            .where(
                BenchmarkLandRecord.case_id == case_id,
                BenchmarkLandRecord.is_active.is_(True),
            )
            .order_by(BenchmarkLandRecord.benchmark_land_no)
        )
        return list(values.all())

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

    async def get_comparison_analysis(
        self, case_id: UUID, comparison_analysis_id: UUID
    ) -> ComparisonAnalysisRecord | None:
        return await self.session.scalar(
            select(ComparisonAnalysisRecord).where(
                ComparisonAnalysisRecord.case_id == case_id,
                ComparisonAnalysisRecord.comparison_analysis_id
                == comparison_analysis_id,
                ComparisonAnalysisRecord.analysis_status != "VOID",
            )
        )

    async def list_comparison_targets(
        self, case_id: UUID, comparison_analysis_id: UUID
    ) -> list[ComparisonTargetRecord]:
        values = await self.session.scalars(
            select(ComparisonTargetRecord)
            .where(
                ComparisonTargetRecord.case_id == case_id,
                ComparisonTargetRecord.comparison_analysis_id
                == comparison_analysis_id,
            )
            .order_by(ComparisonTargetRecord.display_order)
        )
        return list(values.all())

    async def get_rule_version(
        self, rule_version_id: UUID
    ) -> RuleVersionRecord | None:
        return await self.session.scalar(
            select(RuleVersionRecord).where(
                RuleVersionRecord.rule_version_id == rule_version_id,
                RuleVersionRecord.status == "PUBLISHED",
            )
        )

    async def list_factor_levels(
        self,
        rule_version_id: UUID,
        land_use_type: str,
        factor_codes: set[str],
    ) -> list[tuple[FactorDefinitionRecord, FactorLevelRecord]]:
        if not factor_codes:
            return []
        rows = await self.session.execute(
            select(FactorDefinitionRecord, FactorLevelRecord)
            .join(
                FactorLevelRecord,
                FactorLevelRecord.factor_definition_id
                == FactorDefinitionRecord.factor_definition_id,
            )
            .where(
                FactorLevelRecord.rule_version_id == rule_version_id,
                FactorLevelRecord.land_use_type == land_use_type,
                FactorDefinitionRecord.factor_code.in_(factor_codes),
                FactorDefinitionRecord.is_active.is_(True),
            )
            .order_by(
                FactorDefinitionRecord.display_order,
                FactorLevelRecord.sort_order,
            )
        )
        return list(rows.tuples().all())

    async def list_factor_values(
        self, comparison_target_ids: set[UUID]
    ) -> list[ComparisonFactorValueRecord]:
        if not comparison_target_ids:
            return []
        values = await self.session.scalars(
            select(ComparisonFactorValueRecord).where(
                ComparisonFactorValueRecord.comparison_target_id.in_(
                    comparison_target_ids
                )
            )
        )
        return list(values.all())

    async def replace_factor_values(
        self,
        comparison_target_ids: set[UUID],
        records: list[ComparisonFactorValueRecord],
    ) -> None:
        from sqlalchemy import delete

        if comparison_target_ids:
            await self.session.execute(
                delete(ComparisonFactorValueRecord).where(
                    ComparisonFactorValueRecord.comparison_target_id.in_(
                        comparison_target_ids
                    )
                )
            )
        self.session.add_all(records)
        await self.session.flush()

    async def save_comparison_analysis(
        self, record: ComparisonAnalysisRecord
    ) -> ComparisonAnalysisRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def save_comparison_targets(
        self, records: list[ComparisonTargetRecord]
    ) -> None:
        await self.session.flush()
        for record in records:
            await self.session.refresh(record)

    async def create_validation_run(
        self, record: ValidationRunRecord
    ) -> ValidationRunRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def latest_report_validation(
        self, case_id: UUID, report_id: UUID
    ) -> ValidationRunRecord | None:
        return await self.session.scalar(
            select(ValidationRunRecord)
            .where(
                ValidationRunRecord.case_id == case_id,
                ValidationRunRecord.form_instance_id == report_id,
                ValidationRunRecord.run_status == "COMPLETED",
            )
            .order_by(
                ValidationRunRecord.completed_at.desc(),
                ValidationRunRecord.validation_run_id.desc(),
            )
            .limit(1)
        )

    async def validation_for_request(
        self, case_id: UUID, report_id: UUID, request_id: UUID
    ) -> ValidationRunRecord | None:
        return await self.session.scalar(
            select(ValidationRunRecord).where(
                ValidationRunRecord.case_id == case_id,
                ValidationRunRecord.form_instance_id == report_id,
                ValidationRunRecord.request_id == request_id,
            )
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

    async def document_belongs_to_case(
        self, case_id: UUID, document_id: UUID
    ) -> bool:
        value = await self.session.scalar(
            select(DocumentRecord.document_id).where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_id == document_id,
                DocumentRecord.is_active.is_(True),
            )
        )
        return value is not None
