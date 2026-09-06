# Integration Baseline Test Contract Repair Design

## Goal and scope

方案 A is a test-contract repair for the integration baseline at `bb8910d`.
Its purpose is to repair four baseline failures—three handoff integration
selectors and one MinIO round trip—so that the tests assert the behavior
already implemented by the production services, rather than introducing a
second contract in the test fixtures. The unit lock-order fake is a companion
contract-consistency repair and is not counted as a fourth baseline failure.

The repair is test and harness work only. It does not change production
Python code, the Valuation or Review schema, migrations, the
`origin/feature/valuation` branch, or any runtime status constraint. The
existing uncommitted drafts in
`tests/integration/test_valuation_review_handoff.py` and
`tests/test_submission_service.py` are implementation work from another
agent. During this documentation task they must not be edited, staged, or
committed. During a later implementation task, their intended changes may be
adopted only after the baseline RED evidence is preserved or rebuilt and the
smallest verified diff is reviewed; this design does not treat the drafts as
already-verified results.

The worktree's existing `.serena/` directory and
`app/review/MANUAL_INTEGRATION_TEST_GUIDE.md` remain untouched and
uncommitted.

## Current production contracts

The test repairs follow these existing boundaries:

1. `SubmissionService.submit()` builds a canonical immutable submission
   snapshot, computes its SHA-256 `input_fingerprint`, and persists both in
   `valuation.review_submissions`. On a new handoff it sets the Review row to
   `RECEIVED` and the Valuation case row to `IN_REVIEW`.
2. `CorrectionService.send()` transitions the Review row to
   `RETURNED_FOR_REVISION` and the Valuation case row to
   `REVISION_REQUIRED`. `IN_REVIEW` is a case status; it is not a valid
   Review correction status. The two columns must not be substituted for one
   another in test setup or assertions.
3. `ReviewRepository.get_submission_snapshot_record()` reads the persisted
   snapshot and fingerprint and can scope the lookup by `review_id` and
   `case_id`. Review tests must use this immutable handoff record when they
   verify what Review received, especially after changing live Valuation
   rows.
4. SQLAlchemy sessions expire ordinary ORM attributes after `commit()`. A
   test that needs an identifier after a commit or rollback must save the
   scalar UUID before the boundary and use that scalar in later service calls
   and queries.
5. `StorageService` uses `settings.minio_bucket` for every MinIO operation
   and returns that configured bucket in upload metadata. The integration
   harness deliberately supplies a run-scoped value such as
   `land-valuation-test-vr-debug000002`-shaped run value; it must not be replaced by the
   development bucket.

## Three handoff baseline failures and companion unit consistency repair

The three handoff baseline failures are the following test setup or
observation mistakes. The MinIO round trip is the fourth baseline failure and
is described in the next section. The unit fake below is a companion
contract-consistency repair, not a fourth handoff failure. The MinIO case is
normally skipped unless explicitly enabled, so it must not be counted as a
green test merely because the default run omitted it.

### 1. Fingerprint must come from the persistent submission snapshot

Affected test:
`tests/integration/test_valuation_review_handoff.py::test_appraiser_submission_handoff_is_reviewable_and_statuses_pair`.

The test currently has a committed `Submission` ORM object, then reads an
expired relationship attribute as if it were the authoritative Review input.
The repair loads `get_submission_snapshot_record()` with the submission,
Review, and case IDs, asserts that the record exists, and stores its
`input_fingerprint` as the original value. After live document or extracted
field rows are changed, the same scoped persistent record must still contain
the original fingerprint. This proves the snapshot boundary and avoids a
live-source fallback or a session-expiration artifact.

### 2. Revision/recheck integration setup must use Review's status

Affected test:
`tests/integration/test_valuation_review_handoff.py::test_two_sessions_serialize_revision_and_recheck_locks`.

