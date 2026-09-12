"""Development-only performance probe for Case-history search.

Run inside the API runtime with, for example::

    python -m app.history.performance_probe --cases 10000

The probe inserts synthetic cases inside one transaction, measures the real
``HistoryRepository.search`` query, and always rolls the transaction back.
No performance-probe rows should remain in the database after the command.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from time import perf_counter

from sqlalchemy import text

from app.history.demo import _database_runtime, _ensure_development
from app.history.permissions import HistoryScope
from app.history.repository import HistoryRepository
from app.history.schemas import HistorySearchParams


@dataclass(frozen=True)
class ProbeResult:
    name: str
    elapsed_ms: float
    total: int
    rows: int


def _validate_case_count(value: int) -> int:
    if value < 100:
        raise ValueError("case count must be at least 100")
    if value > 100_000:
        raise ValueError("case count must not exceed 100000")
    return value


async def run_probe(case_count: int = 10_000) -> list[ProbeResult]:
    _ensure_development()
    case_count = _validate_case_count(case_count)
    deep_offset = min(max(0, case_count - 2_000), 8_000)
    exact_number = max(1, case_count - 1)
    exact_case_no = f"PERF-HIST-{exact_number:05d}"
    exact_title = f"效能測試 {exact_number}"

    _, sessions = _database_runtime()
    async with sessions() as session:
        transaction = await session.begin()
        try:
            await session.execute(
                text(
                    "CREATE TEMP TABLE perf_history_cases "
                    "(case_id uuid PRIMARY KEY, n int NOT NULL) ON COMMIT DROP"
                )
            )
            await session.execute(
                text(
                    "INSERT INTO perf_history_cases "
                    "SELECT gen_random_uuid(), gs FROM generate_series(1, :case_count) gs"
                ),
                {"case_count": case_count},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO valuation.cases
                        (case_id, case_no, case_title, case_type, valuation_base_date,
                         city_code, district_code, case_status, updated_at)
                    SELECT case_id,
                           'PERF-HIST-' || lpad(n::text, 5, '0'),
                           '案件歷史效能測試 ' || n,
                           'LAND', DATE '2026-08-01', '65000000', '65000010',
                           'COMPLETED',
                           TIMESTAMPTZ '2026-09-01 00:00:00+08'
                             - (n * INTERVAL '1 second')
                    FROM perf_history_cases
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO valuation.form_instances
                        (form_instance_id, case_id, form_code, version_no, form_status)
                    SELECT gen_random_uuid(), case_id, 'F03', 1, 'FINAL'
                    FROM perf_history_cases
                    """
                )
            )

            repository = HistoryRepository(session)
            scope = HistoryScope(valuation=True, review=True)
            probes = [
                (
                    "first-page",
                    HistorySearchParams(city_code="65000000", limit=20, offset=0),
                ),
                (
                    "deep-page",
                    HistorySearchParams(
                        city_code="65000000",
                        limit=20,
                        offset=deep_offset,
                    ),
                ),
                (
                    "exact-case-no",
                    HistorySearchParams(
                        keyword=exact_case_no,
                        city_code="65000000",
                        limit=20,
                        offset=0,
                    ),
                ),
                (
                    "title-contains",
                    HistorySearchParams(
                        keyword=exact_title,
                        city_code="65000000",
                        limit=20,
                        offset=0,
                    ),
                ),
            ]

            results: list[ProbeResult] = []
            for name, params in probes:
                started = perf_counter()
                rows, total = await repository.search(params, scope)
                elapsed_ms = (perf_counter() - started) * 1000
                results.append(
                    ProbeResult(
                        name=name,
                        elapsed_ms=round(elapsed_ms, 1),
                        total=total,
                        rows=len(rows),
                    )
                )
            return results
        finally:
            await transaction.rollback()


async def _main(case_count: int, output_json: bool) -> None:
    results = await run_probe(case_count)
    if output_json:
        print(json.dumps([asdict(result) for result in results], ensure_ascii=False))
        return

    print(f"History performance probe: synthetic_cases={case_count}")
    for result in results:
        print(
            f"{result.name:14} {result.elapsed_ms:8.1f} ms "
            f"total={result.total} rows={result.rows}"
        )
    print("Synthetic rows rolled back; database state was not persisted.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Development-only History search performance probe")
    parser.add_argument("--cases", type=int, default=10_000, help="synthetic case count (100..100000)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    try:
        _validate_case_count(args.cases)
    except ValueError as exc:
        parser.error(str(exc))

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main(args.cases, args.json))


if __name__ == "__main__":
    main()
