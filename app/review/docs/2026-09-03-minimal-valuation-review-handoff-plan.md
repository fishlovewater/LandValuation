# Minimal Valuation to Review Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the smallest production-shaped flow in which an APPRAISER submits an immutable Valuation snapshot and a REVIEWER can open and review that exact submission.

**Architecture:** Restore the previously implemented submission command and permission migration, then adapt Review's demo, workbench, and trusted-input resolution to the canonical extraction schema and immutable submission snapshot. Preserve legacy standalone Review cases through an explicit fallback, keep the database transaction as the handoff boundary, and avoid new UI frameworks or speculative resubmission features.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL 16/pgvector, Alembic, MinIO, pytest, Node test runner, Docker Compose.

## Global Constraints

- Work only on `feature/integrate-valuation-review`; do not modify `feature/review` or `origin/feature/valuation`.
- Do not push or merge.
- PostgreSQL stores structured data and object metadata; MinIO stores file bodies.
- Never expose or accept bucket names, object keys, fixed localhost URLs, or presigned URLs in the submission command.
- Official numeric values remain Decimal-derived and snapshots reject floats.
- Historical Submission, Run, finding, decision, correction request, and report records are immutable.
- Machine Run results remain separate from reviewer decisions.
- Every production change follows red-green-refactor and is verified in the isolated Docker test environment.
- Preserve the pre-existing untracked `.serena/` directory.

---

### Task 1: Restore the submission command and its focused tests

**Files:**
- Create: `app/valuation/submissions/__init__.py`
- Create: `app/valuation/submissions/schemas.py`
- Create: `app/valuation/submissions/snapshot.py`
- Create: `app/valuation/submissions/repository.py`
- Create: `app/valuation/submissions/service.py`
- Create: `app/valuation/submissions/router.py`
- Modify: `app/api/router.py`
- Modify: `app/review/models.py`
- Create: `tests/test_submission_snapshot.py`
- Create: `tests/test_submission_service.py`
- Create: `tests/test_submission_api.py`

**Interfaces:**
- Consumes: canonical `ExtractedFieldRecord`, `FormInstanceRecord`, `DocumentRecord`, `ValidationRun`, `Review`, and `ReviewSubmissionRecord` from migrations through `20260901_0012`.
- Produces: `SubmitForReviewCommand`, `SubmitForReviewResult`, `SubmissionRepository`, `SubmissionService.submit()`, and `POST /api/v1/valuation/cases/{case_id}/submit-for-review`.

- [ ] **Step 1: Restore the exact pre-revert tests as the RED baseline**

Restore these files from commit `9a74975` without production files:

```powershell
git restore --source 9a74975 -- tests/test_submission_snapshot.py tests/test_submission_service.py tests/test_submission_api.py
```

- [ ] **Step 2: Run the restored tests and verify RED**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_submission_snapshot.py tests/test_submission_service.py tests/test_submission_api.py"
```

Expected: collection fails with `ModuleNotFoundError: app.valuation.submissions` or the route assertions fail because the runtime was reverted.

- [ ] **Step 3: Restore the minimal production implementation**

Restore the known implementation from `9a74975`:

```powershell
git restore --source 9a74975 -- app/valuation/submissions app/api/router.py app/review/models.py
```

Required public request shape:

```python
class SubmitForReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_case_version: int = Field(ge=1)
    source_validation_run_id: UUID
    source_report_document_id: UUID

```

`SubmissionService.submit()` must accept `case_id: UUID`, `command: SubmitForReviewCommand`, and `actor: User`, and return `SubmitForReviewResult`.

The router must require `valuation.submit_review` and must not accept client-owned snapshot data.

- [ ] **Step 4: Run the focused tests and verify GREEN**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_submission_snapshot.py tests/test_submission_service.py tests/test_submission_api.py"
```

Expected: all restored snapshot, service, and API tests pass.

- [ ] **Step 5: Commit only Task 1 files**

