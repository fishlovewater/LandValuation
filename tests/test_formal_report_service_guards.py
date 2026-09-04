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


@pytest.mark.asyncio
async def test_formal_validation_locks_case_before_reading_writable_records():
    calls = []

    class _Pages:
        async def _read_records(self, case_id, report_id, user, *, for_update=False):
            calls.append(for_update)
            raise RuntimeError("stop after lock probe")

    service = FormalReportService(
        None,
        pages=_Pages(),
        repository=SimpleNamespace(),
    )

    with pytest.raises(RuntimeError, match="stop after lock probe"):
        await service.validate(uuid4(), uuid4(), SimpleNamespace(), None)

    assert calls == [True]


@pytest.mark.asyncio
async def test_formal_validation_rechecks_request_after_case_lock():
    calls = []
    case_id = uuid4()
    report_id = uuid4()
    request_id = uuid4()
    existing = SimpleNamespace(
        validation_run_id=uuid4(),
        case_id=case_id,
        passed_count=12,
        warning_count=0,
        failed_count=0,
        completed_at=datetime.now(UTC),
        ruleset_snapshot={},
    )

    class _Repository:
        def __init__(self):
            self.lookup_count = 0

        async def validation_for_request(self, case, report, request):
            calls.append("request_lookup")
            self.lookup_count += 1
            return None if self.lookup_count == 1 else existing

    class _Pages:
        async def _read_records(self, case, report, user, *, for_update=False):
            calls.append(("case_lock", for_update))
            return SimpleNamespace(), {}

    repository = _Repository()
    service = FormalReportService(None, pages=_Pages(), repository=repository)
    response = await service.validate(case_id, report_id, SimpleNamespace(), request_id)

    assert response.validation_run_id == existing.validation_run_id
    assert calls == [
        "request_lookup",
        ("case_lock", True),
        "request_lookup",
    ]
