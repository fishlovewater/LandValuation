"""Explicit development-only exceptions for external review demonstrations."""
from app.core.config import get_settings
from app.review.completeness import CompletenessResult

ADVISORY_ITEM_CODES = {"DOC_LAND_REGISTER", "DOC_CADASTRAL_MAP", "FIELD_PARCEL_AREA"}


def allow_missing_materials(case_type, *, submitted=False):
    settings = get_settings()
    return (
        settings.app_env == "development"
        and settings.demo_review_allow_missing_materials
        and case_type == "EXTERNAL_REVIEW"
        and not submitted
    )


def advisory_completeness(result):
    # Source identity and rule effective date remain mandatory. Missing vendor
    # attachments/area stay visible and retain their blocked-rule metadata.
    return CompletenessResult(
        ready=all(item.item_code in ADVISORY_ITEM_CODES for item in result.items),
        items=result.items,
        blocked_rule_codes=result.blocked_rule_codes,
    )
