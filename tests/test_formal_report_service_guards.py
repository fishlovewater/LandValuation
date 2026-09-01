from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.valuation.report_packages.formal_service import FormalReportService
from app.valuation.rule_packs.coverage import NEW_TAIPEI_CITYWIDE_SCOPE


def _case(**overrides):
    values = {
        "valuation_base_date": date(2026, 8, 28),
        "district_code": "65000010",
        "land_use_type": "COMMERCIAL",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rule(**overrides):
    values = {
        "status": "PUBLISHED",
        "import_status": "VERIFIED",
        "verified_at": datetime.now(UTC),
        "source_document_id": uuid4(),
        "source_checksum_sha256": "a" * 64,
        "formula_code": "NTPC_COMPARISON_V1",
        "rounding_code": "NTPC_LAND_PRICE_V1",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "land_use_types": ["COMMERCIAL"],
        "district_scope": dict(NEW_TAIPEI_CITYWIDE_SCOPE),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_formal_rule_guard_accepts_verified_citywide_commercial_rule():
    assert FormalReportService._validate_rule(_case(), _rule()) == "COMMERCIAL"


@pytest.mark.parametrize(
    ("case", "rule", "expected_code"),
    [
        (
            _case(land_use_type="RESIDENTIAL"),
            _rule(land_use_types=["RESIDENTIAL"]),
            "FORMAL_REPORT_TEMPLATE_LAND_USE_UNSUPPORTED",
        ),
        (
            _case(),
            _rule(district_scope={"mode": "INCLUDE", "district_codes": ["65000010"]}),
            "FORMAL_RULE_SCOPE_NOT_CITYWIDE",
        ),
        (
            _case(),
            _rule(status="RETIRED"),
            "FORMAL_RULE_AUDIT_FAILED",
        ),
    ],
)
def test_formal_rule_guard_rejects_unsafe_rule_or_template(case, rule, expected_code):
    with pytest.raises(AppError) as exc_info:
        FormalReportService._validate_rule(case, rule)
    assert exc_info.value.code == expected_code