```powershell
git add app/valuation/submissions app/api/router.py app/review/models.py tests/test_submission_snapshot.py tests/test_submission_service.py tests/test_submission_api.py
git commit -m "feat(valuation): restore minimal review submission"
```

### Task 2: Restore least-privilege submission permissions

**Files:**
- Create: `migrations/versions/20260903_0013_submit_review_permission.py`
- Create: `tests/integration/test_submission_command.py`
- Modify: `tests/integration/sql/001_runtime_role.sql`

**Interfaces:**
- Consumes: group role `land_valuation_app`, migration owner URL, and runtime `DATABASE_URL`.
- Produces: APPRAISER permission `valuation.submit_review` plus runtime access to `review.reviews`, `history.case_events`, and `valuation.review_submissions` required by one atomic submission transaction.

- [ ] **Step 1: Restore the permission tests first**

```powershell
git restore --source 9a74975 -- tests/integration/test_submission_command.py
```

- [ ] **Step 2: Verify RED against current head**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/integration/test_submission_command.py"
```

Expected: failure because revision `20260903_0013`, permission seeding, or runtime Review/history privileges are absent.

- [ ] **Step 3: Restore and minimally harden revision 0013**

```powershell
git restore --source 9a74975 -- migrations/versions/20260903_0013_submit_review_permission.py
```

The upgrade contract must remain:

```sql
GRANT USAGE ON SCHEMA review, history TO land_valuation_app;
GRANT SELECT, INSERT, UPDATE ON review.reviews TO land_valuation_app;
GRANT INSERT ON history.case_events TO land_valuation_app;
GRANT SELECT (occurred_at) ON history.case_events TO land_valuation_app;
GRANT SELECT, INSERT ON valuation.review_submissions TO land_valuation_app;
```

Add only privileges proven necessary by failing Review behavior tests. Do not grant DELETE on Review or Submission history and do not make the migration owner a member of the runtime group.

- [ ] **Step 4: Verify permission and real-session concurrency tests**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/integration/test_submission_command.py tests/integration/test_migration_0012_submission.py"
```

Expected: runtime ACL assertions, migration downgrade/re-upgrade, immutability, and concurrent idempotency pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add migrations/versions/20260903_0013_submit_review_permission.py tests/integration/test_submission_command.py tests/integration/sql/001_runtime_role.sql
git commit -m "fix(db): grant minimal submission workflow access"
```

### Task 3: Move the Review demo and workbench to canonical extraction

**Files:**
- Modify: `app/review/demo.py`
- Modify: `app/review/workbench_repository.py`
- Modify: `app/review/workbench_service.py`
- Modify: `app/review/tests/test_demo_workflow.py`
- Modify: `app/review/tests/test_workbench_demo.py`
- Modify: `app/review/tests/test_workbench_service.py`
- Modify: `app/review/tests/test_schema_contract.py`

**Interfaces:**
- Consumes: `valuation.document_extractions` and canonical `valuation.extracted_fields` fields: `extraction_id`, `form_code`, `field_name`, `confirmed_value`, `source_page`, `source_text`, `field_status`.
- Produces: an idempotent Review demo lifecycle and workbench detail that never reads `valuation.extraction_runs`.

- [ ] **Step 1: Add canonical-schema regression assertions**

Add a source-level guard to `test_schema_contract.py` and behavior assertions to Demo/workbench tests:

```python
def test_review_runtime_does_not_reference_legacy_extraction_schema():
    sources = [
        Path("app/review/demo.py").read_text(encoding="utf-8"),
        Path("app/review/workbench_repository.py").read_text(encoding="utf-8"),
    ]
    joined = "\n".join(sources)
    assert "valuation.extraction_runs" not in joined
    assert "extraction_run_id" not in joined
```

Update the seeded-row assertions to require one completed `document_extractions` row and APPLIED canonical fields with confirmed values.

- [ ] **Step 2: Verify RED**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_schema_contract.py app/review/tests/test_demo_workflow.py app/review/tests/test_workbench_demo.py"
```

