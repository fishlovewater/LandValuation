from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import (
    BenchmarkLandRecord,
    BenchmarkValuationRecord,
    ComparisonAnalysisRecord,
    ParcelRecord,
)


class F03Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_parcel(self, case_id: UUID, parcel_id: UUID) -> ParcelRecord | None:
        return await self.session.scalar(
            select(ParcelRecord).where(
                ParcelRecord.case_id == case_id,
                ParcelRecord.parcel_id == parcel_id,
            )
        )

    async def create_benchmark_land(
        self, record: BenchmarkLandRecord
    ) -> BenchmarkLandRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def list_benchmark_lands(self, case_id: UUID) -> list[BenchmarkLandRecord]:
        statement = (
            select(BenchmarkLandRecord)
            .where(BenchmarkLandRecord.case_id == case_id)
            .order_by(BenchmarkLandRecord.benchmark_land_no)
        )
        return list((await self.session.scalars(statement)).all())

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

    async def comparison_analysis_belongs_to_case(
        self, case_id: UUID, comparison_analysis_id: UUID
    ) -> bool:
        result = await self.session.scalar(
            select(ComparisonAnalysisRecord.comparison_analysis_id).where(
                ComparisonAnalysisRecord.case_id == case_id,
                ComparisonAnalysisRecord.comparison_analysis_id
                == comparison_analysis_id,
            )
        )
        return result is not None

    async def get_draft_for_form(
        self, case_id: UUID, form_instance_id: UUID
    ) -> BenchmarkValuationRecord | None:
        return await self.session.scalar(
            select(BenchmarkValuationRecord).where(
                BenchmarkValuationRecord.case_id == case_id,
                BenchmarkValuationRecord.form_instance_id == form_instance_id,
            )
        )

    async def next_version(self, benchmark_land_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.max(BenchmarkValuationRecord.version_no)).where(
                BenchmarkValuationRecord.benchmark_land_id == benchmark_land_id
            )
        )
        return (latest or 0) + 1

    async def save(
        self, record: BenchmarkValuationRecord
    ) -> BenchmarkValuationRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record
