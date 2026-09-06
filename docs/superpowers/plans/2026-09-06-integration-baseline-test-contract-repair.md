# Integration Baseline Test Contract Repair Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Valuation-to-Review integration test contracts and MinIO integration harness so the tests assert the existing production behavior and preserve run-scoped storage isolation.

**Architecture:** Keep this change at the test and harness boundary. The handoff tests will read the ownership-scoped persisted submission snapshot, keep Review and Valuation case status machines distinct, and retain scalar IDs across SQLAlchemy transaction boundaries. The storage test will compare the service result with the configured run-scoped bucket, while Compose will enable its existing integration guard.

**Tech Stack:** Python 3, pytest and pytest-asyncio, SQLAlchemy async sessions, psycopg, MinIO, Docker Compose, and PowerShell.

## Global Constraints

- Modify only the four test/harness files named in this plan; do not change production Python, schema models, migrations, or external Valuation branch files.
- The four baseline failures in this repair are exactly the three handoff integration selectors and the MinIO round trip; the unit fake change is a companion contract-consistency repair and is not counted as a fourth baseline failure.
- Preserve the existing uncommitted drafts before restoring the two draft files, and never stage or commit the draft patch itself.
- Use Review status `RETURNED_FOR_REVISION` and Valuation case status `REVISION_REQUIRED` for correction/recheck fixtures; `IN_REVIEW` is the case lifecycle value.
- Read the original fingerprint from `ReviewRepository.get_submission_snapshot_record()` with `submission_id`, `review_id`, and `case_id`; do not fall back to live Valuation rows.
- Use a scalar correction request UUID after a `commit()` or `rollback()`; do not dereference an expired ORM attribute across those boundaries.
- Keep `MINIO_BUCKET` run-scoped and configured by the integration harness; never assert or force the development bucket `land-valuation` in the integration test.
- Keep the default non-integration run honest: a skipped MinIO test is reported as skipped coverage, not as a passing round trip.
- Every implementation task ends with a focused test run, a diff-scope check, and a commit containing only that task's intended files.
- If a host Python or virtual environment cannot import project dependencies such as FastAPI, treat that as an environment collection error and rerun the same Python selector or suite with `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "..."`; do not classify the host import error as a product result.
- Do not modify `.serena/` or `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md`; these existing untracked items remain outside this repair.

## File Map

- `tests/integration/test_valuation_review_handoff.py`: three fixture/observation repairs for the persisted fingerprint, Review correction status, and scalar correction ID.
- `tests/test_submission_service.py`: one unit fake repair for the Review/case status split.
- `tests/test_integration_storage.py`: replace the fixed bucket assertion with the configured service bucket assertion while retaining upload, download, byte comparison, and `finally` deletion.
- `docker-compose.integration.yml`: pass `RUN_INTEGRATION: "1"` to the integration test service so the standard run executes the guarded MinIO test.
- Not implementation targets: `scripts/run-integration-tests.ps1`, production `app/` code, `database/`, `migrations/`, `origin/feature/valuation`, `.serena/`, and the untracked manual guide.

### Task 1: Align Valuation-to-Review handoff fixtures with production contracts

**Files:**

- Modify: `tests/integration/test_valuation_review_handoff.py` at `test_appraiser_submission_handoff_is_reviewable_and_statuses_pair`, `test_two_sessions_serialize_revision_and_recheck_locks`, and `test_revision_response_registration_rolls_back_submission_on_lineage_failure`.
- Modify: `tests/test_submission_service.py` at `test_revision_and_recheck_sessions_follow_case_review_correction_lock_order`.
- Test: the three named integration selectors and the named companion unit selector below; only the three handoff selectors are required RED evidence before repair.

**Interfaces:**

- Consumes: `ReviewRepository.get_submission_snapshot_record(submission_id, review_id=..., case_id=...)`, returning a persisted snapshot record or `None`; `SubmissionService.submit()`; and `CorrectionService.send()`.
- Produces: a fingerprint assertion sourced from the immutable handoff record, a valid Review correction status, and a correction request UUID that remains usable after session expiration and rollback.