Expected: failures point to legacy SQL in `demo.py` and `workbench_repository.py`.

- [ ] **Step 3: Replace Demo extraction writes and cleanup**

Replace `_insert_extraction` with this interface:

```python
def _insert_extraction(
    cursor,
    *,
    case_id: UUID,
    document_id: UUID,
    user_id: UUID,
    form_instance_id: UUID,
    adjustment_rate: str,
    expert_grade: str,
) -> UUID:
    """Create one COMPLETED canonical extraction and two APPLIED fields."""
```

Insert into `valuation.document_extractions`, then insert fields using `extraction_id`, `form_code`, `field_name`, `extracted_value`, `confirmed_value`, `field_status='APPLIED'`, confirmation actor/time, and applied form/time. Cleanup deletes canonical extracted fields by `case_id`, then document extractions by `case_id`.

- [ ] **Step 4: Replace the workbench version query**

`list_official_field_versions(case_id)` must join `valuation.documents` to `valuation.document_extractions`, select the latest completed extraction per document, then select APPLIED fields:

```sql
SELECT d.document_id, d.document_group_id, d.version_no AS document_version,
       ef.field_name AS field_code,
       concat(ef.form_code, '.', ef.field_name) AS field_path,
       ef.confirmed_value AS normalized_value,
       coalesce(ef.source_text, '') AS raw_text,
       ef.source_page AS page_number
FROM valuation.documents AS d
JOIN LATERAL (
    SELECT extraction_id
    FROM valuation.document_extractions
    WHERE case_id = d.case_id
      AND document_id = d.document_id
      AND extraction_status = 'COMPLETED'
    ORDER BY completed_at DESC NULLS LAST, created_at DESC, extraction_id DESC
    LIMIT 1
) AS de ON true
JOIN valuation.extracted_fields AS ef
  ON ef.extraction_id = de.extraction_id
 AND ef.field_status = 'APPLIED'
WHERE d.case_id = :case_id
ORDER BY d.document_group_id, ef.field_name, d.version_no;
```

- [ ] **Step 5: Verify Demo and workbench GREEN**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests/test_schema_contract.py app/review/tests/test_demo.py app/review/tests/test_demo_workflow.py app/review/tests/test_workbench_demo.py app/review/tests/test_workbench_service.py"
```

Expected: seed/reset/revise and case-detail tests pass against migration head.

- [ ] **Step 6: Commit Task 3**

```powershell
git add app/review/demo.py app/review/workbench_repository.py app/review/workbench_service.py app/review/tests/test_demo.py app/review/tests/test_demo_workflow.py app/review/tests/test_workbench_demo.py app/review/tests/test_workbench_service.py app/review/tests/test_schema_contract.py
git commit -m "fix(review): use canonical extraction in demo and workbench"
```

### Task 4: Make Review execute against the immutable Submission Snapshot

**Files:**
- Modify: `app/valuation/submissions/repository.py`
- Modify: `app/valuation/submissions/snapshot.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/service.py`
- Modify: `app/review/workbench_repository.py`
- Modify: `app/review/workbench_service.py`
- Modify: `app/review/workbench_schemas.py`
- Modify: `tests/test_submission_service.py`
- Modify: `app/review/tests/test_trusted_inputs.py`
- Modify: `app/review/tests/test_runs_api.py`
- Modify: `app/review/tests/test_workbench_api.py`

**Interfaces:**
- Consumes: `Review.latest_submission_id` and `ReviewSubmissionRecord.input_snapshot`.
- Produces: `ReviewRepository.get_submission_snapshot(submission_id)` and snapshot-derived trusted fields/document evidence for submitted Reviews, with canonical live-data fallback only for legacy standalone Review records whose `latest_submission_id` is NULL.

- [ ] **Step 1: Write failing snapshot-content tests**

Require every submitted APPLIED field to carry immutable evidence:

```python
assert snapshot["applied_fields"][0] == {
    "extracted_field_id": str(field_id),
    "document_id": str(document_id),
    "form_code": "F03",
    "field_name": "adjustment_rate",
    "confirmed_value": "-12.0000",
    "source_page": 3,
    "source_text": "調整率 -12%",
    "confidence": "0.9500",
    "field_status": "APPLIED",
    "confirmed_by_user_id": str(appraiser_id),
    "confirmed_at": confirmed_at.isoformat(),
}
```

Add a Review run test that submits value `-12`, mutates the live canonical field to `-99`, executes Review, and asserts the Run snapshot and finding still use `-12`.

- [ ] **Step 2: Verify RED**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_submission_service.py app/review/tests/test_trusted_inputs.py app/review/tests/test_runs_api.py"
```

