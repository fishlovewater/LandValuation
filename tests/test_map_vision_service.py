from unittest.mock import MagicMock

from app.core.config import Settings
from app.valuation.extraction.map_vision_service import MapVisionService


def settings() -> Settings:
    return Settings(
        _env_file=None,
        aws_location_region="ap-northeast-1",
        aws_location_place_index_name="test-place-index",
        bedrock_region="us-east-1",
        bedrock_model_id="test-model",
        mapbox_access_token="test-token",
        mapbox_username="test-user",
        mapbox_style_id="test-style",
    )


def test_aws_location_geocode() -> None:
    location = MagicMock()
    location.search_place_index_for_text.return_value = {
        "Results": [
            {
                "PlaceId": "place-1",
                "Relevance": 0.98,
                "Place": {
                    "Label": "台北市信義區信義段",
                    "Geometry": {"Point": [121.5654, 25.0330]},
                },
            }
        ]
    }
    service = MapVisionService(
        settings(),
        location_client=location,
        bedrock_client=MagicMock(),
        http_client=MagicMock(),
    )

    result = service.geocode_location("台北市信義區信義段")

    assert result["longitude"] == 121.5654
    assert result["latitude"] == 25.0330
    assert result["place_id"] == "place-1"
    location.search_place_index_for_text.assert_called_once_with(
        IndexName="test-place-index",
        Text="台北市信義區信義段",
        Language="zh-TW",
        MaxResults=5,
    )


def test_mapbox_static_image() -> None:
    http_client = MagicMock()
    response = MagicMock()
    response.content = b"map-image"
    http_client.get.return_value = response
    service = MapVisionService(
        settings(),
        location_client=MagicMock(),
        bedrock_client=MagicMock(),
        http_client=http_client,
    )

    result = service.capture_map_image(25.0330, 121.5654)

    assert result == b"map-image"
    response.raise_for_status.assert_called_once()
    request_url = http_client.get.call_args.args[0]
    assert "api.mapbox.com/styles/v1/test-user/test-style/static/" in request_url
    assert "pin-s+f97316" in request_url


def test_bedrock_map_vision_returns_json_candidates() -> None:
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": (
                            '{"candidates":[{"field_name":"terrain",'
                            '"extracted_value":"平坦","confidence":0.9,'
                            '"source_text":"地圖顯示平坦區域"}]}'
                        )
                    }
                ]
            }
        }
    }
    service = MapVisionService(
        settings(),
        location_client=MagicMock(),
        bedrock_client=bedrock,
        http_client=MagicMock(),
    )

    candidates = service.analyze_map_with_vision_ai(b"image", "return JSON")

    assert candidates[0]["field_name"] == "terrain"
    assert candidates[0]["extracted_value"] == "平坦"
