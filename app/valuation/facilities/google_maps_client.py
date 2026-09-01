import httpx
import logging
from typing import Any
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class GoogleMapsClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or (
            settings.google_maps_api_key.get_secret_value()
            if settings.google_maps_api_key
            else None
        )
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_API_KEY is not set. Google Maps API calls will fail.")
        
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def geocode(self, address: str) -> dict[str, float] | None:
        """
        Geocode an address to latitude and longitude.
        Returns:
            {"lat": float, "lng": float} or None if not found or failed.
        """
        if not self.api_key:
            return None

        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": self.api_key,
            "language": "zh-TW"
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                return {"lat": location["lat"], "lng": location["lng"]}
        except Exception as e:
            logger.error(f"Geocoding failed for {address}: {e}")
        return None

    async def search_nearby_places(self, lat: float, lng: float, place_type: str, radius: int = 2000, max_results: int = 5) -> list[dict[str, Any]]:
        """
        Search for nearby places of a specific type within a radius (in meters).
        Uses Places API (New) if possible, or standard Places API.
        We will use standard Places API Nearby Search for simplicity, returning up to max_results candidates.
        """
        if not self.api_key:
            return []

        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat},{lng}",
            "radius": radius,
            "type": place_type,
            "key": self.api_key,
            "language": "zh-TW"
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            candidates = []
            if data.get("status") in ("OK", "ZERO_RESULTS"):
                results = data.get("results", [])[:max_results]
                for place in results:
                    candidates.append({
                        "name": place.get("name"),
                        "place_id": place.get("place_id"),
                        "lat": place["geometry"]["location"]["lat"],
                        "lng": place["geometry"]["location"]["lng"]
                    })
            else:
                logger.error(f"Places API failed: {data.get('status')} - {data.get('error_message')}")
            return candidates
        except Exception as e:
            logger.error(f"Nearby search failed for type {place_type} at {lat},{lng}: {e}")
        return []

    async def compute_route_matrix(self, origin_lat: float, origin_lng: float, destinations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Compute walking route distance and duration from one origin to multiple destinations.
        Using Distance Matrix API.
        """
        if not self.api_key or not destinations:
            return []

        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        
        origin_str = f"{origin_lat},{origin_lng}"
        dest_strs = [f"{dest['lat']},{dest['lng']}" for dest in destinations]
        
        params = {
            "origins": origin_str,
            "destinations": "|".join(dest_strs),
            "mode": "walking",
            "key": self.api_key,
            "language": "zh-TW"
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "OK":
                elements = data["rows"][0]["elements"]
                results = []
                for idx, element in enumerate(elements):
                    if element.get("status") == "OK":
                        distance_meters = element["distance"]["value"]
                        duration_seconds = element["duration"]["value"]
                        results.append({
                            "destination_index": idx,
                            "distance_meters": distance_meters,
                            "duration_seconds": duration_seconds
                        })
                    else:
                        logger.warning(f"Route to destination {idx} failed: {element.get('status')}")
                return results
            else:
                logger.error(f"Distance Matrix API failed: {data.get('status')} - {data.get('error_message')}")
        except Exception as e:
            logger.error(f"Route matrix computation failed: {e}")
        return []