- [ ] **Step 1: Preserve the existing drafts before creating RED evidence**

Run these commands from the target worktree. The first command writes the two modified test files to a temp patch outside the repository; verify it exists before restoring the files to HEAD.

~~~powershell
$patchPath = Join-Path ([System.IO.Path]::GetTempPath()) "integration-baseline-test-drafts.patch"
git diff --output="$patchPath" -- tests/integration/test_valuation_review_handoff.py tests/test_submission_service.py
Test-Path $patchPath
git restore --source=HEAD -- tests/integration/test_valuation_review_handoff.py tests/test_submission_service.py
~~~

Expected: `Test-Path` prints `True`; the two files are restored to the current HEAD, and the existing `.serena/` and `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md` remain untracked. Do not apply the saved draft wholesale; use the approved minimal snippets in Step 3.

- [ ] **Step 2: Run the targeted RED evidence and record the companion unit result**

Run the three integration selectors through the isolated Compose harness. Run the companion unit selector directly when the host environment has project dependencies installed:

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_valuation_review_handoff.py::test_appraiser_submission_handoff_is_reviewable_and_statuses_pair tests/integration/test_valuation_review_handoff.py::test_two_sessions_serialize_revision_and_recheck_locks tests/integration/test_valuation_review_handoff.py::test_revision_response_registration_rolls_back_submission_on_lineage_failure"
python -m pytest -q tests/test_submission_service.py::test_revision_and_recheck_sessions_follow_case_review_correction_lock_order
~~~

If the direct unit command fails before collection or test execution because the host Python or virtual environment lacks FastAPI or another project dependency, rerun that same selector in the dependency-complete isolated harness:

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/test_submission_service.py::test_revision_and_recheck_sessions_follow_case_review_correction_lock_order"
~~~

Expected: the integration command exits non-zero with failures in the three selected handoff cases, which are the RED evidence for the three stale handoff contracts. Record the companion unit selector's actual result independently: it may already pass because the fake status change is a consistency repair, and a pass must not be reported as a RED failure. If it fails, record its concrete assertion. The output should identify the stale live-ORM fingerprint observation, the invalid Review `IN_REVIEW` fixture, and the expired `draft.correction_request_id` access. The Compose script must still run its `finally` cleanup and leave no integration containers or volumes.

- [ ] **Step 3: Apply the smallest approved test-only repairs with apply_patch**

In `tests/integration/test_valuation_review_handoff.py`, replace the live ORM fingerprint observation immediately after `return_case = handoff_data.cases[1]` with the scoped persisted snapshot read:

~~~python
return_snapshot_record = await ReviewRepository(
    session
).get_submission_snapshot_record(
    return_submission.submission_id,
    review_id=return_submission.review_id,
    case_id=return_case.case_id,
)
assert return_snapshot_record is not None
original_return_fingerprint = return_snapshot_record["input_fingerprint"]
~~~

In the raw correction/recheck setup in the same file, change only the Review column's value and retain the separate case update:

~~~python
admin_cursor.execute(
    "UPDATE valuation.cases SET case_status = 'REVISION_REQUIRED' "
    "WHERE case_id = %s",
    (case.case_id,),
)
admin_cursor.execute(
    "UPDATE review.reviews SET review_status = 'RETURNED_FOR_REVISION' "
    "WHERE review_id = %s",
    (first.review_id,),
)
~~~

In `test_revision_response_registration_rolls_back_submission_on_lineage_failure`, capture the scalar before the first commit and use it for both post-boundary operations:

~~~python
draft_request_id = draft.correction_request_id
await session.commit()
await corrections.send(draft_request_id, reviewer.user_id, uuid4())
await session.commit()
~~~

Use that same `draft_request_id` in the post-rollback status query:

~~~python
).one()
status_row = (
    await session.execute(
        text(
            "SELECT c.case_status, r.status "
            "FROM valuation.cases c "
            "JOIN review.reviews rv ON rv.case_id = c.case_id "
            "JOIN review.correction_requests r "
            "  ON r.review_id = rv.review_id "
            "WHERE c.case_id = :case_id "
            "  AND r.correction_request_id = :request_id"
        ),
        {"case_id": case.case_id, "request_id": draft_request_id},
    )
).one()
~~~

