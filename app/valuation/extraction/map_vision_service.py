import json
import logging
import re
from typing import Any
from urllib.parse import quote

import boto3
import httpx

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)


class MapVisionService:
    """Resolve an extracted area with AWS Location and inspect a Mapbox image."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        location_client: Any | None = None,
        bedrock_client: Any | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.location_client = location_client
        self.bedrock_runtime = bedrock_client
        self.http_client = http_client or httpx.Client(
            timeout=self.settings.mapbox_timeout_seconds
        )
        self._owns_http_client = http_client is None

        if self.location_client is None or self.bedrock_runtime is None:
            session = boto3.Session(
                profile_name=self.settings.aws_profile or None,
                region_name=self.settings.aws_location_region
                or self.settings.bedrock_region,
            )
            if self.location_client is None:
                self.location_client = session.client(
                    "location",
                    region_name=self.settings.aws_location_region,
                )
            if self.bedrock_runtime is None:
                self.bedrock_runtime = session.client(
                    "bedrock-runtime",
                    region_name=self.settings.bedrock_region,
                )

        self.place_index_name = self.settings.aws_location_place_index_name

    def close(self) -> None:
        if self._owns_http_client:
            self.http_client.close()

    def geocode_location(self, address: str) -> dict[str, Any] | None:
        """Resolve the OCR/AI area description with AWS Location Place Index."""
        if not self.place_index_name:
            logger.warning("AWS_LOCATION_PLACE_INDEX_NAME is not configured")
            return None
        try:
            response = self.location_client.search_place_index_for_text(
                IndexName=self.place_index_name,
                Text=address,
                Language=self.settings.aws_location_language,
                MaxResults=5,
            )
            results = response.get("Results") or []
            if not results:
                logger.info("AWS Location found no result for extracted area: %s", address)
                return None
            result = results[0]
            place = result.get("Place") or {}
            point = place.get("Geometry", {}).get("Point")
            if not point or len(point) != 2:
                return None
            return {
                "longitude": float(point[0]),
                "latitude": float(point[1]),
                "label": place.get("Label"),
                "place_id": result.get("PlaceId"),
                "relevance": result.get("Relevance"),
                "query": address,
            }
        except Exception:
            logger.exception("AWS Location place lookup failed")
            return None

    def capture_map_image(
        self,
        lat: float,
        lng: float,
        zoom: int | None = None,
    ) -> bytes | None:
        """Download a marked Mapbox Static Images image for the resolved point."""
        token = (
            self.settings.mapbox_access_token.get_secret_value()
            if self.settings.mapbox_access_token
            else None
        )
        username = self.settings.mapbox_username
        style_id = self.settings.mapbox_style_id
        if not token or not username or not style_id:
            logger.warning("Mapbox image configuration is incomplete; map image skipped")
            return None

        requested_zoom = zoom or self.settings.mapbox_static_zoom
        marker = f"pin-s+f97316({lng:.7f},{lat:.7f})"
        url = (
            "https://api.mapbox.com/styles/v1/"
            f"{quote(username, safe='')}/{quote(style_id, safe='')}/static/"
            f"{marker}/{lng:.7f},{lat:.7f},{requested_zoom}/"
            f"{self.settings.mapbox_image_width}x{self.settings.mapbox_image_height}"
        )
        try:
            response = self.http_client.get(url, params={"access_token": token})
            response.raise_for_status()
            return response.content
        except Exception:
            logger.exception("Mapbox static map request failed")
            return None

    def analyze_map_with_vision_ai(
        self,
        image_bytes: bytes,
        prompt_text: str,
    ) -> list[dict[str, Any]]:
        """Ask Bedrock for grounded observations from the map image."""
        if not self.settings.bedrock_model_id:
            logger.warning("BEDROCK_MODEL_ID is not configured; map analysis skipped")
            return []
        try:
            response = self.bedrock_runtime.converse(
                modelId=self.settings.bedrock_model_id,
                system=[
                    {
                        "text": (
                            "只可回報地圖影像中明確可見的資訊。"
                            "找不到或無法確認的欄位必須省略。"
                            "請只輸出 JSON："
                            '{"candidates":[{"field_name":"...",'
                            '"extracted_value":"...","confidence":0.0,'
                            '"source_text":"..."}]}'
                        )
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": {
                                    "format": "jpeg",
                                    "source": {"bytes": image_bytes},
                                }
                            },
                            {"text": prompt_text},
                        ],
                    }
                ],
                inferenceConfig={
                    "maxTokens": self.settings.bedrock_max_tokens,
                    "temperature": self.settings.bedrock_temperature,
                },
            )
            blocks = response.get("output", {}).get("message", {}).get("content", [])
            output_text = "\n".join(
                str(block["text"]) for block in blocks if block.get("text")
            )
            match = re.search(r"\{.*\}", output_text, flags=re.DOTALL)
            if not match:
                return []
            payload = json.loads(match.group(0))
            candidates = payload.get("candidates", [])
            return candidates if isinstance(candidates, list) else []
        except Exception:
            logger.exception("Bedrock map vision analysis failed")
            return []
