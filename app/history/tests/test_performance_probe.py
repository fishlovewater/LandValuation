import pytest

from app.history import performance_probe


def test_performance_probe_case_count_bounds():
    assert performance_probe._validate_case_count(100) == 100
    assert performance_probe._validate_case_count(100_000) == 100_000

    with pytest.raises(ValueError, match="at least 100"):
        performance_probe._validate_case_count(99)
    with pytest.raises(ValueError, match="must not exceed 100000"):
        performance_probe._validate_case_count(100_001)


@pytest.mark.asyncio
async def test_performance_probe_refuses_production_before_opening_database(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    database_calls = []
    monkeypatch.setattr(
        performance_probe,
        "_database_runtime",
        lambda: database_calls.append("database"),
    )

    with pytest.raises(RuntimeError, match="DEVELOPMENT_ONLY"):
        await performance_probe.run_probe(100)

    assert database_calls == []
