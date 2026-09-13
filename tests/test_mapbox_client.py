from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.valuation.facilities.mapbox_client import MapboxClient


def settings() -> Settings:
    return Settings(
        _env_file=None,
        mapbox_access_token="test-token",
        mapbox_username="test-user",
        mapbox_style_id="test-style",
    )


@pytest.mark.asyncio
async def test_mapbox_geocode() -> None:
    http_client = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "features": [{"center": [121.0, 25.0]}]
    }
    http_client.get = AsyncMock(return_value=response)

    client = MapboxClient(settings=settings(), client=http_client)
    result = await client.geocode("Test Address")

    assert result == {"lat": 25.0, "lng": 121.0}
    response.raise_for_status.assert_called_once()
    http_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_mapbox_nearby_search() -> None:
    http_client = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "features": [
            {"text": "Place 1", "id": "id1", "center": [121.1, 25.1]},
            {"text": "Place 2", "id": "id2", "center": [121.2, 25.2]},
        ]
    }
    http_client.get = AsyncMock(return_value=response)

    client = MapboxClient(settings=settings(), client=http_client)
    results = await client.search_nearby_places(25.0, 121.0, "park")

    assert len(results) == 2
    assert results[0]["name"] == "Place 1"
    assert results[0]["place_id"] == "id1"


@pytest.mark.asyncio
async def test_mapbox_walking_routes() -> None:
    http_client = MagicMock()
    responses = []
    for distance, duration in ((500, 300), (200, 120)):
        response = MagicMock()
        response.json.return_value = {
            "routes": [{"distance": distance, "duration": duration}]
        }
        responses.append(response)
    http_client.get = AsyncMock(side_effect=responses)

    client = MapboxClient(settings=settings(), client=http_client)
    results = await client.compute_route_matrix(
        25.0,
        121.0,
        [{"lat": 25.1, "lng": 121.1}, {"lat": 25.2, "lng": 121.2}],
    )

    assert results == [
        {"destination_index": 0, "distance_meters": 500, "duration_seconds": 300},
        {"destination_index": 1, "distance_meters": 200, "duration_seconds": 120},
    ]