In `tests/test_submission_service.py`, keep `prepare_newer_revision()` setting `state.case.case_status = "REVISION_REQUIRED"` and set only the fake Review status as follows:

~~~python
review = state.review
review.review_status = "RETURNED_FOR_REVISION"
~~~

Use `apply_patch` for these exact replacements. Do not touch production service code, model constraints, migration files, or any other test.

- [ ] **Step 4: Run the focused GREEN tests**

~~~powershell
python -m pytest -q tests/test_submission_service.py::test_revision_and_recheck_sessions_follow_case_review_correction_lock_order
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_valuation_review_handoff.py::test_appraiser_submission_handoff_is_reviewable_and_statuses_pair tests/integration/test_valuation_review_handoff.py::test_two_sessions_serialize_revision_and_recheck_locks tests/integration/test_valuation_review_handoff.py::test_revision_response_registration_rolls_back_submission_on_lineage_failure"
~~~

If the direct unit command has a host dependency collection error, use the same isolated fallback from Step 2. Expected: the companion unit selector and all three handoff selectors pass, the isolated integration run exits zero, and its run-scoped containers and volumes are removed. The handoff test obtains and rechecks the original fingerprint from the same ownership-scoped persisted snapshot after live Valuation rows are mutated; the lineage test reports `CORRECTION_RESUBMISSION_INVALID`, rolls back, observes one submission, `("REVISION_REQUIRED", "SENT")`, and the unchanged fingerprint.

- [ ] **Step 5: Review and commit only Task 1**

~~~powershell
git diff --check -- tests/integration/test_valuation_review_handoff.py tests/test_submission_service.py
git diff --name-only -- tests/integration/test_valuation_review_handoff.py tests/test_submission_service.py
git status --short
git add -- tests/integration/test_valuation_review_handoff.py tests/test_submission_service.py
git commit -m "test: align valuation review handoff contracts"
~~~

Expected: `git diff --check` is silent; the staged name list contains exactly the two Task 1 files; the commit does not include `.serena/`, the manual guide, the saved patch, or any production/schema/migration path. Leave the saved temp patch available until the implementation is reviewed.

### Task 2: Exercise the run-scoped MinIO round trip in the standard harness

**Files:**

- Modify: `tests/test_integration_storage.py` at `test_minio_upload_download_delete_round_trip`.
- Modify: `docker-compose.integration.yml` at the `test.environment` block.
- Test: the storage selector with the default local guard and with the isolated Compose harness.

**Interfaces:**

- Consumes: `StorageService.bucket`, which is populated from `get_settings().minio_bucket`, and the existing `MINIO_BUCKET` environment value supplied by `scripts/run-integration-tests.ps1`.
- Produces: an assertion that the upload metadata names the configured run-scoped bucket while the existing upload/download/byte-comparison/delete path remains intact.

- [ ] **Step 1: Record the default guard behavior before enabling the harness**

Run without `RUN_INTEGRATION`:

~~~powershell
Remove-Item Env:RUN_INTEGRATION -ErrorAction SilentlyContinue
python -m pytest -q tests/test_integration_storage.py::test_minio_upload_download_delete_round_trip
~~~

Expected: pytest exits zero only because the selector is skipped, and reports `1 skipped` with the reason `Set RUN_INTEGRATION=1 to test the configured MinIO instance`. Record this as unexecuted storage coverage, not as a passing round trip.

If the host command fails before collection because the host Python or virtual environment lacks project dependencies, run the same selector through the dependency-complete harness before the Compose environment is changed in Step 2:

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/test_integration_storage.py::test_minio_upload_download_delete_round_trip"
~~~

Because this fallback is run before the `RUN_INTEGRATION: "1"` Compose edit, its expected result is still the guarded skip; it is not the explicit MinIO execution used in Steps 2 and 4.

- [ ] **Step 2: Enable explicit MinIO execution and expose the stale bucket assertion**

Use `apply_patch` to add the existing guard variable only to the integration test service:

