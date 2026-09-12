from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.valuation.locations.schemas import LocationCreate, LocationResponse, LocationUpdate
from app.valuation.locations.service import ValuationLocationService
router = APIRouter()
Reader = Annotated[User, Depends(require_permissions('case.read'))]
Editor = Annotated[User, Depends(require_permissions('case.update'))]
@router.get('/cases/{case_id}/locations', response_model=list[LocationResponse])
async def list_locations(case_id: UUID, session: DbSession, user: Reader): return await ValuationLocationService(session).list(case_id, user)
@router.post('/cases/{case_id}/locations', response_model=LocationResponse, status_code=201)
async def create_location(case_id: UUID, payload: LocationCreate, session: DbSession, user: Editor): return await ValuationLocationService(session).create(case_id, payload, user)
@router.patch('/cases/{case_id}/locations/{location_id}', response_model=LocationResponse)
async def update_location(case_id: UUID, location_id: UUID, payload: LocationUpdate, session: DbSession, user: Editor): return await ValuationLocationService(session).update(case_id, location_id, payload, user)
@router.post('/cases/{case_id}/locations/{location_id}/set-benchmark', response_model=LocationResponse)
async def set_benchmark(case_id: UUID, location_id: UUID, session: DbSession, user: Editor): return await ValuationLocationService(session).set_benchmark(case_id, location_id, user)
@router.post('/cases/{case_id}/locations/{location_id}/archive', response_model=LocationResponse)
async def archive_location(case_id: UUID, location_id: UUID, session: DbSession, user: Editor): return await ValuationLocationService(session).archive(case_id, location_id, user)