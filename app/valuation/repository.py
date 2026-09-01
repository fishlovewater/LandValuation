from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import (
    BenchmarkValuationRecord,
    CaseRecord,
    DocumentRecord,
    FormInstanceRecord,
    ParcelRecord,
    RuleVersionRecord,
)


class ValuationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_case(self, record: CaseRecord) -> CaseRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_case(self, case_id: UUID) -> CaseRecord | None:
        return await self.session.scalar(
            select(CaseRecord).where(CaseRecord.case_id == case_id)
        )

    async def list_cases(
        self,
        *,
        owner_id: UUID | None,
        case_status: str | None,
        offset: int,
        limit: int,
    ) -> list[CaseRecord]:
        statement = select(CaseRecord)
        if owner_id is not None:
            statement = statement.where(CaseRecord.created_by_user_id == owner_id)
        if case_status is not None:
            statement = statement.where(CaseRecord.case_status == case_status)
        statement = statement.order_by(CaseRecord.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def save_case(self, record: CaseRecord) -> CaseRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def create_parcel(self, record: ParcelRecord) -> ParcelRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_parcel(self, case_id: UUID, parcel_id: UUID) -> ParcelRecord | None:
        return await self.session.scalar(
            select(ParcelRecord).where(
                ParcelRecord.case_id == case_id,
                ParcelRecord.parcel_id == parcel_id,
            )
        )

    async def list_parcels(self, case_id: UUID) -> list[ParcelRecord]:
        statement = (
            select(ParcelRecord)
            .where(ParcelRecord.case_id == case_id)
            .order_by(
                ParcelRecord.district_code,
                ParcelRecord.section_name,
                ParcelRecord.subsection_name,
                ParcelRecord.land_no,
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def save_parcel(self, record: ParcelRecord) -> ParcelRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def document_belongs_to_case(self, case_id: UUID, document_id: UUID) -> bool:
        result = await self.session.scalar(
            select(DocumentRecord.document_id).where(
                DocumentRecord.case_id == case_id,
                DocumentRecord.document_id == document_id,
                DocumentRecord.is_active.is_(True),
            )
        )
        return result is not None

    async def next_form_version(self, case_id: UUID, form_code: str) -> int:
        latest = await self.session.scalar(
            select(func.max(FormInstanceRecord.version_no)).where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_code == form_code,
            )
        )
        return (latest or 0) + 1

    async def create_form(self, record: FormInstanceRecord) -> FormInstanceRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_form(
        self, case_id: UUID, form_instance_id: UUID
    ) -> FormInstanceRecord | None:
        return await self.session.scalar(
            select(FormInstanceRecord).where(
                FormInstanceRecord.case_id == case_id,
                FormInstanceRecord.form_instance_id == form_instance_id,
            )
        )

    async def list_forms(self, case_id: UUID) -> list[FormInstanceRecord]:
        statement = (
            select(FormInstanceRecord)
            .where(FormInstanceRecord.case_id == case_id)
            .order_by(FormInstanceRecord.form_code, FormInstanceRecord.version_no.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def save_form(self, record: FormInstanceRecord) -> FormInstanceRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_benchmark_valuation(
        self, case_id: UUID, benchmark_valuation_id: UUID
    ) -> BenchmarkValuationRecord | None:
        return await self.session.scalar(
            select(BenchmarkValuationRecord).where(
                BenchmarkValuationRecord.case_id == case_id,
                BenchmarkValuationRecord.benchmark_valuation_id
                == benchmark_valuation_id,
            )
        )

    async def get_formal_rule(self, rule_version_id: UUID) -> RuleVersionRecord | None:
        return await self.session.scalar(
            select(RuleVersionRecord).where(
                RuleVersionRecord.rule_version_id == rule_version_id,
                RuleVersionRecord.status == "PUBLISHED",
                RuleVersionRecord.import_status == "VERIFIED",
            )
        )
