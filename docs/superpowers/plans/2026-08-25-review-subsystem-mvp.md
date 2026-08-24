# Review Subsystem MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one complete, traceable review workflow for a fixed valuation case: queue, missing-material handling, deterministic findings, risk, reviewer decisions, rerun, and structured report.

**Architecture:** Extend the existing `review` and `valuation.validation_*` tables instead of creating duplicate case/run tables. Mount one `/api/v1/review` router, then keep all domain code and tests under `app/review/**`; deterministic services produce immutable machine evidence, while reviewer-facing findings and decisions remain separate.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2 async, PostgreSQL 16, Alembic, MinIO, pytest, pytest-asyncio.

## Global Constraints

- Do not modify Alembic revisions `20260823_0001` through `20260824_0004`; add `20260825_0005` only.
- Do not update `database/init/**`; Alembic is the authoritative schema source.
- Do not create another PostgreSQL engine, `AsyncSession`, MinIO client, authentication system, case master, or error format.
- PostgreSQL stores structured data and metadata; MinIO stores PDF/image/attachment bodies.
- MinIO uses bucket `land-valuation`; object keys start with `cases/` or `knowledge/` and never store localhost URLs or presigned URLs.
- Formal amount, rate, and grade calculations use `Decimal`; AI never performs authoritative calculations or final approval.
- Existing documents, runs, findings, risk summaries, and decisions are append-only audit records and are never overwritten.
- Before Task 2 ends, the permitted non-`app/review/**` changes are revision `20260825_0005`, adding `boto3>=1.35,<2.0` and `reportlab>=4.2,<5.0` to `requirements.txt`, and mounting the router in `app/api/router.py`.
- After Task 2 completes, do not modify any path outside `app/review/**` without explicit user approval.
- New tests live in `app/review/tests/**`; run the full suite explicitly as `pytest tests app/review/tests` because `pytest.ini` currently limits default discovery to `tests`.
- Do not create Vue code, online training, automatic rule updates, multi-reviewer locking, or cross-case analytics.

---

## File Map

- `migrations/versions/20260825_0005_expand_review_workflow.py`: one-time schema extension before the path lock starts.
- `app/api/router.py`: one-time review router registration in Task 2.
- `app/review/models.py`: SQLAlchemy mappings for existing and newly extended review/validation tables.
- `app/review/schemas.py`: request/response contracts and finding evidence structures.
- `app/review/repository.py`: async PostgreSQL queries and writes using the existing request session.
- `app/review/service.py`: review lifecycle orchestration and state transitions.
- `app/review/sorting.py`: deterministic queue ordering.
- `app/review/completeness.py`: required-document and required-field evaluation.
- `app/review/rule_selection.py`: published, effective rule selection.
- `app/review/recalculation.py`: Decimal grade/rate/price calculations.
- `app/review/ai.py`: Bedrock structured finding explanation with schema validation and deterministic fallback.
- `app/review/risks.py`: hard-coded severity aggregation.
- `app/review/decisions.py`: finding and case decision validation.
- `app/review/reports.py`: structured review report assembly.
- `app/review/pdf_reports.py`: fixed-layout PDF bytes for storage through the existing MinIO service.
- `app/review/tests/**`: unit, API, schema-contract, and workflow tests.

---

### Task 1: Extend the Existing Review Schema

**Files:**
- Create: `app/review/tests/conftest.py`
- Create: `app/review/tests/test_schema_contract.py`
- Create: `migrations/versions/20260825_0005_expand_review_workflow.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: existing revision `20260824_0004`, schemas `review` and `valuation`.
- Produces: queue fields on `review.reviews`, run/version fields on `valuation.validation_runs`, rich evidence fields on `review.findings`, audit fields on decisions/missing items, and run-scoped risk summaries.

- [ ] **Step 1: Write the failing live-schema contract test**

Create `app/review/tests/conftest.py` with the live database fixture:

```python
import os

import psycopg
import pytest


@pytest.fixture
def postgres_connection():
    connection = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        yield connection
    finally:
        connection.close()