The test's raw setup must write `review.reviews.review_status =
'RETURNED_FOR_REVISION'` before exercising a resubmission/recheck race. The
case row may separately be `REVISION_REQUIRED`. Writing `IN_REVIEW` to the
Review column is not a valid way to represent this state and can violate the
existing Review constraint or transition table. The repair changes only the
test's fixture state and keeps the lock-order scenario intact.

### 3. Preserve scalar correction IDs across commit boundaries

Affected test:
`tests/integration/test_valuation_review_handoff.py::test_revision_response_registration_rolls_back_submission_on_lineage_failure`.

The test must assign `draft.correction_request_id` to a local scalar before
`session.commit()`. It then uses that UUID for `corrections.send()` and for
the post-rollback query. This makes the test deterministic under normal
SQLAlchemy expiration and keeps its real assertion: an invalid response
lineage raises `CORRECTION_RESUBMISSION_INVALID`, the attempted submission
is rolled back, the correction request remains `SENT`, exactly one
submission remains, and the original persisted fingerprint is unchanged.

### Companion repair: match the unit fake to the same Review/case status split

This companion repair is not counted as a baseline failure.

Affected test:
`tests/test_submission_service.py::test_revision_and_recheck_sessions_follow_case_review_correction_lock_order`.

The fake Review object must start at `RETURNED_FOR_REVISION` while the fake
case remains in `REVISION_REQUIRED`. This mirrors the integration fixture and
lets the test exercise the existing correction/recheck and submission lock
order. It must not use case-only `IN_REVIEW` as a Review status merely to
reach the branch under test.

## 4. MinIO round-trip and harness observability

The MinIO round trip is the fourth baseline failure in this repair.

Affected test:
`tests/test_integration_storage.py::test_minio_upload_download_delete_round_trip`.

The upload result must be asserted against the configured run-scoped value,
for example `os.environ["MINIO_BUCKET"]` or the constructed service's
`bucket`, not the fixed development bucket `land-valuation`. The test still
performs the complete upload, download, byte comparison, and `finally`
cleanup in that same bucket. No fixed bucket or shared prefix is introduced.

The test currently has an explicit `RUN_INTEGRATION=1` guard. The preferred
harness repair is to add `RUN_INTEGRATION: "1"` to the integration test
service environment in `docker-compose.integration.yml`, because the
standard integration command should exercise the real MinIO round-trip and
should not report a skip as coverage. If the project intentionally retains
opt-in execution, the acceptance command must pass the variable explicitly
and report the skip as unexecuted coverage; the default path must not be
described as having verified MinIO.

The run-scoped database and bucket remain mandatory. The configuration
validator already permits `land-valuation-test-*` only in test mode, and the
MinIO initializer creates the exact value supplied by the harness. The
repair therefore verifies configuration propagation rather than weakening
the validator or changing the production default.

## Data flow

The repaired tests should make the following boundaries explicit:

```text
run-integration-tests.ps1
  -> TEST_RUN_ID / POSTGRES_DB / MINIO_BUCKET / APP_ENV=test
  -> docker-compose.integration.yml test container
  -> Settings and StorageService(settings.minio_bucket)
  -> isolated MinIO bucket and PostgreSQL database

handoff fixture
  -> Valuation source rows and MinIO document
  -> SubmissionService.submit()
  -> persisted review_submissions.input_snapshot + input_fingerprint
  -> ReviewRepository scoped snapshot read
  -> Workbench / ReviewService / CorrectionService
  -> Review status and case status assertions