Expected: submission fields lack evidence and Review reads the mutated live field.

- [ ] **Step 3: Expand server-built snapshot inputs without changing the request body**

Extend `SubmissionRepository.load_submission_inputs()` to select and serialize `document_id`, evidence, confidence, status, confirmation actor/time, and all referenced document metadata. Continue to reject floats through `normalize_snapshot_value()`.

- [ ] **Step 4: Add the Review repository snapshot lookup**

```python
async def get_submission_snapshot(self, submission_id: UUID) -> dict | None:
    snapshot = await self.session.scalar(
        select(ReviewSubmissionRecord.input_snapshot).where(
            ReviewSubmissionRecord.submission_id == submission_id
        )
    )
    return dict(snapshot) if isinstance(snapshot, dict) else None
```

- [ ] **Step 5: Resolve submitted Review fields from Snapshot**

In `_resolve_trusted_run_context(review)`, use the immutable snapshot when `latest_submission_id` exists. Convert each `applied_fields` item through one explicit adapter:

```python
@staticmethod
def _trusted_field_from_submission(item: dict) -> TrustedField:
    return TrustedField(
        extracted_field_id=item["extracted_field_id"],
        form_code=item["form_code"],
        field_name=item["field_name"],
        confirmed_value=item["confirmed_value"],
        source_page=item.get("source_page"),
        source_text=item.get("source_text"),
        confidence=item.get("confidence"),
        field_status="APPLIED",
        confirmed_by_user_id=item.get("confirmed_by_user_id"),
        confirmed_at=item.get("confirmed_at"),
    )
```

If the pointer exists but the snapshot is missing or malformed, fail closed with `SUBMISSION_SNAPSHOT_INVALID` and status `409`. Only a NULL pointer may use the existing canonical live-data path for legacy Review cases.

- [ ] **Step 6: Expose submission provenance in workbench detail**

Add optional `submission_id`, `submission_no`, `submitted_at`, and `input_fingerprint` fields to the workbench detail response. Do not expose object keys or the raw full Snapshot by default.

- [ ] **Step 7: Verify snapshot immutability and workbench visibility GREEN**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_submission_snapshot.py tests/test_submission_service.py app/review/tests/test_trusted_inputs.py app/review/tests/test_runs_api.py app/review/tests/test_workbench_api.py"
```

Expected: submitted Review uses the pre-mutation value and workbench shows submission provenance.

- [ ] **Step 8: Commit Task 4**

```powershell
git add app/valuation/submissions/repository.py app/valuation/submissions/snapshot.py app/review/repository.py app/review/service.py app/review/workbench_repository.py app/review/workbench_service.py app/review/workbench_schemas.py tests/test_submission_service.py app/review/tests/test_trusted_inputs.py app/review/tests/test_runs_api.py app/review/tests/test_workbench_api.py
git commit -m "feat(review): execute against submitted snapshot"
```

### Task 5: Restore Valuation Swagger behavior

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_swagger_docs.py`

**Interfaces:**
- Consumes: `register_swagger_docs(application, title=settings.app_name)`.
- Produces: customized `/docs` with the large intake JSON editor when docs are enabled.

