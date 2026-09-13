import httpx
import logging
from typing import Any
from urllib.parse import quote

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)


class MapboxClient:
    """Mapbox geocoding, nearby search and walking route adapter."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.access_token = (
            self.settings.mapbox_access_token.get_secret_value()
            if self.settings.mapbox_access_token
            else None
        )
        self.client = client or httpx.AsyncClient(
            timeout=self.settings.mapbox_timeout_seconds
        )
        self._owns_client = client is None

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def geocode(self, address: str) -> dict[str, float] | None:
        if not self.configured:
            return None
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(address)}.json"
        try:
            response = await self.client.get(
                url,
                params={
                    "access_token": self.access_token,
                    "language": "zh-TW",
                    "limit": 1,
                    "country": "tw",
                },
            )
            response.raise_for_status()
            features = response.json().get("features") or []
            if not features:
                return None
            longitude, latitude = features[0]["center"]
            return {"lat": float(latitude), "lng": float(longitude)}
        except Exception:
            logger.exception("Mapbox geocoding failed")
            return None

    async def search_nearby_places(
        self,
        lat: float,
        lng: float,
        place_type: str,
        radius: int = 2000,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        del radius
        if not self.configured:
            return []
        query = place_type.replace("_", " ")
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(query)}.json"
        try:
            response = await self.client.get(
                url,
                params={
                    "access_token": self.access_token,
                    "language": "zh-TW",
                    "limit": max_results,
                    "types": "poi",
                    "proximity": f"{lng},{lat}",
                    "country": "tw",
                },
            )
            response.raise_for_status()
            candidates = []
            for feature in (response.json().get("features") or [])[:max_results]:
                center = feature.get("center")
                if not center or len(center) != 2:
                    continue
                candidates.append(
                    {
                        "name": feature.get("text") or feature.get("place_name"),
                        "place_id": feature.get("id"),
                        "lat": center[1],
                        "lng": center[0],
                    }
                )
            return candidates
        except Exception:
            logger.exception("Mapbox nearby search failed")
            return []

    async def compute_route_matrix(
        self,
        origin_lat: float,
        origin_lng: float,
        destinations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self.configured or not destinations:
            return []
        results: list[dict[str, Any]] = []
        for index, destination in enumerate(destinations):
            url = (
                "https://api.mapbox.com/directions/v5/mapbox/walking/"
                f"{origin_lng},{origin_lat};{destination['lng']},{destination['lat']}"
            )
            try:
                response = await self.client.get(
                    url,
                    params={
                        "access_token": self.access_token,
                        "overview": "false",
                        "steps": "false",
                        "alternatives": "false",
                    },
                )
                response.raise_for_status()
                routes = response.json().get("routes") or []
                if not routes:
                    continue
                route = routes[0]
                results.append(
                    {
                        "destination_index": index,
                        "distance_meters": round(float(route.get("distance", 0))),
                        "duration_seconds": round(float(route.get("duration", 0))),
                    }
                )
            except Exception:
                logger.exception("Mapbox walking route failed for destination %s", index)
        return results