~~~diff
*** Begin Patch
*** Update File: docker-compose.integration.yml
@@
     environment:
       APP_ENV: test
+      RUN_INTEGRATION: "1"
       TEST_RUN_ID: ${TEST_RUN_ID}
       POSTGRES_HOST: db
*** End Patch
~~~

Before changing the test assertion, execute the storage selector through the fresh run-scoped harness:

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/test_integration_storage.py::test_minio_upload_download_delete_round_trip"
~~~

Expected: the test is no longer skipped; it uploads and attempts to download from the bucket shaped like `land-valuation-test-vr-<run-id>`, then fails at the fixed `land-valuation` assertion. The script exits non-zero and still removes the Compose project, volumes, and containers in its `finally` block. Do not treat this RED result as a storage pass.

- [ ] **Step 3: Make the storage expectation follow the configured service bucket**

Use `apply_patch` to replace the hard-coded assertion and leave the object key, download, byte comparison, and `finally` deletion unchanged:

~~~diff
*** Begin Patch
*** Update File: tests/test_integration_storage.py
@@
-        assert result["bucket_name"] == "land-valuation"
+        assert result["bucket_name"] == service.bucket
         assert result["object_key"] == object_key
*** End Patch
~~~

The resulting assertion must be exactly equivalent to:

~~~python
assert result["bucket_name"] == service.bucket
assert result["object_key"] == object_key
~~~

Do not add a development bucket fallback, a shared object prefix, or a production configuration change. The existing `finally` block must continue to call `await service.delete(object_key)`; a successful call against the configured bucket is the test's delete operation, and Compose teardown removes the run-scoped infrastructure.

- [ ] **Step 4: Run the explicit storage GREEN test and verify cleanup**

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/test_integration_storage.py::test_minio_upload_download_delete_round_trip"
~~~

Expected: the isolated run passes with no skip; upload metadata names `service.bucket`, download returns the exact payload bytes, and the `finally` delete completes. The script exits zero, then its cleanup assertions report no containers or volumes for the generated Compose project.

- [ ] **Step 5: Review and commit only Task 2**

~~~powershell
git diff --check -- tests/test_integration_storage.py docker-compose.integration.yml
git diff --name-only -- tests/test_integration_storage.py docker-compose.integration.yml
git add -- tests/test_integration_storage.py docker-compose.integration.yml
git commit -m "test: exercise run-scoped MinIO storage"
~~~

Expected: the diff contains only the configured bucket assertion and the one test-service environment entry; the commit contains exactly the two Task 2 files and no application, schema, migration, script, or unrelated untracked path.

### Task 3: Perform fresh verification and scope audit

**Files:**

- Verify only: the four files changed by Tasks 1 and 2.
- Do not modify: production Python, `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md`, `.serena/`, schema, migrations, or external branches.

**Interfaces:**

- Consumes: the two implementation commits, the isolated Compose runner, the Review test suite, and the existing Review test UI assets.
- Produces: reproducible focused, integration, non-integration, Review UI, migration-scope, and worktree evidence without claiming browser acceptance from static tests.

- [ ] **Step 1: Re-run the focused contract selectors from a fresh Compose project**

~~~powershell
python -m pytest -q tests/test_submission_service.py::test_revision_and_recheck_sessions_follow_case_review_correction_lock_order
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_valuation_review_handoff.py::test_appraiser_submission_handoff_is_reviewable_and_statuses_pair tests/integration/test_valuation_review_handoff.py::test_two_sessions_serialize_revision_and_recheck_locks tests/integration/test_valuation_review_handoff.py::test_revision_response_registration_rolls_back_submission_on_lineage_failure tests/test_integration_storage.py::test_minio_upload_download_delete_round_trip"
~~~

If the direct unit command fails before collection because the host Python or virtual environment lacks project dependencies, rerun that selector with the dependency-complete harness:

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/test_submission_service.py::test_revision_and_recheck_sessions_follow_case_review_correction_lock_order"
~~~

Expected: the unit selector and all selected integration/storage selectors pass; the fresh isolated run executes the MinIO selector rather than skipping it, and leaves no run-scoped database containers, volumes, or MinIO object after teardown.

