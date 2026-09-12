from dataclasses import dataclass


@dataclass(frozen=True)
class FormRequirementDefinition:
    form_code: str
    form_name: str
    required_fields: tuple[str, ...]
    required_documents: tuple[str, ...]
    optional_documents: tuple[str, ...]
    calculated_fields: tuple[str, ...]


# These definitions are limited to fields already required by the reviewed
# database schema and the F03 example explicitly stated in the backend guide.
FORM_REQUIREMENTS: dict[str, FormRequirementDefinition] = {
    "S01": FormRequirementDefinition(
        form_code="S01",
        form_name="地價區段勘查表",
        required_fields=(
            "administrative_area",
            "valuation_base_date",
            "price_zone_no",
            "zone_boundary_description",
            "urban_plan_scope",
            "land_use_zone_category",
            "main_road_name",
            "main_road_width_m",
            "survey_date",
        ),
        required_documents=(),
        optional_documents=("photos", "attachments"),
        calculated_fields=("average_internal_road_width_m",),
    ),
    "F01": FormRequirementDefinition(
        form_code="F01",
        form_name="買賣實例調查估價表",
        required_fields=(
            "transaction_no",
            "transaction_date",
            "transaction_total_price",
            "location",
            "land_area_sqm",
        ),
        required_documents=(),
        optional_documents=(),
        calculated_fields=("normal_land_unit_price",),
    ),
    "F02": FormRequirementDefinition(
        form_code="F02",
        form_name="比較法調查估價表",
        required_fields=(
            "parcel_id",
            "benchmark_land_no",
            "price_zone_no",
            "valuation_base_date",
        ),
        required_documents=(),
        optional_documents=(),
        calculated_fields=("benchmark_comparison_price",),
    ),
    "F02-RF": FormRequirementDefinition(
        form_code="F02-RF",
        form_name="影響地價區域因素分析明細表（商業用地）",
        required_fields=(
            "benchmark_land_id",
            "comparison_analysis_id",
            "comparison_targets",
            "confirmed_factor_levels",
            "rule_version_id",
        ),
        required_documents=(),
        optional_documents=("attachments",),
        calculated_fields=(
            "regional_adjustment_rate",
            "total_adjustment_rate",
        ),
    ),
    "F03": FormRequirementDefinition(
        form_code="F03",
        form_name="比準地地價估計表",
        required_fields=("valuation_base_date", "benchmark_land_id"),
        # These documents improve evidence quality when available, but are not mandatory for the report workflow.
        required_documents=(),
        optional_documents=("land-register", "cadastral-map", "photos", "attachments"),
        calculated_fields=(
            "adjusted_unit_price",
            "benchmark_land_price",
        ),
    ),
    "F04": FormRequirementDefinition(
        form_code="F04",
        form_name="徵收土地宗地市價估計表",
        required_fields=(
            "benchmark_valuation_id",
            "valuation_base_date",
            "price_zone_no",
        ),
        required_documents=(),
        optional_documents=(),
        calculated_fields=("parcel_unit_price",),
    ),
}
