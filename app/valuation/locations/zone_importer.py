import json
from decimal import Decimal
import logging
from typing import TextIO

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.valuation.models import LandValueZoneRecord

logger = logging.getLogger(__name__)

def import_zones_from_geojson(session: Session, file_obj: TextIO, city_code: str | None = None, district_code: str | None = None) -> int:
    """
    Imports standard Land Value Section GeoJSON data into the database.
    Expects properties to contain 'price_zone_no' or 'ZONE_NO' and 'area_sqm' or 'SHAPE_Area'.
    """
    try:
        data = json.load(file_obj)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid GeoJSON file: {e}")
        return 0

    if data.get("type") != "FeatureCollection":
        logger.error("GeoJSON must be a FeatureCollection")
        return 0

    features = data.get("features", [])
    count = 0

    for feature in features:
        props = feature.get("properties", {})
        geometry = feature.get("geometry")

        # Find price_zone_no
        zone_no = props.get("price_zone_no") or props.get("ZONE_NO") or props.get("zone_no")
        if not zone_no:
            continue

        # Find area
        area = props.get("area_sqm") or props.get("SHAPE_Area") or props.get("Shape_Area") or props.get("area")
        
        area_dec = None
        if area is not None:
            try:
                area_dec = Decimal(str(area))
            except Exception:
                pass

        # Check if exists
        existing = session.scalars(
            select(LandValueZoneRecord)
            .where(LandValueZoneRecord.price_zone_no == str(zone_no))
        ).first()

        if existing:
            existing.geometry_geojson = geometry
            if area_dec is not None:
                existing.area_sqm = area_dec
            if city_code:
                existing.city_code = city_code
            if district_code:
                existing.district_code = district_code
        else:
            new_record = LandValueZoneRecord(
                price_zone_no=str(zone_no),
                area_sqm=area_dec,
                geometry_geojson=geometry,
                city_code=city_code,
                district_code=district_code
            )
            session.add(new_record)
        count += 1

    session.commit()
    logger.info(f"Imported/Updated {count} land value zones.")
    return count
