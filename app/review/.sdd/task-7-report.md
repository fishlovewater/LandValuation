# Task 7 Report: Trusted Workflow History

## Delivered

- Rebuilt the fixed-case workflow around server-owned empty `{}` run and rerun commands.
- The E2E fixture now creates completed original v1/v2 extraction runs, distinct verified official field IDs, an approved published knowledge source, an applicable published F01 rule version, and active adjustment/grade rules.
- It proves run 1 keeps v1 snapshot/evidence IDs after revision, run 2 uses v2 IDs, and each new finding supersedes the corresponding prior finding.
- Stored finding evidence now includes `verification_status`; report API and pure report tests preserve the stored evidence shape.
- The missing-items recheck fixture now supplies the complete trusted context while preserving its original assertion that historical missing items become `RESOLVED` rather than being deleted.

## Production corrections

- Finding identity is now `rule_version_id:validation_rule_id`, not an extracted-field ID.  The field ID remains in immutable snapshots and evidence, while reruns can match the same rule across document versions.
- Completed runs now clamp `completed_at` to at least `started_at`.  A full-suite run exposed the old race between DB-default `started_at` and app-clock `completed_at`, which could violate `ck_validation_runs_times`.

## TDD evidence

- RED: old E2E fixture failed because a published rule version lacked a source document; the rewritten E2E then failed exactly because v2 findings had `supersedes_finding_id = null`.
- GREEN: scoped workflow/report/missing-item/rerun suite: `14 passed, 1 warning`.
- Fresh full review suite: `124 passed, 1 warning` (existing Starlette TestClient/httpx deprecation).

## Review follow-up

- RED: a requested run report included other-run and case decisions; a legacy
  `rule_code:extracted_field_id` finding did not supersede on the first
  server-owned rerun.
- Fixed report construction to retain only decisions whose `finding_id` belongs
  to the requested run. Case decisions remain unassigned without a migration,
  so they are intentionally excluded from run-scoped reports.
- Fixed rerun matching through the existing
  `review.findings.source_validation_finding_id -> valuation.validation_findings.validation_rule_id`
  relation. It reads only the directly previous run and leaves duplicate rule
  links unmatched (fail closed).
- Added report API coverage for run 1/run 2/case decisions, legacy finding-code
  coverage, and explicit stored run-1/run-2 snapshot endpoint assertions.
- GREEN: scoped suite `16 passed, 1 warning`; fresh full review suite
  `126 passed, 1 warning` (existing Starlette TestClient/httpx deprecation).

## Commit

Committed locally (not pushed): `95fe853 fix(review): keep historical reports run scoped`.

## Third review follow-up: rerun history serialization

### Inherited RED record

- The prior review package (`review-task-7-r2.diff`) identified the uncorrected
  behavior: rerun read `latest_validation_run_id` before locking the review, and
  the rule-link query was scoped only by run ID.  That permits stale history and
  cross-review link lookup under concurrent requests.
- This follow-up inherited the in-progress production and test changes after the
  original implementer was interrupted.  They were preserved rather than
  reverted.  The new focused tests exercise the reported failure modes: a
  cross-review query returns no rows, duplicate rule links omit supersession,
  and two reruns serialize their history reads as `[run1, run2]`.

### Implemented correction

- `rerun()` takes the review row with `FOR UPDATE` before reading
  `latest_validation_run_id`; the request-scoped session holds that lock until
  the route completes and commits.
- `create_run()` accepts the already-locked row only for rerun.  The ordinary
  create-run route continues to acquire its own `FOR UPDATE` lock.
- `list_finding_rule_links(review_id, validation_run_id)` joins
  `ValidationRun` and filters both finding and run ownership by review ID.  The
  SQLAlchemy UUID comparisons remain bound parameters.
- Duplicate links for one validation rule are deliberately removed from the
  supersession map, so rerun fails closed instead of picking an arbitrary prior
  finding.

### Verification

- Focused rerun/repository suite: `12 passed, 1 warning`.
- Task 7 scoped workflow/report/missing-items/rerun/repository suite:
  `62 passed, 1 warning`.
- Fresh full review suite: `129 passed, 1 warning`.
- The only warning is the existing Starlette `TestClient` / httpx deprecation.
