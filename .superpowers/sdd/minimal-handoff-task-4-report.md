# Minimal handoff Task 4 report

## Scope

Review now executes from the immutable `Review.latest_submission_id` /
`valuation.review_submissions.input_snapshot` boundary. Submitted Review paths
validate the Snapshot and stored fingerprint, reject missing, malformed, or
cross-review/case pointers with `SUBMISSION_SNAPSHOT_INVALID` (409), and do not
fall back to live canonical fields. Legacy Reviews with a NULL pointer retain
the existing canonical-data fallback.

The product-facing workbench exposes safe submission provenance and, for a
submitted Review, builds its document list from the validated Snapshot instead
of live document/field-version queries. The raw Snapshot, bucket, and object
key remain excluded from the workbench response. Existing live version-diff
behavior remains available for legacy Reviews.

## TDD evidence

1. Added `test_submitted_workbench_detail_uses_snapshot_documents_after_live_change`.
2. RED command:

   ```powershell
   pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_workbench_api.py -k submitted_workbench_detail_uses_snapshot_documents_after_live_change"
   ```

   Result: the test failed as intended. The response included the newly added
   `post-submit` live document in addition to the submitted document.
3. GREEN focused command:

   ```powershell
   pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_workbench_api.py"
   ```

   Result: `17 passed in 4.15s`.

## Validation

Required Task 4 command:

```powershell
pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_submission_snapshot.py tests/test_submission_service.py app/review/tests/test_trusted_inputs.py app/review/tests/test_runs_api.py app/review/tests/test_workbench_api.py"
```

Result: `131 passed in 11.71s`, test container exit code `0`. The isolated
Docker Compose database, MinIO service, containers, and network were cleaned up
by the test script.

Additional checks:

```powershell
git diff --check
git diff --cached --check
```

Both checks passed before the follow-up commit. `rtk` was unavailable in this
Windows session, so the equivalent native PowerShell/Git commands were used.

## Commits

- `61d3b9f feat(review): execute against submitted snapshot`
- `7998b30 fix(review): enforce submitted snapshot boundary`

The second commit contains only the Task 4 implementation/test files. The
pre-existing untracked `.serena/` directory was not staged or modified. No
push, merge, branch cleanup, or changes to `feature/review` or
`origin/feature/valuation` were performed.

Browser acceptance was not claimed; this report records automated integration
verification only.

## Post-commit verification

The same required Task 4 command was rerun after `7998b30`:

- `131 passed in 12.07s`
- test container exit code `0`
- Compose database, MinIO, containers, and network removed successfully
- final `git diff --check` passed

## Follow-up Task 4 re-review fixes

The snapshot preflight boundary now validates a non-NULL
`Review.latest_submission_id` before any live completeness read, evaluates
submitted completeness from the trusted Snapshot boundary, scopes provenance
to both owning Review and case, and projects all Run provenance through one
bounded bulk query per workbench detail response.

### TDD evidence

1. Extended `test_submitted_preflight_uses_snapshot_after_live_field_is_invalidated`
   to invalidate live documents, parcels, and case number while retaining the
   submitted Snapshot, and added invalid-Snapshot and cross-owner provenance
   regressions.
2. RED command:

   ```powershell
   pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_workbench_api.py"
   ```

   Result: the three new/extended regressions failed as intended (`3 failed,
   16 passed in 8.20s`, test container exit code `1`).
3. GREEN focused command:

   ```powershell
   pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_workbench_api.py"
   ```

   Result: `19 passed in 4.55s`, test container exit code `0`.

### Validation

Required Task 4 selector:

```powershell
pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_submission_snapshot.py tests/test_submission_service.py app/review/tests/test_trusted_inputs.py app/review/tests/test_runs_api.py app/review/tests/test_workbench_api.py"
```

Result: `133 passed in 11.30s`, test container exit code `0`. The isolated
Docker Compose database, MinIO service, containers, and network were cleaned
up by the test script.

Additional checks:

```powershell
git diff --check
```

Passed before the follow-up commit. `rtk` was unavailable in this Windows
session, so equivalent native PowerShell/Git commands were used.

### Commit

- Commit message: `fix(review): close snapshot preflight gaps`.
- The pre-existing untracked `.serena/` directory was not staged or modified.

## Final Task 4 re-review fixes

The workbench latest-submission provenance join now requires both the owning
Review and its case. Run projections expose submission metadata only when the
ownership-scoped provenance map contains the Run's submission; an unverified
raw `ValidationRun.submission_id` is no longer returned.

### TDD evidence

1. Added a mismatched-case regression for
   `WorkbenchRepository.get_submission_provenance()` and extended the
   cross-review/cross-case Run regression to assert that all submission
   provenance fields, including `submission_id`, are `null` when ownership
   validation fails.
2. RED command:

   ```powershell
   pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_workbench_api.py"
   ```

   Result: the two new/extended regressions failed as intended (`2 failed,
   18 passed in 11.39s`, test container exit code `1`).
3. GREEN focused command:

   ```powershell
   pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_workbench_api.py"
   ```

   Result: `20 passed in 6.92s`, test container exit code `0`.

### Validation

Required Task 4 selector:

```powershell
pwsh -File .\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_submission_snapshot.py tests/test_submission_service.py app/review/tests/test_trusted_inputs.py app/review/tests/test_runs_api.py app/review/tests/test_workbench_api.py"
```

Result: `134 passed in 12.34s`, test container exit code `0`. The isolated
Docker Compose database, MinIO service, containers, and network were cleaned
up by the test script.

Additional checks:

```powershell
git diff --check
```

Passed before the follow-up commit. `rtk` was unavailable in this Windows
session, so equivalent native PowerShell/Git commands were used.

### Commit

- Commit message: `fix(review): scope workbench submission provenance`.
- The pre-existing untracked `.serena/` directory was not staged or modified.