```

The handoff test may mutate live Valuation rows only to prove that Review
continues to read the persisted snapshot. The mutation must not be used as a
new source for the expected fingerprint or document metadata. The rollback
test must query by the scalar IDs captured before commit, after explicitly
rolling back the failed transaction.

## Error handling and failure meaning

- A missing or ownership-mismatched snapshot record is a test failure. The
  test must fail closed; it must not fall back to current Valuation rows.
- A Review row containing `IN_REVIEW` in the correction/recheck setup is a
  fixture error, not a reason to broaden the Review constraint. The test
  should use the valid `RETURNED_FOR_REVISION` state and retain the separate
  case status.
- `CORRECTION_RESUBMISSION_INVALID` is the expected service error in the
  lineage-failure test. After catching it, the test rolls back before
  inspecting database state and verifies that no partial submission escaped.
- A MinIO bucket mismatch is a configuration/test failure. Upload, download,
  and delete must all address the configured run-scoped bucket, with cleanup
  in `finally` so a failed assertion does not leave the test object behind.
- A skipped MinIO test is not a pass. The harness must either set
  `RUN_INTEGRATION=1` or make the explicit opt-in command part of acceptance
  evidence.

## Alternatives considered

### A. Test-only contract alignment (selected)

Update the three stale handoff fixtures/observations, align the companion
unit fake, assert the configured MinIO bucket, and enable the guarded storage
test in the integration harness. This keeps production behavior and isolation
unchanged while making failures point to real contract regressions. It is the
smallest scope and matches the existing uncommitted draft intent.

### B. Broaden the Review constraint to accept `IN_REVIEW`

Rejected. `IN_REVIEW` belongs to the Valuation case lifecycle, while the
Review lifecycle already has `RECEIVED`, `PREPROCESSING`,
`RETURNED_FOR_REVISION`, and related states. Expanding the constraint would
hide a fixture error, blur the two state machines, require schema/migration
changes, and make the test less faithful to the running services.

### C. Force the production bucket or hardcode `land-valuation` in tests

Rejected. Replacing the configured bucket would defeat per-run isolation and
could mix objects between concurrent or interrupted test runs. A fixed
assertion would preserve the stale expectation rather than test the storage
configuration. The expected value must be the run-scoped environment value
created by the harness.

### D. Leave the MinIO test opt-in and skipped by the standard harness

Not selected as the default. It avoids a Compose edit but leaves a real
storage regression invisible to the normal integration command. It remains a
documented fallback only when a caller deliberately chooses opt-in coverage
and reports that choice.

## TDD and implementation sequence

The future implementation should follow this order. The documentation commit
contains this file alone. During the later implementation phase, preserve or
rebuild RED evidence before adopting any change from the existing drafts;
then verify each smallest diff independently. An implementation commit may
include the two intended test files and the harness change listed below, but
only after that evidence exists and never with unrelated edits:

1. Record the baseline against the target checkout as three failing handoff
   selectors plus the MinIO round trip—the four baseline failures in scope.
   Run the MinIO test explicitly once to expose its stale fixed-bucket
   assertion rather than relying on the default skip. Record the unit fake's
   result separately; it is a companion consistency check and is not counted
   among the four failures.
2. Repair the integration fixture observations: read the scoped persisted
   snapshot, use `RETURNED_FOR_REVISION`, and capture the correction UUID
   before commit.
3. Repair the unit fake's Review status to the same valid state.
4. Change the storage assertion to the configured bucket and make the
   standard integration test container set `RUN_INTEGRATION=1`.
5. Run the focused unit tests, then the isolated PostgreSQL/MinIO tests with
   a fresh run ID. Confirm the storage object is deleted and the run-scoped
   database and bucket are cleaned up.
6. Run the relevant full suite and inspect the diff. Only the intended test
   and harness changes may be included in the implementation commit; the
   design-only commit contains this file alone.

The red/green boundary is explicit: before the repair, the three handoff
selectors fail, and the explicitly enabled MinIO round trip exposes its
stale fixed-bucket expectation; the default guarded MinIO run may otherwise
skip. The companion unit fake may already pass because it does not enforce
the database constraint. After the repair, the four baseline contracts pass
while production source, schema, and migrations are unchanged.

## Acceptance criteria

The repair is accepted when all of the following are true:

- The four baseline contracts—the three handoff integration selectors and
  the MinIO round trip—pass against the existing production contract.
- The unit lock-order selector also passes after its companion
  fixture-consistency repair, but is not counted as a baseline failure.
- The handoff test obtains and rechecks the original fingerprint from the
  persisted, ownership-scoped submission snapshot after live-source mutation.
- The correction/recheck fixtures distinguish Review
  `RETURNED_FOR_REVISION` from case `IN_REVIEW` and `REVISION_REQUIRED`.
- The lineage-failure test survives commit and rollback boundaries using
  scalar IDs, observes `CORRECTION_RESUBMISSION_INVALID`, and proves that no
  extra submission was committed.
- The MinIO round-trip asserts the configured run-scoped bucket, performs
  upload/download/delete successfully, and is executed by the standard
  harness or explicitly reported as opt-in coverage.
- No production Python file, Valuation/Review schema, migration, or
  `origin/feature/valuation` file is changed.
- This documentation commit contains no test drafts, `.serena/`, or
  `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md`. In a later implementation
  commit, the two intended test files may be staged only after RED evidence
  is preserved or rebuilt and the resulting changes pass the focused tests;
  no unreviewed draft is treated as verified, and no unrelated edits are
  included.
- There are no unresolved placeholders, contradictory status meanings, or
  claims that a skipped test passed.

## Exact affected files

The implementation plan is limited to these files:

- `tests/integration/test_valuation_review_handoff.py` — three integration
  fixture/observation repairs described above.
- `tests/test_submission_service.py` — one unit fixture status repair.
- `tests/test_integration_storage.py` — configured run-scoped bucket
  assertion.
- `docker-compose.integration.yml` — add the existing test guard variable to
  the test service environment if the standard harness is chosen to execute
  the round-trip.

`scripts/run-integration-tests.ps1`, production application files, schema
models, migrations, and external Valuation branch files are not implementation
targets for this repair.
