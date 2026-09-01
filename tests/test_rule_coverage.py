from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.valuation.rule_packs.coverage import (
    NEW_TAIPEI_DISTRICTS,
    expanded_district_codes,
    rules_overlap,
)
from app.valuation.rule_packs.coverage_service import RuleCoverageService


def rule(
    *,
    district_scope=None,
    land_use_types=None,
    effective_from=date(2026, 1, 1),
    effective_to=None,
):
    return SimpleNamespace(
        rule_version_id=uuid4(),
        rule_set_code="NTPC_FORMAL_RULE",
        version_no=1,
        version_name="新北市正式規則",
        jurisdiction_code="NEW_TAIPEI_CITY",
        status="PUBLISHED",
        effective_from=effective_from,
        effective_to=effective_to,
        district_scope=district_scope
        or {"mode": "INCLUDE", "district_codes": ["65000010"]},
        land_use_types=land_use_types or ["RESIDENTIAL"],
    )


class FakeRepository:
    def __init__(self, values):
        self.values = values

    async def list_effective_published(self, valuation_date):
        del valuation_date
        return self.values


def test_all_scope_expands_to_exactly_29_official_districts() -> None:
    assert len(NEW_TAIPEI_DISTRICTS) == 29
    assert expanded_district_codes({"mode": "ALL", "district_codes": []}) == set(
        NEW_TAIPEI_DISTRICTS
    )


def test_overlapping_scope_land_use_and_dates_are_detected() -> None:
    left = rule()
    right = rule(effective_from=date(2026, 6, 1))
    separate = rule(
        district_scope={"mode": "INCLUDE", "district_codes": ["65000270"]}
    )

    assert rules_overlap(left, right) is True
    assert rules_overlap(left, separate) is False


@pytest.mark.asyncio
async def test_coverage_requires_one_unique_formal_rule() -> None:
    value = rule()
    covered = await RuleCoverageService(FakeRepository([value])).check(
        district_code="65000010",
        land_use_type="RESIDENTIAL",
        valuation_date=date(2026, 8, 27),
    )
    assert covered.status == "COVERED"
    assert covered.covered is True

    missing = await RuleCoverageService(FakeRepository([])).check(
        district_code="65000010",
        land_use_type="RESIDENTIAL",
        valuation_date=date(2026, 8, 27),
    )
    assert missing.status == "MISSING"

    ambiguous = await RuleCoverageService(FakeRepository([value, rule()])).check(
        district_code="65000010",
        land_use_type="RESIDENTIAL",
        valuation_date=date(2026, 8, 27),
    )
    assert ambiguous.status == "AMBIGUOUS"


@pytest.mark.asyncio
async def test_missing_coverage_blocks_formal_calculation() -> None:
    service = RuleCoverageService(FakeRepository([]))

    with pytest.raises(AppError) as exc_info:
        await service.require(
            district_code="65000270",
            land_use_type="COMMERCIAL",
            valuation_date=date(2026, 8, 27),
        )

    assert exc_info.value.code == "RULE_COVERAGE_MISSING"


@pytest.mark.asyncio
async def test_matrix_contains_29_districts_times_five_land_uses() -> None:
    matrix = await RuleCoverageService(FakeRepository([])).matrix(
        date(2026, 8, 27)
    )

    assert matrix.total_combinations == 145
    assert matrix.covered_count == 0
    assert matrix.missing_count == 145
    assert matrix.ambiguous_count == 0