- [ ] **Step 1: Re-run the existing RED test**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_swagger_docs.py"
```

Expected: `test_swagger_docs_include_large_intake_json_editor` fails because `app/main.py` uses FastAPI's default docs route.

- [ ] **Step 2: Restore the upstream Valuation registration pattern**

```python
from app.core.swagger_docs import register_swagger_docs

application = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)
application.add_middleware(RequestContextMiddleware)
register_error_handlers(application)
application.include_router(health_router)
application.include_router(api_router, prefix=settings.api_prefix)
if settings.docs_enabled:
    register_swagger_docs(application, title=settings.app_name)
```

- [ ] **Step 3: Verify GREEN**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/test_swagger_docs.py tests/test_integration_surface.py"
```

Expected: customized docs and both subsystem routes pass.

- [ ] **Step 4: Commit Task 5**

```powershell
git add app/main.py
git commit -m "fix(api): restore valuation swagger editor"
```

### Task 6: Isolate migration round-trip tests

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/test_migration_0010_forms_reports.py`
- Modify: `tests/integration/test_migration_0011_rule_sources.py`
- Modify: `tests/integration/test_migration_0012_submission.py`
- Modify: `tests/integration/test_submission_command.py`

**Interfaces:**
- Consumes: `MIGRATION_DATABASE_URL` and the current Alembic head.
- Produces: a schema-mutating test fixture that always returns the database to head even after a failing assertion.

- [ ] **Step 1: Add a test proving a downgraded test cannot poison its successor**

Add a pair of ordered tests in a dedicated class or module: the first downgrades to `20260901_0009` and intentionally exits after registering cleanup; the second asserts `alembic_version` equals `20260903_0013` and all `0010`–`0013` columns exist.

- [ ] **Step 2: Verify RED with the combined migration order**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/integration"
```

Expected before the fix: the previously reproduced result includes downstream missing-column/table failures after an earlier migration test fails or leaves the schema downgraded.

- [ ] **Step 3: Add one schema mutation fixture**

```python
@pytest.fixture
def migration_roundtrip():
    migration_database_url = _database_url("MIGRATION_DATABASE_URL")

    def run(command: str, revision: str, *, expect_success: bool = True):
        env = {**os.environ, "DATABASE_URL": migration_database_url}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", command, revision],
            capture_output=True,
            text=True,
            env=env,
        )
        assert (result.returncode == 0) is expect_success, result.stdout + result.stderr
        return result

    try:
        yield run
    finally:
        env = {**os.environ, "DATABASE_URL": migration_database_url}
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
```

Use this fixture in every test that calls Alembic directly. Remove duplicated `_run_alembic()` helpers. Ensure test-owned rows are deleted before final upgrade when a downgrade guard intentionally rejects live data.

- [ ] **Step 4: Verify the entire integration directory GREEN twice**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/integration"
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/integration"
```

Expected: both independent runs pass with identical totals and no missing-schema cascades.

- [ ] **Step 5: Commit Task 6**

```powershell
git add tests/integration
git commit -m "test(db): isolate migration round trips"
```

### Task 7: Verify the full appraiser-to-reviewer flow

**Files:**
- Create: `tests/integration/test_valuation_review_handoff.py`
- Modify: `tests/test_integration_surface.py`
- Modify: `app/review/docs/2026-09-03-minimal-valuation-review-handoff-design.md`

**Interfaces:**
- Consumes: completed Valuation report, submission API/service, Review queue/detail, Review Run and decision services.
- Produces: one executable acceptance test for the user-visible handoff.

- [ ] **Step 1: Write the failing end-to-end acceptance test**

The test must create real database rows and use application services/API to assert this sequence:

```python
submission = await SubmissionService(session).submit(case_id, command, appraiser)
await session.commit()

workbench = WorkbenchService(
    WorkbenchRepository(session),
    ReviewRepository(session),
    CorrectionRepository(session),
)
queue = await workbench.list_cases(None, None, None, None, 100, 0)
assert submission.review_id in {item.review_id for item in queue.items}