```

Create a test that queries `information_schema.columns` and requires this exact minimum contract:

```python
EXPECTED_COLUMNS = {
    ("review", "reviews", "received_at"),
    ("review", "reviews", "due_at"),
    ("review", "reviews", "assigned_reviewer_id"),
    ("review", "reviews", "manual_priority"),
    ("review", "reviews", "current_risk_level"),
    ("review", "reviews", "latest_validation_run_id"),
    ("valuation", "validation_runs", "review_id"),
    ("valuation", "validation_runs", "input_snapshot"),
    ("valuation", "validation_runs", "model_id"),
    ("valuation", "validation_runs", "prompt_version"),
    ("review", "findings", "source_evidence"),
    ("review", "findings", "comparison_result"),
    ("review", "findings", "recommended_action"),
    ("review", "findings", "ai_reasoning_summary"),
    ("review", "decisions", "request_id"),
}

def test_review_schema_contains_mvp_contract(postgres_connection):
    with postgres_connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema IN ('review', 'valuation')
        """)
        actual = set(cursor.fetchall())
    assert EXPECTED_COLUMNS <= actual
```

- [ ] **Step 2: Run the contract test and verify RED**

Run: `rtk docker compose up -d db`

Run: `rtk docker compose build api`

Run: `rtk docker compose run --rm api pytest app/review/tests/test_schema_contract.py -q`

Expected: FAIL listing the absent `received_at`, `review_id`, evidence, and audit columns.

- [ ] **Step 3: Add revision `20260825_0005`**

The migration must use explicit `op.execute()` statements and add:

```sql
ALTER TABLE review.reviews
  ADD COLUMN received_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN due_at timestamptz,
  ADD COLUMN assigned_reviewer_id uuid,
  ADD COLUMN manual_priority integer NOT NULL DEFAULT 0,
  ADD COLUMN manual_priority_reason text,
  ADD COLUMN current_risk_level varchar(20),
  ADD COLUMN high_count integer NOT NULL DEFAULT 0,
  ADD COLUMN medium_count integer NOT NULL DEFAULT 0,
  ADD COLUMN low_count integer NOT NULL DEFAULT 0,
  ADD COLUMN missing_item_count integer NOT NULL DEFAULT 0,
  ADD COLUMN latest_validation_run_id uuid;

ALTER TABLE valuation.validation_runs
  ADD COLUMN review_id uuid,
  ADD COLUMN input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN model_id varchar(200),
  ADD COLUMN prompt_version varchar(100),
  ADD COLUMN error_code varchar(100),
  ADD COLUMN error_message text;
```

Add foreign keys with `ON DELETE RESTRICT`, nonnegative count/priority checks, due-date checks, review status values from the design, a partial unique index allowing only one `RUNNING` validation run per review, and queue indexes. Add the finding evidence JSONB/text/numeric fields from the design, `supersedes_finding_id`, `request_id` plus before/after JSONB on decisions, and run linkage plus resolution/notification details on missing items and risk summaries. Convert `review.risk_summaries.review_id` from unique-per-review to unique `(review_id, validation_run_id)` without deleting old rows.

Use these exact additional columns:

```sql
ALTER TABLE review.findings
  ADD COLUMN validation_run_id uuid,
  ADD COLUMN document_id uuid,
  ADD COLUMN document_version integer,
  ADD COLUMN page_number integer,
  ADD COLUMN field_path text,
  ADD COLUMN bounding_box jsonb,
  ADD COLUMN source_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN reported_text text,
  ADD COLUMN reported_value text,
  ADD COLUMN legal_basis jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN reported_grade varchar(100),
  ADD COLUMN system_grade varchar(100),
  ADD COLUMN reported_adjustment_rate numeric(12,6),
  ADD COLUMN system_adjustment_rate numeric(12,6),
  ADD COLUMN comparison_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN recommended_action jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN ai_reasoning_summary text,
  ADD COLUMN ai_confidence numeric(5,4),
  ADD COLUMN ai_status varchar(40) NOT NULL DEFAULT 'NOT_REQUESTED',
  ADD COLUMN supersedes_finding_id uuid;

ALTER TABLE review.decisions
  ADD COLUMN request_id uuid,
  ADD COLUMN before_value jsonb,
  ADD COLUMN after_value jsonb;

ALTER TABLE review.missing_items
  ADD COLUMN validation_run_id uuid,
  ADD COLUMN field_path text,
  ADD COLUMN reason text,
  ADD COLUMN affected_rule_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN due_at timestamptz,
  ADD COLUMN notified_at timestamptz,
  ADD COLUMN notification_status varchar(30);

ALTER TABLE review.risk_summaries
  ADD COLUMN validation_run_id uuid,
  ADD COLUMN high_count integer NOT NULL DEFAULT 0,
  ADD COLUMN medium_count integer NOT NULL DEFAULT 0,
  ADD COLUMN low_count integer NOT NULL DEFAULT 0,
  ADD COLUMN missing_item_count integer NOT NULL DEFAULT 0,
  ADD COLUMN risk_reasons jsonb NOT NULL DEFAULT '[]'::jsonb;
```

The downgrade must remove only objects introduced by `0005`, in reverse dependency order.

- [ ] **Step 4: Add the two locked-in runtime dependencies**

Append exactly these compatible ranges to `requirements.txt` before the path lock starts:

```text
boto3>=1.35,<2.0
reportlab>=4.2,<5.0
```

- [ ] **Step 5: Apply migration and verify GREEN**

Run: `rtk docker compose build migrate api`

Run: `rtk docker compose run --rm migrate alembic upgrade head`

Run: `rtk docker compose run --rm api pytest app/review/tests/test_schema_contract.py -q`

Expected: migration exits 0 and the schema contract test passes.

- [ ] **Step 6: Verify reversible migration on an isolated test database**

Run the revision sequence `upgrade 20260825_0005`, `downgrade 20260824_0004`, `upgrade 20260825_0005` against a disposable PostgreSQL database.

Expected: all three commands exit 0; the final `alembic current` reports `20260825_0005`.

- [ ] **Step 7: Commit the schema and dependency slice**

```powershell
rtk git add requirements.txt migrations/versions/20260825_0005_expand_review_workflow.py app/review/tests/conftest.py app/review/tests/test_schema_contract.py
rtk git commit -m "feat(review): expand review workflow schema"
```

---

### Task 2: Create and Mount the Review Module

**Files:**
- Create: `app/review/__init__.py`
- Create: `app/review/router.py`
- Create: `app/review/tests/__init__.py`
- Create: `app/review/tests/test_router.py`
- Modify once: `app/api/router.py`

**Interfaces:**
- Consumes: existing `api_router`, `require_permissions`, and `DbSession`.
- Produces: `app.review.router.router` mounted at `/api/v1/review`; after this task, the path lock is active.

- [ ] **Step 1: Write the failing router test**

```python
from app.main import application

def test_review_router_is_registered():
    paths = {route.path for route in application.routes}
    assert "/api/v1/review/cases" in paths
```

- [ ] **Step 2: Verify RED**

Run: `rtk docker compose run --rm api pytest app/review/tests/test_router.py -q`

Expected: FAIL because `/api/v1/review/cases` is absent.

- [ ] **Step 3: Add the minimal router and mount it once**

`app/review/router.py` starts with:

```python
from fastapi import APIRouter, Depends
from app.auth.dependencies import require_permissions

router = APIRouter(prefix="/review", tags=["review"])

@router.get("/cases")
async def list_review_cases(
    user=Depends(require_permissions("review.execute")),
) -> list[dict]:
    return []
```

Add only these lines to `app/api/router.py`:

```python
from app.review.router import router as review_router
api_router.include_router(review_router)
```

- [ ] **Step 4: Verify GREEN and authorization behavior**

Add tests proving unauthenticated requests return `401` and a user lacking `review.execute` returns `403`, then run:

`rtk docker compose run --rm api pytest app/review/tests/test_router.py tests/test_permissions.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Activate the path lock and commit**

From this point onward, stop before changing any path outside `app/review/**`.

```powershell
rtk git add app/api/router.py app/review
rtk git commit -m "feat(review): mount review API module"
```

---

### Task 3: Implement Queue Models, Sorting, Repository, and APIs

**Files:**
- Create: `app/review/models.py`
- Create: `app/review/schemas.py`
- Create: `app/review/sorting.py`
- Create: `app/review/repository.py`
- Create: `app/review/service.py`
- Modify: `app/review/router.py`
- Create: `app/review/tests/test_sorting.py`
- Create: `app/review/tests/test_service.py`
- Create: `app/review/tests/test_cases_api.py`

**Interfaces:**
- Consumes: existing `AsyncSession`, `auth.User`, and schema from Task 1.
- Produces: `ReviewCreate`, `ReviewUpdate`, `ReviewRead`, `ReviewList`, `ReviewRepository`, `ReviewService`, and queue endpoints.

- [ ] **Step 1: Write failing deterministic sorting tests**

```python
def test_queue_key_prioritizes_manual_then_overdue_then_risk():
    ordered = sorted(cases, key=review_queue_key)
    assert [item.case_no for item in ordered] == ["MANUAL", "OVERDUE", "HIGH", "NORMAL"]

def test_remaining_days_uses_due_date_and_reference_time():
    assert remaining_days(due_at, now) == 2
```

Use timezone-aware UTC datetimes and include equal-key tie cases for `received_at`.

- [ ] **Step 2: Verify RED, implement `sorting.py`, verify GREEN**

The public functions are `remaining_days(due_at: datetime | None, now: datetime) -> int | None` and `review_queue_key(item: QueueSortable, now: datetime) -> tuple[int, int, int, int, int, datetime]`. The queue key negates descending numeric fields and uses `datetime.max` when no due date exists so ordinary ascending `sorted()` yields the specified order.

Run: `rtk docker compose run --rm api pytest app/review/tests/test_sorting.py -q`

- [ ] **Step 3: Write failing service transition tests**

Require these legal transitions:

```python
ALLOWED_TRANSITIONS = {
    "RECEIVED": {"PREPROCESSING"},
    "PREPROCESSING": {"PENDING_MATERIALS", "READY_FOR_REVIEW"},
    "PENDING_MATERIALS": {"PREPROCESSING"},
    "READY_FOR_REVIEW": {"ANALYZING"},
    "ANALYZING": {"REVIEW_REQUIRED"},
    "REVIEW_REQUIRED": {"RETURNED_FOR_REVISION", "SUPPLEMENT_REQUIRED", "EXPERT_REVIEW", "APPROVED"},
    "RETURNED_FOR_REVISION": {"PREPROCESSING"},
    "SUPPLEMENT_REQUIRED": {"PREPROCESSING"},
    "EXPERT_REVIEW": {"REVIEW_REQUIRED"},
    "APPROVED": {"REVIEW_COMPLETED"},
    "REVIEW_COMPLETED": set(),
}
```

Illegal transitions raise an `AppError` with code `REVIEW_STATE_CONFLICT` and status `409`.

- [ ] **Step 4: Implement mappings and repository**

Map existing tables without `create_all()`. `ReviewRepository` exposes the exact methods `create(payload: ReviewCreate, started_by_user_id: UUID) -> Review`, `get(review_id: UUID, for_update: bool = False) -> Review | None`, `list(query: ReviewListQuery) -> tuple[list[Review], int]`, `assign(review_id: UUID, reviewer_id: UUID) -> Review`, and `set_priority(review_id: UUID, priority: int, reason: str, actor_id: UUID) -> Review`.

All list filters are SQL expressions, all ordering is deterministic, and pagination uses `limit <= 100`.

- [ ] **Step 5: Implement queue APIs and verify RED→GREEN**

Add and test:

```text
POST  /review/cases                  201
GET   /review/cases                  200
GET   /review/cases/{review_id}      200/404
PATCH /review/cases/{review_id}      200/409
POST  /review/cases/{review_id}/assign    200
POST  /review/cases/{review_id}/priority  200/422
```

Creation, execution, assignment, and manual priority require the existing `review.execute` permission; finding and case decisions require the existing `review.decide` permission. Cross-case access is filtered in repository queries rather than checked after loading unrelated data.

Run: `rtk docker compose run --rm api pytest app/review/tests/test_sorting.py app/review/tests/test_service.py app/review/tests/test_cases_api.py -q`

- [ ] **Step 6: Commit the queue slice**

```powershell
rtk git add app/review
rtk git commit -m "feat(review): add review queue and prioritization"
```

---

### Task 4: Implement Completeness, Rule Selection, and Missing Materials

**Files:**
- Create: `app/review/completeness.py`
- Create: `app/review/rule_selection.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/service.py`
- Modify: `app/review/router.py`
- Create: `app/review/tests/test_completeness.py`
- Create: `app/review/tests/test_rule_selection.py`
- Create: `app/review/tests/test_missing_items_api.py`

**Interfaces:**
- Produces: `CompletenessResult`, `MissingRequirement`, `evaluate_completeness()`, and `select_effective_rule()`.

- [ ] **Step 1: Write failing completeness tests**

```python
def test_missing_land_register_blocks_core_recalculation():
    result = evaluate_completeness(case_snapshot_without_land_register)
    assert result.ready is False
    assert result.blocked_rule_codes == {"PARCEL_AREA_MATCH", "PRICE_RECALCULATION"}
    assert result.items[0].document_category == "land-register"

def test_current_document_versions_satisfy_requirements():
    result = evaluate_completeness(complete_case_snapshot)
    assert result.ready is True
    assert result.items == ()
```

- [ ] **Step 2: Implement pure completeness evaluation and verify GREEN**

The public function is `evaluate_completeness(snapshot: CaseInputSnapshot, requirements: Sequence[Requirement] = MVP_REQUIREMENTS) -> CompletenessResult`. It compares only active latest document versions and normalized fields, returns immutable tuples, and computes `blocked_rule_codes` as the union of codes attached to missing requirements.

The MVP requirements are `original`, `land-register`, `cadastral-map`, and required normalized fields `case_no`, `valuation_base_date`, `district_code`, `parcel_area`.

- [ ] **Step 3: Write failing effective-rule tests**

Require a rule only when status is `PUBLISHED`, `effective_from <= valuation_base_date`, `effective_to` is null or not before the base date, and case type/district/form code match. Ambiguous highest-priority matches raise `RULE_SELECTION_CONFLICT` with `409`; no match creates a reviewer-visible `REQUIRES_EXPERT_JUDGMENT` result rather than inventing a rule.

- [ ] **Step 4: Implement missing-item persistence and APIs**

Add:

```text
POST /review/cases/{review_id}/completeness-check
GET  /review/cases/{review_id}/missing-items
POST /review/cases/{review_id}/supplement-request
```

The check upserts open missing requirements without overwriting resolved history, updates `missing_item_count`, and moves the case to `PENDING_MATERIALS` or `READY_FOR_REVIEW`.

- [ ] **Step 5: Verify selected tests and commit**

Run: `rtk docker compose run --rm api pytest app/review/tests/test_completeness.py app/review/tests/test_rule_selection.py app/review/tests/test_missing_items_api.py -q`

```powershell
rtk git add app/review
rtk git commit -m "feat(review): add completeness and rule selection"
```

---

### Task 5: Implement Deterministic Recalculation, Findings, and Risk

**Files:**
- Create: `app/review/recalculation.py`
- Create: `app/review/ai.py`
- Create: `app/review/risks.py`
- Modify: `app/review/schemas.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/service.py`
- Modify: `app/review/router.py`
- Create: `app/review/tests/test_recalculation.py`
- Create: `app/review/tests/test_ai.py`
- Create: `app/review/tests/test_risks.py`
- Create: `app/review/tests/test_runs_api.py`

**Interfaces:**
- Produces: `recalculate_adjustment_rate()`, `recalculate_weighted_price()`, `grade_for_value()`, `risk_level_for_findings()`, run and finding APIs.

- [ ] **Step 1: Write failing Decimal calculation tests**

```python
def test_adjustment_rate_is_quantized_without_float():
    result = recalculate_adjustment_rate(Decimal("-12"), Decimal("-5"), Decimal("0"))
    assert result.system_rate == Decimal("-5.00")
    assert result.difference == Decimal("-7.00")
    assert result.within_tolerance is False

def test_weighted_price_preserves_unrounded_and_final_values():
    result = recalculate_weighted_price(((Decimal("101.11"), Decimal("0.6")), (Decimal("99.99"), Decimal("0.4"))))
    assert result.unrounded == Decimal("100.662")
    assert result.final == Decimal("100.66")
```

- [ ] **Step 2: Implement minimal calculation functions and verify GREEN**

Reject weights not summing to `Decimal("1.000000")` within the explicit tolerance and never coerce through `float`.

- [ ] **Step 3: Write failing risk tests and implement hard rules**

`MISSING_DATA` remains a processing state. Otherwise the case risk is the highest unresolved severity. Wrong legal basis, opposite direction, out-of-range rate, price/formula mismatch, and critical source contradiction are `HIGH`; expert-grade judgment is at least `MEDIUM`.

- [ ] **Step 4: Write failing Bedrock structured-output tests**

Inject a fake Bedrock runtime client and require `BedrockFindingExplainer.explain(input: FindingExplanationInput) -> AIExplanation` to send only evidence IDs, excerpts, reported values, verified legal sources, and deterministic calculation results. Validate the response with Pydantic fields `reasoning_summary`, `recommended_action`, `confidence`, `model_id`, `prompt_version`, and `generated_at`. Reject unknown source IDs and invented page/article references. Timeout, throttling, malformed JSON, or schema failure returns `AIExplanationUnavailable` without removing the deterministic finding.

- [ ] **Step 5: Implement the minimal Bedrock adapter and verify GREEN**

Use `boto3.client("bedrock-runtime").converse(**request)` behind constructor injection. The adapter never receives an `AsyncSession`, never calculates authoritative numbers, and never persists hidden model reasoning. The service writes only the validated public summary and metadata to `review.findings`.

- [ ] **Step 6: Implement run orchestration and finding contract**

Add:

```text
POST /review/cases/{review_id}/runs              202/409
GET  /review/cases/{review_id}/runs              200
GET  /review/runs/{validation_run_id}             200/404
GET  /review/runs/{validation_run_id}/findings    200
GET  /review/findings/{finding_id}                200/404
GET  /review/runs/{validation_run_id}/risk-summary 200
```

Each finding response contains all ten design fields. Creating a run first locks the review row and checks the partial unique running-run rule. Machine evidence is inserted before reviewer finding records. AI fields may be null with `ai_status = "AI_EXPLANATION_UNAVAILABLE"`; deterministic findings remain queryable.

- [ ] **Step 7: Verify selected tests and commit**

Run: `rtk docker compose run --rm api pytest app/review/tests/test_recalculation.py app/review/tests/test_ai.py app/review/tests/test_risks.py app/review/tests/test_runs_api.py -q`

```powershell
rtk git add app/review
rtk git commit -m "feat(review): add deterministic findings and risk"
```

---

### Task 6: Implement Reviewer Decisions and Reruns

**Files:**
- Create: `app/review/decisions.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/service.py`
- Modify: `app/review/router.py`
- Create: `app/review/tests/test_decisions.py`
- Create: `app/review/tests/test_rerun.py`

**Interfaces:**
- Produces: `validate_finding_decision()`, `validate_case_decision()`, decision APIs, and append-only rerun linkage.

- [ ] **Step 1: Write failing decision tests**

Test `ACCEPTED`, `PARTIALLY_ACCEPTED`, `REJECTED`, `REQUIRES_SUPPLEMENT`, and `EXPERT_REVIEW`. Every decision requires a nonblank reason; partial acceptance additionally requires `after_value`. A case with unresolved high-risk findings cannot become `APPROVED` unless the actor has the explicit override permission and supplies an override reason.

- [ ] **Step 2: Implement decision validation and verify GREEN**

The exact public interfaces are `validate_finding_decision(command: FindingDecisionCommand) -> FindingStatus` and `validate_case_decision(command: CaseDecisionCommand, summary: ReviewGateSummary) -> str`. Both return the resulting status and raise `AppError(code="REVIEW_DECISION_INVALID", status_code=409)` for failed gates.

- [ ] **Step 3: Add decision and rerun APIs**

```text
POST /review/findings/{finding_id}/decisions
POST /review/cases/{review_id}/decision
GET  /review/cases/{review_id}/decisions
POST /review/cases/{review_id}/rerun
```

The repository verifies `finding.review_id == review_id`, records `request_id`, before/after JSON, actor, and reason, and never updates existing decision rows. Rerun creates a new validation run, leaves previous rows untouched, and links replacement findings through `supersedes_finding_id`.

- [ ] **Step 4: Verify append-only behavior and commit**

Run: `rtk docker compose run --rm api pytest app/review/tests/test_decisions.py app/review/tests/test_rerun.py -q`

```powershell
rtk git add app/review
rtk git commit -m "feat(review): add decisions and rerun history"
```

---

### Task 7: Assemble Structured Reports and Verify the End-to-End Workflow

**Files:**
- Create: `app/review/reports.py`
- Create: `app/review/pdf_reports.py`
- Modify: `app/review/schemas.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/router.py`
- Create: `app/review/tests/test_reports.py`
- Create: `app/review/tests/test_pdf_reports.py`
- Create: `app/review/tests/test_workflow_e2e.py`

**Interfaces:**
- Produces: `build_review_report()` and `GET /review/runs/{validation_run_id}/report`.

- [ ] **Step 1: Write the failing report contract test**

```python
def test_report_keeps_machine_ai_and_human_records_separate(report_fixture):
    report = build_review_report(report_fixture)
    assert report.run.validation_run_id == report_fixture.run_id
    assert report.findings[0].source_evidence
    assert report.findings[0].ai_assessment.reasoning_summary
    assert report.findings[0].decisions[0].reason == "現勘資料支持部分調整"
    assert report.risk_summary.high_count == 1
```

- [ ] **Step 2: Implement report assembly and verify GREEN**

The report includes case metadata, run/rule/model/prompt versions, completeness status, all ten finding fields, AI availability, risk counts/reasons, and append-only decisions. It does not expose hidden model reasoning, credentials, object-store endpoints, or presigned URLs.

- [ ] **Step 3: Write the failing simplified-PDF test, implement, and verify GREEN**

Require `build_review_pdf(report: ReviewReport) -> bytes` to return bytes starting with `%PDF`, include the case number, run number, risk summary, and one row per finding, and never include credentials or object-store endpoints. Use ReportLab with an in-memory `BytesIO`; the router uploads the result through the existing `StorageService` to `cases/{case_id}/generated/{document_id}/v{version}/review-report.pdf`, then stores only bucket/object metadata in PostgreSQL.

Add:

```text
POST /review/runs/{validation_run_id}/report/pdf
GET  /review/runs/{validation_run_id}/report/pdf/download
```

- [ ] **Step 4: Write and run the fixed-case end-to-end test**

The test must execute this sequence through service or HTTP boundaries:

```text
create review
→ completeness check reports missing land register
→ add a new document version fixture
→ completeness check becomes ready
→ run creates one HIGH and one MEDIUM finding
→ reviewer partially accepts HIGH finding with reason
→ case returns for revision
→ rerun creates a new run and superseding finding
→ old run/finding/decision remain queryable
→ new finding is resolved
→ structured report is internally consistent
```

- [ ] **Step 5: Run all old and new tests**

Run: `rtk docker compose run --rm api pytest tests app/review/tests -q`

Expected: zero failures; existing health, auth, error, permission, and storage tests remain green.

- [ ] **Step 6: Run service and migration verification**

Run: `rtk docker compose up -d --build`

Run: `rtk docker compose ps -a`

Run: `rtk docker compose run --rm migrate alembic current`

Expected: PostgreSQL, MinIO, and API are healthy; migrate/minio-init exit 0; Alembic current is `20260825_0005`.

- [ ] **Step 7: Inspect scope before final commit**

Run: `rtk git diff --name-only 64bac88..HEAD`

Expected after Task 2: every newly changed product path is under `app/review/**`; the only product-code/configuration exceptions are `requirements.txt`, `migrations/versions/20260825_0005_expand_review_workflow.py`, and `app/api/router.py`. The approved design and plan files under `docs/superpowers/**` are documentation exceptions created before Task 2.

- [ ] **Step 8: Commit the report and workflow slice**

```powershell
rtk git add app/review
rtk git commit -m "feat(review): add structured report workflow"
```

---

## Completion Evidence

Before claiming the MVP complete, record fresh output for:

```powershell
rtk docker compose run --rm api pytest tests app/review/tests -q
rtk docker compose run --rm migrate alembic current
rtk docker compose ps -a
rtk git status
rtk git diff --name-only 64bac88..HEAD
```

Completion requires zero test failures, migration at `20260825_0005`, healthy PostgreSQL/MinIO/API, no unintended working-tree changes, and no post-Task-2 edits outside `app/review/**`.
