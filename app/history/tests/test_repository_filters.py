from app.history.permissions import HistoryScope
from app.history.repository import HistoryRepository
from app.history.schemas import HistorySearchParams


def test_new_taipei_filters_match_legacy_and_official_codes() -> None:
    repository = HistoryRepository(None)  # type: ignore[arg-type]
    filters, values = repository._filters(
        HistorySearchParams(city_code="65000000", district_code="65000010"),
        HistoryScope(valuation=True, review=False),
    )

    sql = " AND ".join(filters)
    assert "city_code_alias_1" in sql
    assert "city_code_alias_3" in sql
    assert "district_code_alias" in sql
    assert values["city_code"] == "31"
    assert values["city_code_alias_2"] == "65000000"
    assert values["city_code_alias_3"] == "NWT"
    assert values["district_code"] == "65000010"
    assert values["district_code_alias"] == "3101"


def test_legacy_district_filter_matches_official_code() -> None:
    repository = HistoryRepository(None)  # type: ignore[arg-type]
    _, values = repository._filters(
        HistorySearchParams(city_code="31", district_code="3104"),
        HistoryScope(valuation=True, review=False),
    )

    assert values["district_code"] == "3104"
    assert values["district_code_alias"] == "65000030"


def test_persistent_demo_city_code_is_treated_as_new_taipei_alias() -> None:
    repository = HistoryRepository(None)  # type: ignore[arg-type]
    filters, values = repository._filters(
        HistorySearchParams(city_code="NWT"),
        HistoryScope(valuation=True, review=True),
    )

    assert "city_code_alias_3" in " AND ".join(filters)
    assert values["city_code_alias_3"] == "NWT"