from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.valuation.report_packages.page_schemas import (
    DraftSourceType,
    F02RFFactorDraft,
    F02RFTargetLevelDraft,
    S01Observation,
)


def test_s01_walking_distance_requires_verifiable_confirmation() -> None:
    with pytest.raises(ValidationError):
        S01Observation(
            item_code="parking_convenience",
            facility_name="QA PARKING",
            walking_distance_m="120",
            distance_type="WALKING",
            origin_type="BENCHMARK_LAND_ENTRANCE",
        )

    accepted = S01Observation(
        item_code="parking_convenience",
        facility_name="QA PARKING",
        walking_distance_m="120",
        distance_type="WALKING",
        origin_type="BENCHMARK_LAND_ENTRANCE",
        source_type="MANUAL_CONFIRMED",
        source_notes="QA ROUTE SCREENSHOT",
        confirmed_by_user=True,
    )
    assert accepted.distance_type == "WALKING"


def test_s01_route_provider_candidate_requires_full_provenance() -> None:
    with pytest.raises(ValidationError):
        S01Observation(
            item_code="parking_convenience",
            facility_name="QA PARKING",
            walking_distance_m="120",
            walking_duration_seconds=80,
            distance_type="WALKING",
            origin_type="BENCHMARK_LAND_ENTRANCE",
            source_type=DraftSourceType.ROUTE_PROVIDER_CONFIRMED,
            source_notes="USER CONFIRMED ROUTE RESULT",
            confirmed_by_user=True,
        )

    accepted = S01Observation(
        item_code="parking_convenience",
        facility_name="QA PARKING",
        walking_distance_m="120",
        walking_duration_seconds=80,
        distance_type="WALKING",
        origin_type="BENCHMARK_LAND_ENTRANCE",
        origin_reference_id=uuid4(),
        origin_latitude="25.0",
        origin_longitude="121.0",
        destination_latitude="25.1",
        destination_longitude="121.1",
        destination_place_id="qa-place",
        route_provider="GOOGLE_MAPS",
        route_method="DISTANCE_MATRIX_WALKING",
        search_radius_m=2000,
        candidate_count=5,
        source_type=DraftSourceType.ROUTE_PROVIDER_CONFIRMED,
        source_notes="USER CONFIRMED ROUTE RESULT",
        confirmed_by_user=True,
    )
    assert accepted.route_method == "DISTANCE_MATRIX_WALKING"


def test_s01_rejects_factor_not_in_supplied_template() -> None:
    with pytest.raises(ValidationError):
        S01Observation(item_code="invented_factor")


def test_f02_rf_confirmed_level_requires_manual_evidence() -> None:
    with pytest.raises(ValidationError):
        F02RFFactorDraft(
            factor_code="urban_plan_status",
            benchmark_confirmed_level="QA LEVEL",
        )

    with pytest.raises(ValidationError):
        F02RFFactorDraft(
            factor_code="urban_plan_status",
            targets=[
                F02RFTargetLevelDraft(
                    comparison_target_id=uuid4(),
                    display_order=1,
                    confirmed_level="QA LEVEL",
                )
            ],
        )
