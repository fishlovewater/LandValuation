from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.valuation.models import LandValueZoneRecord

class ZoneService:
    def __init__(self, session: Session):
        self.session = session

    def get_zone_area(self, price_zone_no: str) -> Optional[Decimal]:
        """
        Look up the area_sqm for a given price_zone_no from the database.
        Returns the Decimal area in square meters if found, else None.
        """
        if not price_zone_no:
            return None

        record = self.session.scalars(
            select(LandValueZoneRecord)
            .where(LandValueZoneRecord.price_zone_no == str(price_zone_no))
            .where(LandValueZoneRecord.is_active.is_(True))
        ).first()

        if record and record.area_sqm is not None:
            return record.area_sqm
        return None
