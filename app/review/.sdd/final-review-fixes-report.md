# Final Review Fixes Report

## Scope

- Modified only `app/review/**` plus the user-approved
  `migrations/versions/20260825_0007_add_trusted_review_inputs.py`.
- Did not create another migration or change any other external path.

## Root causes fixed

- Rule-source lookup ignored the case valuation-base date.
- Validation-run snapshots omitted immutable trust, source, rule, and report
  context, while historical reports read mutable review status/counts.
- Machine validation findings stored `field_path` in `field_code`.
- Case decisions had no run association, so they could not be included safely in
  a historical run report.
- Migration `0007` rejected every published rule, including rules already
  linked to a valid knowledge source.

## TDD evidence

- RED after a rebuilt API image: `8 failed, 58 passed, 1 warning`.
  The failures covered snapshot completeness, both invalid source-date bounds
  in run and completeness flows, field-code persistence, case-decision report
  association, and the migration preflight contract.
- GREEN focused suite:
  `71 passed, 1 warning` for runs, completeness, reports, trusted input policy,
  and repository queries.
- Fresh full suite:
  `151 passed, 1 skipped, 1 warning` from
  `pytest tests app/review/tests -q`.
  The only warning is the existing Starlette TestClient/httpx deprecation.

## Migration verification

- Main database revision: `20260825_0007`.
- Exact isolated database `land_valuation_migration_test_0007` was absent,
  created, migrated to `0006`, and seeded with one legal `PUBLISHED` rule that
  already has `source_document_id`.
- `upgrade head -> downgrade 20260825_0006 -> upgrade head` all succeeded.
- After downgrade, `source_document_id` was confirmed present on
  `valuation.rule_versions`.
- The isolated database was preflighted by exact name, dropped, then postchecked
  with count `0`.

## Commit

- Pending local commit: `fix(review): preserve trusted audit context`.

## Final re-review follow-up: every official field snapshot

- Root cause: `field_snapshots` was derived from `prepared_rules`; official
  fields not targeted by a selected rule were omitted, and a shared target would
  duplicate the same field in audit data.
- `TrustedRunContext` now carries the complete, repository-ordered official
  field tuple separately from the duplicate-fail-closed execution mapping.
  Snapshot serialization keeps each `extracted_field_id` once, including
  verification, confidence, and source-location metadata.
- RED: the real run fixture omitted an unrelated official field; a pure context
  fixture proved shared prepared targets needed one audit record. The database
  prevents duplicate rule codes in one version, so the shared-target case is
  represented safely with two distinct in-memory validation rule IDs.
- GREEN focused suite: `54 passed, 1 warning` for runs, workflow history, and
  reports.
- Fresh full suite after rebuild: `152 passed, 1 skipped, 1 warning`.
- Repeated migration verification: the exact isolated database was absent,
  created, migrated to `0006`, seeded with a valid source-linked `PUBLISHED`
  rule, upgraded to `0007`, downgraded to `0006`, and upgraded to head. After
  downgrade the 0004 column, foreign key, and index checks were `1|1|1`; the
  exact test database was then dropped and postchecked at `0`.
- Main database remained at `20260825_0007`; API, PostgreSQL, and MinIO were
  healthy.

## Follow-up commit

- Pending local commit: `fix(review): snapshot every official field`.

## Final re-review follow-up: decimal-safe snapshots

- RED: a database-backed extracted-field `confidence` set to
  `Decimal('0.987654')` caused `validation_runs.input_snapshot` JSONB
  persistence to fail with `TypeError: Object of type Decimal is not JSON
  serializable`.
- The shared snapshot serializer now recursively serializes `Decimal` as its
  exact string form, rather than a float. Field confidence, normalized values,
  bounding boxes, rule configurations, and source-evidence bounding boxes use
  that common serializer.
- GREEN focused suite: `55 passed, 1 warning` for Decimal regression, runs,
  workflow history, and reports. Both API response and stored JSONB preserved
  confidence as `"0.987654"`.
- Fresh full suite: `153 passed, 1 skipped, 1 warning`.
- Main database remained at `20260825_0007`; API, PostgreSQL, and MinIO were
  healthy.

## Decimal follow-up commit

- Pending local commit: `fix(review): serialize snapshot decimals`.

## 2026-08-27 synchronous response maintenance

### Scope

- Modified and tracked only `app/review/**`.
- Preserved root `pytest.ini` unchanged at the user's request so separately developed subsystems retain independent test collection.
- Did not add a worker queue or alter run execution, persistence, findings, decisions, snapshots, or reports.

### Root cause and contract

- Both run endpoints awaited all service work and returned a `COMPLETED` `ValidationRunRead` in the same request, while their decorators advertised `202 Accepted`.
- The approved contract keeps execution synchronous and reports successful completion as `200 OK`.

### TDD evidence

- RED: after changing only successful API assertions, focused tests produced `10 failed, 54 passed`; each executed failure showed expected `200` and actual `202`.
- The first GREEN attempt exposed four parameterized source-date success cases that still encoded `202`; a complete search confirmed those were the only remaining HTTP-contract values.
- GREEN: run, rerun, and fixed-case workflow tests produced `64 passed, 1 warning`.
- Fresh full Review suite: `141 passed, 1 warning`.
- The remaining warning is the pre-existing Starlette TestClient/httpx deprecation.

### Records

- Design: `app/review/docs/2026-08-27-review-maintenance-design.md`, commit `f0c923f`.
- Plan: `app/review/docs/2026-08-27-review-maintenance-plan.md`.
- User-facing history: `app/review/CHANGELOG.md`.
- Implementation commit message: `fix(review): align synchronous run responses`.
- Historical `.sdd/*.diff` attachments preserve their original patch text, including historical whitespace. The submission gate applies `git diff --cached --check` to live code, current tests, and current maintenance Markdown rather than rewriting archived evidence.
