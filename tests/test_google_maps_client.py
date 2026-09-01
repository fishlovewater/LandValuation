import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.valuation.facilities.google_maps_client import GoogleMapsClient

@pytest.mark.asyncio
async def test_geocode():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [{"geometry": {"location": {"lat": 25.0, "lng": 121.0}}}]
        }
        mock_get.return_value = mock_response
        
        client = GoogleMapsClient(api_key="dummy_key")
        result = await client.geocode("Test Address")
        
        assert result == {"lat": 25.0, "lng": 121.0}
        mock_get.assert_called_once()
        await client.close()

@pytest.mark.asyncio
async def test_search_nearby_places():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {"name": "Place 1", "place_id": "id1", "geometry": {"location": {"lat": 25.1, "lng": 121.1}}},
                {"name": "Place 2", "place_id": "id2", "geometry": {"location": {"lat": 25.2, "lng": 121.2}}}
            ]
        }
        mock_get.return_value = mock_response
        
        client = GoogleMapsClient(api_key="dummy_key")
        results = await client.search_nearby_places(25.0, 121.0, "park")
        
        assert len(results) == 2
        assert results[0]["name"] == "Place 1"
        await client.close()

@pytest.mark.asyncio
async def test_compute_route_matrix():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "OK",
            "rows": [{
                "elements": [
                    {"status": "OK", "distance": {"value": 500}, "duration": {"value": 300}},
                    {"status": "OK", "distance": {"value": 200}, "duration": {"value": 120}}
                ]
            }]
        }
        mock_get.return_value = mock_response
        
        client = GoogleMapsClient(api_key="dummy_key")
        destinations = [{"lat": 25.1, "lng": 121.1}, {"lat": 25.2, "lng": 121.2}]
        results = await client.compute_route_matrix(25.0, 121.0, destinations)
        
        assert len(results) == 2
        assert results[0]["distance_meters"] == 500
        assert results[1]["distance_meters"] == 200
        await client.close()
