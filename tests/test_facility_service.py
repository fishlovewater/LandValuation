from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.valuation.facilities.schemas import (
    FacilityOriginType,
    ManualWalkingDistanceRequest,
    NearestFacilityRequest,
)
from app.main import app
from app.valuation.facilities.service import FacilityService


def _client() -> MagicMock:
    client = MagicMock()
    client.configured = True
    client.geocode = AsyncMock(return_value={"lat": 25.0, "lng": 121.0})
    client.search_nearby_places = AsyncMock(
        return_value=[
            {"name": "Place 1", "place_id": "id1", "lat": 25.1, "lng": 121.1},
            {"name": "Place 2", "place_id": "id2", "lat": 25.2, "lng": 121.2},
        ]
    )
    client.compute_route_matrix = AsyncMock(
        return_value=[
            {"destination_index": 0, "distance_meters": 500, "duration_seconds": 300},
            {"destination_index": 1, "distance_meters": 200, "duration_seconds": 120},
        ]
    )
    return client


@pytest.mark.asyncio
async def test_find_nearest_facility_returns_unconfirmed_candidate() -> None:
    client = _client()
    service = FacilityService(client)
    reference_id = uuid4()
    request = NearestFacilityRequest(
        facility_type="park",
        origin_type=FacilityOriginType.BENCHMARK_LAND_ENTRANCE,
        origin_address="Test Addr",
        origin_reference_id=reference_id,
        confirm_lookup=True,
    )

    result = await service.find_nearest_facility(request)

    assert result is not None
    assert result["facility_name"] == "Place 2"
    assert result["walking_distance_m"] == 200
    assert result["walking_duration_seconds"] == 120
    assert result["provider"] == "GOOGLE_MAPS"
    assert result["route_method"] == "DISTANCE_MATRIX_WALKING"
    assert result["destination_place_id"] == "id2"
    assert result["route_reference"] is None
    assert result["confirmed_by_user"] is False


@pytest.mark.asyncio
async def test_find_nearest_facility_no_route() -> None:
    client = _client()
    client.compute_route_matrix.return_value = []
    service = FacilityService(client)
    request = NearestFacilityRequest(
        facility_type="park",
        origin_lat="25.0",
        origin_lng="121.0",
        confirm_lookup=True,
    )

    assert await service.find_nearest_facility(request) is None


def test_manual_walking_distance_requires_confirmation_and_valid_range() -> None:
    with pytest.raises(Exception):
        ManualWalkingDistanceRequest(
            item_code="market_proximity",
            facility_name="金山市場",
            walking_distance_m="92",
            source_notes="主辦單位資料",
        )

    accepted = ManualWalkingDistanceRequest(
        item_code="market_proximity",
        facility_name="金山市場",
        walking_distance_m="92",
        source_notes="主辦單位資料",
        confirm_distance=True,
    )
    assert accepted.walking_distance_m == 92


def test_manual_walking_distance_endpoint_is_in_swagger() -> None:
    path = (
        "/api/v1/valuation/cases/{case_id}/reports/{report_id}/"
        "facilities/manual-walking-distance"
    )
    assert path in app.openapi()["paths"]