- [ ] **Step 2: Run the non-integration Python suite and report skips honestly**

~~~powershell
python -m pytest -q tests --ignore=tests/integration
~~~

If this host command fails before collection because the host Python or virtual environment lacks project dependencies, run the dependency-complete equivalent while excluding the separately verified guarded storage selector:

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests --ignore=tests/integration --ignore=tests/test_integration_storage.py"
~~~

Expected: the non-integration suite completes without test failures. In the direct host command, the root-level guarded storage test may report a skip because `RUN_INTEGRATION` is not set; preserve that skip in the evidence and do not relabel it as a successful MinIO execution.

- [ ] **Step 3: Verify the existing Review UI contract without changing UI files**

~~~powershell
python -m pytest -q app/review/tests
node --test app/review/tests/test_ui_behavior.mjs
~~~

If the Review Python command fails before collection because the host Python or virtual environment lacks project dependencies, rerun only that Python suite with the dependency-complete harness:

~~~powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "app/review/tests"
~~~

Expected: the Review backend/UI contract tests and the JavaScript behavior tests pass. This repair changes no Review UI or seed behavior, so a browser flow is not relevant to acceptance of this change; do not claim the real `APPRAISER login -> Valuation submit -> REVIEWER login -> Review review` browser flow from these automated checks. If a reviewer separately requests browser acceptance, it must use persistent prepared data and an actual browser session as a distinct activity.

- [ ] **Step 4: Prove there is no Alembic, schema, or production-source diff**

After the two implementation commits, the implementation range is the two commits immediately after the plan commit. Capture and inspect that range:

~~~powershell
$implementationBase = git rev-parse HEAD~2
git diff --name-only "$implementationBase..HEAD"
git diff --name-only "$implementationBase..HEAD" -- app database migrations
git diff --check "$implementationBase..HEAD"
~~~

Expected: the first command lists exactly `tests/integration/test_valuation_review_handoff.py`, `tests/test_submission_service.py`, `tests/test_integration_storage.py`, and `docker-compose.integration.yml`; the second command is empty; and `git diff --check` is silent. Do not run or create a migration, and do not alter `origin/feature/valuation`.

- [ ] **Step 5: Verify final worktree and commit scope**

~~~powershell
git show --stat --oneline HEAD
git show --name-only --format= HEAD
git status --short --branch
~~~

Expected: the last commit is the Task 2 commit and names only `tests/test_integration_storage.py` and `docker-compose.integration.yml`; the preceding implementation commit names only the two Task 1 test files. The pre-existing untracked entries `.serena/` and `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md` remain untouched, and no draft patch or unexpected file is staged.

## Acceptance Criteria

- The three handoff integration selectors and the MinIO round trip are the four baseline contracts in scope and pass against the existing production contracts; the unit lock-order selector also passes after its companion fixture-consistency repair, but is not counted as a baseline failure.
- The handoff test reads and rechecks the original fingerprint from the persisted, ownership-scoped submission snapshot after live-source mutation.
- Review correction fixtures use `RETURNED_FOR_REVISION`; Valuation case fixtures retain `REVISION_REQUIRED`; no Review fixture uses case-only `IN_REVIEW`.
- The lineage-failure test captures the correction request UUID before commit, observes `CORRECTION_RESUBMISSION_INVALID`, rolls back, and proves that no extra submission or fingerprint change was committed.
- The MinIO selector runs under the standard Compose harness, asserts `result["bucket_name"] == service.bucket`, compares downloaded bytes, deletes the object in `finally`, and uses a fresh run-scoped bucket.
- The default host run reports a guarded MinIO skip honestly; the explicit isolated run reports the MinIO test as executed.
- The non-integration suite and Review UI checks pass, with no browser-acceptance claim.
- The implementation range contains no production, Valuation, Review schema, database, or migration changes, and all untracked pre-existing items remain out of the commits.

## Execution Handoff

This plan is ready for task-by-task execution. Use a fresh implementation session with either subagent-driven development (one reviewed worker per task) or inline execution with a review checkpoint after each commit; preserve the RED evidence and the exact file-scope checks above.
