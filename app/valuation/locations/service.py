from uuid import UUID
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.valuation.models import BenchmarkLandRecord, ValuationLocationRecord
from app.valuation.service import ValuationService
from app.valuation.locations.schemas import LocationCreate, LocationUpdate

class ValuationLocationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.valuation = ValuationService(session)

    async def list(self, case_id: UUID, user: User, active_only: bool = True):
        await self.valuation.get_case(case_id, user)
        stmt = select(ValuationLocationRecord).where(ValuationLocationRecord.case_id == case_id)
        if active_only:
            stmt = stmt.where(ValuationLocationRecord.is_active.is_(True))
        return list((await self.session.scalars(stmt.order_by(ValuationLocationRecord.display_order))).all())

    async def create(self, case_id: UUID, payload: LocationCreate, user: User):
        await self.valuation._owned_editable_case(case_id, user)
        next_order = (await self.session.scalar(select(func.coalesce(func.max(ValuationLocationRecord.display_order), 0)).where(ValuationLocationRecord.case_id == case_id))) + 1
        record = ValuationLocationRecord(case_id=case_id, display_order=next_order, label=payload.label, address=payload.address)
        self.session.add(record)
        await self.session.flush(); await self.session.refresh(record)
        return record

    async def update(self, case_id: UUID, location_id: UUID, payload: LocationUpdate, user: User):
        await self.valuation._owned_editable_case(case_id, user)
        record = await self._get(case_id, location_id)
        for field in payload.model_fields_set:
            setattr(record, field, getattr(payload, field))
        await self.session.flush(); await self.session.refresh(record)
        return record

    async def set_benchmark(self, case_id: UUID, location_id: UUID, user: User):
        await self.valuation._owned_editable_case(case_id, user)
        record = await self._get(case_id, location_id)
        await self.session.execute(update(ValuationLocationRecord).where(ValuationLocationRecord.case_id == case_id).values(is_benchmark_location=False))
        record.is_benchmark_location = True
        await self.session.flush(); await self.session.refresh(record)
        return record

    async def archive(self, case_id: UUID, location_id: UUID, user: User):
        await self.valuation._owned_editable_case(case_id, user)
        record = await self._get(case_id, location_id)
        if record.is_benchmark_location:
            raise AppError('BENCHMARK_LOCATION_ARCHIVE_BLOCKED', '此地點目前是比準地，請先選擇其他比準地', 409)
        count = await self.session.scalar(select(func.count()).select_from(ValuationLocationRecord).where(ValuationLocationRecord.case_id == case_id, ValuationLocationRecord.is_active.is_(True)))
        if count <= 1:
            raise AppError('LAST_LOCATION_ARCHIVE_BLOCKED', '案件至少必須保留一個估價地點', 409)
        record.is_active = False
        await self.session.flush(); await self.session.refresh(record)
        return record

    async def _get(self, case_id: UUID, location_id: UUID):
        record = await self.session.scalar(select(ValuationLocationRecord).where(ValuationLocationRecord.case_id == case_id, ValuationLocationRecord.location_id == location_id))
        if record is None:
            raise ResourceNotFoundError('估價地點')
        return record