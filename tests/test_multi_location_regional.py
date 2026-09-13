from app.valuation.report_packages.multi_location_regional import (
    RULE_VERSION,
    calculate_multi_location_regional_adjustments,
    level_for_value,
)


def test_residential_field_rules_resolve_unambiguous_values_only():
    assert RULE_VERSION == "NTPC_RESIDENTIAL_TABLE_5_1_V1"
    assert level_for_value("building_coverage_rate", "50%") == "L4"
    assert level_for_value("floor_area_ratio", "260%") == "L3"
    assert level_for_value("land_use_zone", "第一種住宅區") == "L2"
    assert level_for_value("road_plan", "道路狀況良好") is None


def test_multi_location_calculation_uses_confirmed_values_and_keeps_unknown_blank():
    result = calculate_multi_location_regional_adjustments([
        {
            "location_id": "benchmark",
            "is_benchmark_location": True,
            "values": {
                "building_coverage_rate": "50%",
                "floor_area_ratio": "200%",
                "land_use_zone": "第一種住宅區",
            },
        },
        {
            "location_id": "comparison-1",
            "is_benchmark_location": False,
            "values": {
                "building_coverage_rate": "50%",
                "floor_area_ratio": "260%",
                "land_use_zone": "第一種住宅區",
                "road_plan": "道路狀況良好",
            },
        },
    ])

    target = result["comparison-1"]
    assert target["factor_adjustment_rates"] == {
        "building_coverage_rate": "0.000000",
        "floor_area_ratio": "-0.062500",
        "land_use_zone": "0.000000",
    }
    assert "road_plan" not in target["factor_adjustment_rates"]
    assert target["regional_adjustment_rate"] == "-0.062500"
