# Task 2 report: trusted extraction and rule applicability schema

## Scope

Implemented the task-2 schema contract in:

- `migrations/versions/20260825_0007_add_trusted_review_inputs.py`
- `app/review/tests/test_schema_contract.py`

No application services, API, Vue, Alembic configuration, or existing migrations were changed.

## Preflight

Command:

```powershell
rtk docker compose --env-file .env.example exec -T db psql -U app_user -d land_valuation -Atc "SELECT count(*) FROM valuation.rule_versions WHERE status = 'PUBLISHED'"
```

Result: `0`. No published rule version was changed.

## TDD evidence

### RED

After adding `test_trusted_input_schema_contract`, the first API test invocation used a stale image and could not find the new test. The API image was rebuilt and recreated; the same test then failed for the intended reason:

```text
FAILED app/review/tests/test_schema_contract.py::test_trusted_input_schema_contract
AssertionError: TRUSTED_INPUT_COLUMNS <= actual
```

The missing members included `valuation.extraction_runs`, `valuation.extracted_fields`, and the three new rule applicability columns.

### GREEN

After migration 0007 was applied to the main development database:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_schema_contract.py -q
```

Result:

```text
3 passed in 0.06s
```

## Migration validation

The exact isolated database was retained: `land_valuation_migration_test_0007`.

1. `rtk docker compose --env-file .env.example build migrate` — exit 0.
2. `rtk docker compose --env-file .env.example exec -T db createdb -U app_user land_valuation_migration_test_0007` — exit 0.
3. Initial isolated `alembic upgrade head` — failed before correction with `DuplicateColumn: source_document_id`.
4. The failure was transactional: querying that database for `alembic_version` returned `relation "alembic_version" does not exist`, confirming that no partial migration schema remained.
5. After the correction, rebuilt migrate image — exit 0.
6. Isolated `alembic upgrade head` — exit 0; reached `20260825_0007`.
7. Isolated `alembic downgrade 20260825_0006` — exit 0.
8. Isolated `alembic upgrade head` — exit 0; reached `20260825_0007` again.
9. Main `alembic upgrade head` — exit 0.
10. Main revision query returned `20260825_0007`.

## Required baseline compatibility correction

The task brief described `source_document_id` and `fk_rule_versions_source_document` as new additions. Read-only inspection showed both already exist in the 0006 baseline, introduced by migration 0004; the source-document index also already exists. Attempting to add them caused the initial isolated migration failure.

Migration 0007 therefore preserves those 0004-owned objects and adds only:

- `applicable_case_type`, `applicable_district_code`, `selection_priority`
- `ck_rule_versions_selection_priority`, `ck_rule_versions_published_source`
- `idx_rule_versions_selection`

Its downgrade removes only these 0007-owned objects, while retaining the prior `source_document_id`, foreign key, and index. The resulting database still fulfills the requested trusted-input column contract.

## Self-review

- Upgrade creates both extraction tables, their foreign keys, constraints, unique constraints, and indexes specified for 0007.
- Upgrade enforces the published-rule source guard before DDL.
- Downgrade order is dependency-safe: rule selection index and new rule additions, extracted-fields index/table, extraction-runs index/table.
- `source_document_id` baseline ownership is preserved in both directions.
- Main database revision and all schema contract tests were verified after the final migration.

## Concerns

- The isolated validation database intentionally remains for Task 8 cleanup.
- The initial stale API image produced a test-discovery error; it was not accepted as RED. The rebuilt-image RED failure and final GREEN result are recorded above.
