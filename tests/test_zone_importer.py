import json
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from app.valuation.locations.zone_importer import import_zones_from_geojson

@pytest.fixture
def sample_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "price_zone_no": "A-123",
                    "area_sqm": 1500.5
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0,0], [1,0], [1,1], [0,1], [0,0]]]
                }
            }
        ]
    }

@patch('app.valuation.locations.zone_importer.json.load')
@patch('app.valuation.locations.zone_importer.open', create=True)
def test_import_zones_from_geojson(mock_open, mock_json_load, sample_geojson):
    mock_json_load.return_value = sample_geojson
    mock_session = MagicMock()
    
    # Simulate DB where record does not exist
    mock_query = mock_session.execute.return_value
    mock_query.first.return_value = None
    
    result = import_zones_from_geojson(mock_session, "dummy_path.geojson")
    
    assert result == {"inserted": 1, "updated": 0, "skipped": 0}
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    
    # verify the added record
    added_record = mock_session.add.call_args[0][0]
    assert added_record.price_zone_no == "A-123"
    assert added_record.area_sqm == Decimal("1500.5")
