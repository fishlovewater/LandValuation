import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from app.valuation.locations.zone_service import ZoneService
from app.valuation.models import LandValueZoneRecord

@pytest.fixture
def mock_session():
    session = MagicMock()
    return session

def test_get_zone_area_success(mock_session):
    # Setup
    zone_svc = ZoneService(mock_session)
    mock_record = LandValueZoneRecord(
        price_zone_no="100-01",
        area_sqm=Decimal("5000.55")
    )
    
    mock_query = mock_session.scalars.return_value
    mock_query.first.return_value = mock_record
    
    # Execute
    result = zone_svc.get_zone_area("100-01")
    
    # Assert
    assert result == Decimal("5000.55")

def test_get_zone_area_not_found(mock_session):
    # Setup
    zone_svc = ZoneService(mock_session)
    
    mock_query = mock_session.scalars.return_value
    mock_query.first.return_value = None
    
    # Execute
    result = zone_svc.get_zone_area("NONEXISTENT")
    
    # Assert
    assert result is None

def test_get_zone_area_empty_input(mock_session):
    zone_svc = ZoneService(mock_session)
    assert zone_svc.get_zone_area("") is None
    assert zone_svc.get_zone_area(None) is None
