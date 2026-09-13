from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.core.exceptions import AppError

from .mapbox_client import MapboxClient
from .schemas import NearestFacilityRequest


class FacilityService:
    SEARCH_RADIUS_M = 2000
    MAX_CANDIDATES = 5

    def __init__(self, client: MapboxClient | None = None) -> None:
        self.client = client or MapboxClient()
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()

    async def find_nearest_facility(
        self,
        request: NearestFacilityRequest,
        *,
        resolved_lat: Decimal | None = None,
        resolved_lng: Decimal | None = None,
    ) -> dict[str, Any] | None:
        """Return a walking-distance candidate; never mark it user-confirmed."""
        if not self.client.configured:
            raise AppError(
                "MAP_PROVIDER_NOT_CONFIGURED",
                "尚未設定 MAPBOX_ACCESS_TOKEN，無法執行外部步行距離查詢",
                503,
            )

        origin_lat = resolved_lat if resolved_lat is not None else request.origin_lat
        origin_lng = resolved_lng if resolved_lng is not None else request.origin_lng
        if origin_lat is None or origin_lng is None:
            if request.origin_address is None:
                raise AppError(
                    "FACILITY_ORIGIN_UNRESOLVED",
                    "案件內起點沒有座標，請補充地址或經緯度",
                    422,
                )
            geocoded = await self.client.geocode(request.origin_address)
            if not geocoded:
                return None
            origin_lat = Decimal(str(geocoded["lat"]))
            origin_lng = Decimal(str(geocoded["lng"]))

        candidates = await self.client.search_nearby_places(
            lat=float(origin_lat),
            lng=float(origin_lng),
            place_type=request.facility_type,
            radius=self.SEARCH_RADIUS_M,
            max_results=self.MAX_CANDIDATES,
        )
        if not candidates:
            return None

        routes = await self.client.compute_route_matrix(
            origin_lat=float(origin_lat),
            origin_lng=float(origin_lng),
            destinations=candidates,
        )
        valid_routes = [
            route
            for route in routes
            if 0 <= int(route["destination_index"]) < len(candidates)
            and int(route["distance_meters"]) >= 0
        ]
        if not valid_routes:
            return None

        best_route = min(valid_routes, key=lambda item: int(item["distance_meters"]))
        best_candidate = candidates[int(best_route["destination_index"])]
        return {
            "facility_type": request.facility_type,
            "facility_name": best_candidate["name"],
            "distance_type": "WALKING",
            "walking_distance_m": Decimal(str(best_route["distance_meters"])),
            "walking_duration_seconds": int(best_route["duration_seconds"]),
            "origin_type": request.origin_type,
            "origin_reference_id": request.origin_reference_id,
            "origin_latitude": origin_lat,
            "origin_longitude": origin_lng,
            "destination_latitude": Decimal(str(best_candidate["lat"])),
            "destination_longitude": Decimal(str(best_candidate["lng"])),
            "destination_place_id": best_candidate.get("place_id"),
            "provider": "MAPBOX",
            "route_method": "MAPBOX_DIRECTIONS_WALKING",
            "route_reference": None,
            "search_radius_m": self.SEARCH_RADIUS_M,
            "candidate_count": len(candidates),
            "measured_at": datetime.now(timezone.utc),
            "confirmed_by_user": False,
        }
