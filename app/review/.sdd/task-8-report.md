# Task 8 Report: Trusted Input Migration Record and Verification

## Scope

- Updated `app/review/OUTSIDE_REVIEW_CHANGES.md` with item 7 for the sole approved external change: `migrations/versions/20260825_0007_add_trusted_review_inputs.py`.
- Corrected design and plan wording: `source_document_id`, `fk_rule_versions_source_document`, and `idx_rule_versions_source_document` were created by migration `20260824_0004`; migration `0007` preserves that ownership and adds extraction schema, applicability/priority fields, and the published-source constraint.

## Fresh verification

- Rebuilt and recreated the API service before testing.
- `rtk docker compose --env-file .env.example exec -T api pytest tests app/review/tests -q`: `141 passed, 1 skipped, 1 warning in 5.72s`.
- The only warning is the existing Starlette TestClient/httpx deprecation warning.
- `rtk git diff --check`: exit 0 with no output.
- Main database `alembic_version`: `20260825_0007`.
- API, PostgreSQL, and MinIO all reported `healthy` from `docker compose ps`.
- `rtk git diff --name-status 5f81a0f` showed every changed path under `app/review/**` except the approved `migrations/versions/20260825_0007_add_trusted_review_inputs.py`.

## Isolated migration database cleanup

- Exact preflight query returned one row, exactly `land_valuation_migration_test_0007`.
- Removed only that database using `dropdb -U app_user land_valuation_migration_test_0007`.
- Post-cleanup exact-name count query returned `0`.

## Remaining process

- Documentation commit: `547a8ba docs(review): record trusted input migration` (three `app/review` files only; no push).
- This task does not claim overall completion: independent final code review is still required.