detail = await workbench.detail(submission.review_id)
assert detail.submission_id == submission.submission_id
assert detail.submission_no == 1

run, summary = await ReviewService(session).create_run(
    submission.review_id,
    reviewer.user_id,
)
assert run.submission_id == submission.submission_id
assert summary.review_id == submission.review_id
```

For the approval branch, resolve every finding through `ReviewService.triage_finding()` and the existing finding-decision contract, then call `CorrectionService.complete_review(review_id, reason, reviewer.user_id, request_id)`. Assert both `review.reviews.review_status` and `valuation.cases.case_status` equal `REVIEW_COMPLETED`. Add a separate return assertion through `CorrectionService.send(request_id, reviewer.user_id, audit_request_id)` and require Review `RETURNED_FOR_REVISION` plus Valuation `REVISION_REQUIRED`.

- [ ] **Step 2: Verify RED for the first missing handoff behavior**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/integration/test_valuation_review_handoff.py"
```

Expected: failure at the first missing queue, immutable-snapshot, or paired final-status behavior, with the preceding assertions passing.

- [ ] **Step 3: Wire the paired completion and return statuses required by the acceptance test**

Reuse the restored Submission and existing Review services. In the existing locked completion transaction, set the Valuation case to `REVIEW_COMPLETED`; in the existing correction-send transaction, set it to `REVISION_REQUIRED`. Add no resubmission UI, notifications, background jobs, or new workflow layer.

- [ ] **Step 4: Verify the E2E handoff GREEN**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "tests/integration/test_valuation_review_handoff.py tests/test_integration_surface.py"
```

Expected: APPRAISER submission is visible and reviewable by REVIEWER using the immutable Snapshot.

- [ ] **Step 5: Update the short design with implemented evidence**

Record the exact route, migration head, automated E2E test, and deliberately deferred resubmission UI. Do not claim browser acceptance in this document.

- [ ] **Step 6: Commit Task 7**

```powershell
git add tests/integration/test_valuation_review_handoff.py tests/test_integration_surface.py app/review/docs/2026-09-03-minimal-valuation-review-handoff-design.md
git commit -m "test(integration): cover valuation review handoff"
```

### Task 8: Full verification and manual-test handoff

**Files:**
- Verify only; modify files only if a failing test identifies an in-scope defect and restart that defect's TDD cycle.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: fresh acceptance evidence and a clean manual-test handoff.

- [ ] **Step 1: Run Review frontend behavior tests**

```powershell
node --test app/review/tests/test_ui_behavior.mjs
```

Expected: all Node tests pass.

- [ ] **Step 2: Run Review backend suite**

```powershell
.\scripts\run-integration-tests.ps1 -PytestArgs "app/review/tests"
```

Expected: zero failures and zero errors.

- [ ] **Step 3: Run the complete isolated suite**

```powershell
.\scripts\run-integration-tests.ps1
```

Expected: zero failures and the script confirms cleanup.

- [ ] **Step 4: Run repository quality checks**

```powershell
git diff --check feature/review...HEAD
python -m compileall -q app tests
git status --short --branch
```

Expected: no new whitespace errors, Python compiles, and only the pre-existing `.serena/` remains untracked.

- [ ] **Step 5: Verify Docker cleanup**

```powershell
docker ps -a --filter name=valuation-review-vr --format "{{.Names}} {{.Status}}"
docker network ls --filter name=valuation-review-vr --format "{{.Name}}"
```

Expected: both commands return no test resources.

- [ ] **Step 6: Request independent code review**

Review the full range from `24e5688` to HEAD for blocking correctness, authorization, immutable snapshot, migration safety, and Demo regressions. Address every blocking or important finding through a new TDD cycle.

- [ ] **Step 7: Prepare the user's browser checklist**

Provide a short role-by-role checklist: APPRAISER creates/formalizes/submits, REVIEWER logs in/sees the same case/opens immutable evidence/runs review/decides/approves or returns. Clearly state that browser acceptance remains for the user and do not claim it from Node tests.
