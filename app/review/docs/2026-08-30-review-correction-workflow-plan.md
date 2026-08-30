# Review Correction Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace reviewer-selected formal values with an auditable finding-triage and correction-request loop, add deadline urgency, recheck revised appraisal versions, and export immutable Excel and Word risk reports.

**Architecture:** Keep the existing Review run, Finding, Decision, version-lineage, MinIO, and atomic-completion foundations. Add focused correction domain/repository/service modules, two Review-owned tables plus urgency settings, and format-specific report builders. The appraisal subsystem remains responsible for changing reports and official values; Review accepts only a same-case newer document version and never accepts a reviewer-supplied formal value.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL, Alembic, MinIO, pytest, openpyxl, python-docx, vanilla HTML/JavaScript test workbench.

## Global Constraints

- The approved specification is `app/review/docs/2026-08-30-review-correction-request-workflow-design.md`.
- Review detects, confirms, reports, and rechecks problems; it never edits an appraisal report or chooses a formal appraisal value.
- New triage decisions are exactly `CONFIRMED_ISSUE`, `DISMISSED_FALSE_POSITIVE`, and `EXPERT_REVIEW`; `reason` is required and `after_value` is forbidden.
- Existing `ACCEPTED`, `REJECTED`, `PARTIALLY_ACCEPTED`, `after_value`, and `selection_source` records remain readable as legacy history but cannot be created through the new workbench.
- Missing inputs block execution and create no Run.
- A sent correction request has immutable case, Run, base-document, message, and item snapshots.
- A resubmission must identify a document owned by the same case, with a version greater than the request base version and valid lineage.
- Old Runs, Findings, Decisions, correction requests, report documents, and snapshots are never overwritten.
- Content risk and deadline urgency remain separate values. Defaults are `urgent_days=3` and `due_soon_days=7`, with `0 <= urgent_days < due_soon_days`.
- PostgreSQL stores structured data and file metadata; MinIO stores `.xlsx`, `.docx`, PDF, images, and attachments.
- API responses never expose MinIO bucket names, object keys, or fixed localhost URLs.
- Completion is one reviewer action. The server locks the case, revalidates every gate, records the audit Decision, and sets `REVIEW_COMPLETED` in one transaction.
- Do not modify or stage the user-owned untracked `app/review/DEMO_GUIDE.md` without separate approval.
- Do not push, merge, delete, or clean `feature/review`.
- Use TDD for every behavior change and run fresh full-suite evidence before claiming completion.

## Authorization Gate Before Execution

Tasks 2 and 7 require files outside `app/review/**`:

- `migrations/versions/20260830_0008_add_review_correction_workflow.py`
- `requirements.txt`

Before implementing either task, obtain explicit user approval to modify those exact paths. If approval is not granted, stop after Task 1 and report that the database-backed workflow and Excel/Word exports cannot be completed safely inside `app/review/**` alone.

## Planned File Structure

### Create

- `app/review/corrections.py`: pure correction gates, enums, and immutable snapshot helpers.
- `app/review/correction_repository.py`: correction-request, item, settings, and resubmission persistence.
- `app/review/correction_service.py`: transactional orchestration for draft, send, resubmit, recheck, and completion.
- `app/review/urgency.py`: deadline urgency calculation and queue ranking primitives.
- `app/review/xlsx_reports.py`: pure `.xlsx` renderer.
- `app/review/docx_reports.py`: pure `.docx` renderer.
- `app/review/tests/test_corrections.py`: pure correction-domain tests.
- `app/review/tests/test_correction_service.py`: service and repository behavior tests.
- `app/review/tests/test_correction_api.py`: HTTP contract and authorization tests.
- `app/review/tests/test_urgency.py`: urgency boundary and settings tests.
- `app/review/tests/test_xlsx_reports.py`: workbook structure and content tests.
- `app/review/tests/test_docx_reports.py`: document structure and content tests.
- `migrations/versions/20260830_0008_add_review_correction_workflow.py`: tables, constraints, indexes, and compatible status values; requires authorization.

### Modify

- `app/review/models.py`: map correction requests, items, and urgency settings.
- `app/review/schemas.py`: triage, correction, urgency, resubmission, safe report metadata, and API response models.
- `app/review/decisions.py`: remove new formal-value semantics and define triage/completion gates while retaining legacy readers.
- `app/review/repository.py`: update latest-run risk counts and add safe report metadata helpers.
- `app/review/service.py`: expose triage and reusable run/report primitives to the focused correction service.
- `app/review/router.py`: add correction, settings, recheck, completion, and `xlsx`/`docx` routes; remove object-storage details from responses.
- `app/review/reports.py`: add correction history, urgency, document version, and immutable report context.
- `app/review/sorting.py`: delegate deadline classification to `urgency.py` and preserve deterministic queue ordering.
- `app/review/workbench_repository.py`: return risk counts, deadline inputs, correction round, and latest request state.
- `app/review/workbench_schemas.py`: expose urgency and correction workflow fields.
- `app/review/workbench_service.py`: aggregate correction requests and report metadata.
- `app/review/test_ui/index.html`: replace formal-value controls with triage, correction, recheck, and report tabs.
- Existing Review tests: replace old-new-flow expectations while retaining explicit legacy-read compatibility cases.
- `app/review/CHANGELOG.md`: document the new Review responsibility boundary and compatibility behavior.
- `requirements.txt`: add openpyxl and python-docx; requires authorization.

---

### Task 1: Introduce Finding Triage Semantics Without Wiring Routes

**Files:**
- Modify: `app/review/decisions.py`
- Modify: `app/review/schemas.py`
- Modify: `app/review/tests/test_decisions.py`
- Modify: `app/review/tests/test_schema_contract.py`

**Interfaces:**
- Produces: `FindingTriageDecision`, `FindingTriageCommand`, `validate_finding_triage(command) -> str`.
- Produces: `FindingTriageRequest` with `extra="forbid"`, so `after_value` is rejected before service execution.
- Preserves: existing `DecisionRead` and stored legacy values for read-only history.

- [ ] **Step 1: Replace new-flow decision tests with failing triage tests**

```python
import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.review.decisions import FindingTriageCommand, validate_finding_triage
from app.review.schemas import FindingTriageRequest


@pytest.mark.parametrize(
    "decision",
    ["CONFIRMED_ISSUE", "DISMISSED_FALSE_POSITIVE", "EXPERT_REVIEW"],
)
def test_finding_triage_accepts_only_review_meaning(decision):
    assert validate_finding_triage(FindingTriageCommand(decision, "已核對證據")) == decision


def test_finding_triage_requires_reason():
    with pytest.raises(AppError, match="必須填寫理由"):
        validate_finding_triage(FindingTriageCommand("CONFIRMED_ISSUE", "   "))


@pytest.mark.parametrize("legacy", ["ACCEPTED", "REJECTED", "PARTIALLY_ACCEPTED"])
def test_new_triage_schema_rejects_legacy_value_choices(legacy):
    with pytest.raises(ValidationError):
        FindingTriageRequest(review_id="00000000-0000-0000-0000-000000000001", decision=legacy, reason="x")


def test_new_triage_schema_rejects_after_value():
    with pytest.raises(ValidationError):
        FindingTriageRequest(
            review_id="00000000-0000-0000-0000-000000000001",
            decision="CONFIRMED_ISSUE",
            reason="x",
            after_value={"value": "不得接受"},
        )
```

- [ ] **Step 2: Run the focused tests and verify the new interfaces are absent**

Run:

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_decisions.py app/review/tests/test_schema_contract.py -q
```

Expected: FAIL because `FindingTriageCommand`, `validate_finding_triage`, and `FindingTriageRequest` do not exist.

- [ ] **Step 3: Add the minimal triage domain**

```python
# app/review/decisions.py
FindingTriageDecision = Literal[
    "CONFIRMED_ISSUE",
    "DISMISSED_FALSE_POSITIVE",
    "EXPERT_REVIEW",
]


@dataclass(frozen=True)
class FindingTriageCommand:
    decision: FindingTriageDecision
    reason: str


def validate_finding_triage(command: FindingTriageCommand) -> str:
    if not command.reason.strip():
        raise AppError("REVIEW_DECISION_INVALID", "人工判定必須填寫理由", 409)
    return command.decision
```

```python
# app/review/schemas.py
FindingTriageDecision = Literal[
    "CONFIRMED_ISSUE",
    "DISMISSED_FALSE_POSITIVE",
    "EXPERT_REVIEW",
]


class FindingTriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: UUID
    decision: FindingTriageDecision
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason 不得為空白")
        return value
```

Keep the legacy request model only under a legacy-specific name if an existing compatibility test needs to deserialize old payloads. Do not leave it connected to a write route.

- [ ] **Step 4: Run focused tests and the existing decision unit suite**

Run the Step 2 command again.

Expected: PASS with no accepted new-flow `after_value` payload.

- [ ] **Step 5: Commit the triage domain**

```bash
git add app/review/decisions.py app/review/schemas.py app/review/tests/test_decisions.py app/review/tests/test_schema_contract.py
git commit -m feat-review-finding-triage-domain
```

---

### Task 2: Add Correction and Urgency Persistence

**Authorization required before this task:** `migrations/versions/**` is outside `app/review/**`.

**Files:**
- Create: `migrations/versions/20260830_0008_add_review_correction_workflow.py`
- Modify: `app/review/models.py`
- Modify: `app/review/tests/test_schema_contract.py`

**Interfaces:**
- Produces ORM models: `CorrectionRequest`, `CorrectionRequestItem`, `UrgencySettings`.
- Produces database uniqueness for `(review_id, request_no)` and one non-`RECHECKED` request per Review, including drafts.
- Extends finding and decision CHECK constraints without deleting legacy values.

- [ ] **Step 1: Write failing schema-contract tests**

```python
@pytest.mark.parametrize(
    ("schema", "table", "column"),
    [
        ("review", "correction_requests", "based_on_validation_run_id"),
        ("review", "correction_requests", "response_document_id"),
        ("review", "correction_request_items", "recheck_outcome"),
        ("review", "urgency_settings", "urgent_days"),
    ],
)
def test_correction_schema_columns_exist(postgres_connection, schema, table, column):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s AND column_name=%s
            """,
            (schema, table, column),
        )
        assert cursor.fetchone() == (1,)
```

Add a test that inserting a second active request for the same `review_id` fails, while any number of `RECHECKED` historical requests is allowed.

- [ ] **Step 2: Run migration tests before creating revision 0008**

Run:

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_schema_contract.py -q
```

Expected: FAIL because the three new tables do not exist.

- [ ] **Step 3: Create revision 0008 with explicit constraints**

The migration must use `revision="20260830_0008"` and `down_revision="20260825_0007"`. Its `upgrade()` must:

```sql
CREATE TABLE review.correction_requests (
    correction_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL REFERENCES review.reviews(review_id) ON DELETE RESTRICT,
    request_no integer NOT NULL CHECK (request_no > 0),
    based_on_validation_run_id uuid NOT NULL REFERENCES valuation.validation_runs(validation_run_id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','SENT','RESUBMITTED','RECHECKING','RECHECKED')),
    due_at timestamptz NOT NULL,
    message text NOT NULL CHECK (nullif(btrim(message), '') IS NOT NULL),
    base_document_id uuid NOT NULL REFERENCES valuation.documents(document_id) ON DELETE RESTRICT,
    base_document_version integer NOT NULL CHECK (base_document_version > 0),
    response_document_id uuid REFERENCES valuation.documents(document_id) ON DELETE RESTRICT,
    response_document_version integer CHECK (response_document_version > base_document_version),
    created_by_user_id uuid NOT NULL REFERENCES auth.users(user_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE RESTRICT,
    sent_at timestamptz,
    resubmitted_at timestamptz,
    rechecked_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE RESTRICT,
    rechecked_at timestamptz,
    UNIQUE (review_id, request_no)
);

CREATE UNIQUE INDEX uq_review_correction_one_active
ON review.correction_requests(review_id)
WHERE status <> 'RECHECKED';
```

Create the item and settings tables exactly as follows:

```sql
CREATE TABLE review.correction_request_items (
    correction_request_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    correction_request_id uuid NOT NULL
        REFERENCES review.correction_requests(correction_request_id) ON DELETE RESTRICT,
    finding_id uuid NOT NULL REFERENCES review.findings(finding_id) ON DELETE RESTRICT,
    finding_code varchar(100) NOT NULL,
    finding_type varchar(50) NOT NULL,
    severity varchar(20) NOT NULL,
    document_id uuid REFERENCES valuation.documents(document_id) ON DELETE RESTRICT,
    document_version integer CHECK (document_version IS NULL OR document_version > 0),
    page_number integer CHECK (page_number IS NULL OR page_number > 0),
    reported_text text,
    reported_value text,
    legal_basis_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_evidence_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    issue_summary text NOT NULL CHECK (nullif(btrim(issue_summary), '') IS NOT NULL),
    requested_correction text NOT NULL CHECK (nullif(btrim(requested_correction), '') IS NOT NULL),
    recheck_outcome varchar(20) NOT NULL DEFAULT 'PENDING'
        CHECK (recheck_outcome IN ('PENDING','RESOLVED','STILL_PRESENT','NOT_EVALUATED')),
    resulting_finding_id uuid REFERENCES review.findings(finding_id) ON DELETE RESTRICT,
    rechecked_at timestamptz,
    UNIQUE (correction_request_id, finding_id)
);

CREATE INDEX idx_correction_items_request_outcome
ON review.correction_request_items(correction_request_id, recheck_outcome);

CREATE TABLE review.urgency_settings (
    settings_id smallint PRIMARY KEY CHECK (settings_id = 1),
    urgent_days integer NOT NULL,
    due_soon_days integer NOT NULL,
    updated_by_user_id uuid REFERENCES auth.users(user_id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (urgent_days >= 0 AND urgent_days < due_soon_days)
);

INSERT INTO review.urgency_settings(settings_id, urgent_days, due_soon_days)
VALUES (1, 3, 7)
ON CONFLICT (settings_id) DO NOTHING;
```

Add a paired-response CHECK so `response_document_id` and `response_document_version` are either both null or both present. Add timestamp/status consistency CHECKs: `DRAFT` has no `sent_at`; every later status has `sent_at`; `RESUBMITTED` and later have response fields plus `resubmitted_at`; only `RECHECKED` has `rechecked_by_user_id` and `rechecked_at`.

Create singleton `review.urgency_settings` with `settings_id=1`, `urgent_days`, `due_soon_days`, updater and timestamp, plus `CHECK (urgent_days >= 0 AND urgent_days < due_soon_days)`. Seed `(1,3,7)` with `ON CONFLICT DO NOTHING`.

Replace `ck_findings_status` and `ck_decisions_value` with supersets that add the three new triage values while retaining every existing accepted legacy value. The downgrade must first fail closed if correction rows or new decision/status values exist, then restore the exact 0007-compatible constraints.

- [ ] **Step 4: Add matching ORM models**

```python
class CorrectionRequest(Base):
    __tablename__ = "correction_requests"
    __table_args__ = {"schema": "review"}
    correction_request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_no: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_validation_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="DRAFT")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    base_document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    base_document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    response_document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    response_document_version: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    sent_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resubmitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rechecked_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    rechecked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Add the remaining approved item and settings mappings with exact database column names.

- [ ] **Step 5: Upgrade, run schema tests, downgrade, and upgrade again**

Run:

```bash
docker compose --env-file .env.example exec -T api alembic upgrade head
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_schema_contract.py -q
docker compose --env-file .env.example exec -T api alembic downgrade 20260825_0007
docker compose --env-file .env.example exec -T api alembic upgrade head
```

Expected: every command exits 0; the focused schema tests pass; the database returns to revision `20260830_0008`.

- [ ] **Step 6: Commit persistence**

```bash
git add migrations/versions/20260830_0008_add_review_correction_workflow.py app/review/models.py app/review/tests/test_schema_contract.py
git commit -m feat-review-correction-persistence
```

---

### Task 3: Wire Triage Into Service, Risk Counts, and API

**Files:**
- Modify: `app/review/service.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/router.py`
- Modify: `app/review/tests/test_service.py`
- Modify: `app/review/tests/test_router.py`
- Create: `app/review/tests/test_correction_api.py`

**Interfaces:**
- Consumes: `FindingTriageRequest`, `FindingTriageCommand`, `validate_finding_triage`.
- Produces: `ReviewService.triage_finding(finding_id, payload, actor_id, request_id) -> Decision`.
- Produces route: `POST /api/v1/review/findings/{finding_id}/triage`.

- [ ] **Step 1: Write failing service and HTTP tests**

```python
def test_triage_confirmed_issue_writes_no_formal_value(review_client, open_finding):
    response = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "CONFIRMED_ISSUE",
            "reason": "與適用規則不一致",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "CONFIRMED_ISSUE"
    assert body["after_value"] == {"status": "CONFIRMED_ISSUE"}
    assert "value" not in body["after_value"]


def test_triage_route_rejects_after_value(review_client, open_finding):
    response = review_client.post(
        f"/api/v1/review/findings/{open_finding.finding_id}/triage",
        json={
            "review_id": str(open_finding.review_id),
            "decision": "CONFIRMED_ISSUE",
            "reason": "x",
            "after_value": {"value": "45000"},
        },
    )
    assert response.status_code == 422
```

Add tests for false-positive exclusion from risk counts, expert-review inclusion, duplicate triage returning `FINDING_DECISION_CONFLICT`, cross-review finding rejection, and legacy `/decisions` write attempts returning a documented 409 compatibility error.

- [ ] **Step 2: Run focused tests to see route and service failures**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_service.py app/review/tests/test_router.py app/review/tests/test_correction_api.py -q
```

Expected: FAIL because the triage route and service do not exist.

- [ ] **Step 3: Implement `triage_finding` transactionally**

```python
async def triage_finding(self, finding_id, payload, actor_id, request_id):
    review = await self.repository.get(payload.review_id, for_update=True)
    if review is None:
        raise ResourceNotFoundError("審查案件")
    if review.review_status not in {"REVIEW_REQUIRED", "EXPERT_REVIEW"}:
        raise AppError("REVIEW_STATE_CONFLICT", "目前案件不可判定疑點", 409)
    finding = await self.repository.get_finding_for_review(finding_id, payload.review_id, for_update=True)
    if finding is None:
        raise ResourceNotFoundError("審查疑點")
    if finding.validation_run_id != review.latest_validation_run_id or finding.status != "OPEN":
        raise AppError("FINDING_DECISION_CONFLICT", "疑點不是最新待判定項目", 409)
    status = validate_finding_triage(FindingTriageCommand(payload.decision, payload.reason))
    finding.status = status
    decision = await self.repository.create_decision(
        review_id=review.review_id,
        finding_id=finding.finding_id,
        decision=status,
        reason=payload.reason.strip(),
        decided_by_user_id=actor_id,
        request_id=request_id,
        before_value={"status": "OPEN"},
        after_value={"status": status},
    )
    await self._refresh_review_risk_counts(review)
    return decision
```

Update risk queries so `OPEN`, `CONFIRMED_ISSUE`, and `EXPERT_REVIEW` count as unresolved; `DISMISSED_FALSE_POSITIVE` does not. Retain legacy unresolved statuses only for legacy latest Runs.

- [ ] **Step 4: Add the triage route and close the old write route**

Wire `FindingTriageRequest` to `/triage` with `review.decide`. Keep the old Decision list/read route. If the old POST route must remain for compatibility, make it return 409 `LEGACY_FINDING_DECISION_DISABLED` for new requests instead of calling `decide_finding`.

- [ ] **Step 5: Run focused and legacy-read tests**

Run the Step 2 command plus:

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_reports.py app/review/tests/test_workbench_service.py -q
```

Expected: PASS; legacy records still serialize, but no write path accepts a formal value.

- [ ] **Step 6: Commit triage wiring**

```bash
git add app/review/service.py app/review/repository.py app/review/router.py app/review/tests/test_service.py app/review/tests/test_router.py app/review/tests/test_correction_api.py
git commit -m feat-review-triage-api
```

---

### Task 4: Build Correction Draft and Send Workflow

**Files:**
- Create: `app/review/corrections.py`
- Create: `app/review/correction_repository.py`
- Create: `app/review/correction_service.py`
- Create: `app/review/tests/test_corrections.py`
- Create: `app/review/tests/test_correction_service.py`
- Modify: `app/review/schemas.py`
- Modify: `app/review/router.py`
- Modify: `app/review/tests/test_correction_api.py`

**Interfaces:**
- Produces: `CorrectionGateSummary`, `validate_correction_send(summary) -> None`.
- Produces: `CorrectionService.create_draft(review_id, payload, actor_id)` and `CorrectionService.send(request_id, actor_id, audit_request_id)`.
- Produces: correction request/item read schemas and routes.

- [ ] **Step 1: Write failing pure gate tests**

```python
@pytest.mark.parametrize(
    "summary, blocker",
    [
        (CorrectionGateSummary(False, 0, 1, 0, False), "最新一次智慧審查尚未完成"),
        (CorrectionGateSummary(True, 1, 1, 0, False), "尚有 1 項疑點未判定"),
        (CorrectionGateSummary(True, 0, 0, 1, False), "尚有 1 項專業覆核"),
        (CorrectionGateSummary(True, 0, 0, 0, False), "沒有確認成立的疑點"),
        (CorrectionGateSummary(True, 0, 1, 0, True), "已有未完成修正通知"),
    ],
)
def test_correction_send_gate_rejects_each_blocker(summary, blocker):
    with pytest.raises(AppError) as error:
        validate_correction_send(summary)
    assert blocker in str(error.value.detail)
```

- [ ] **Step 2: Write failing service/API tests**

Cover server-selected latest-Run items, item snapshot completeness, request number increment, draft editability, send immutability, due date in the future, one active request, and atomic `RETURNED_FOR_REVISION` transition.

```python
def test_create_draft_snapshots_only_confirmed_findings(review_client, triaged_case):
    response = review_client.post(
        f"/api/v1/review/cases/{triaged_case.review_id}/correction-requests",
        json={"message": "請依附件疑點修正", "due_at": triaged_case.future_due_at.isoformat()},
    )
    assert response.status_code == 201
    assert {item["finding_id"] for item in response.json()["items"]} == {
        str(triaged_case.confirmed_finding_id)
    }
```

- [ ] **Step 3: Run correction tests and verify failure**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_corrections.py app/review/tests/test_correction_service.py app/review/tests/test_correction_api.py -q
```

Expected: FAIL because correction modules and routes do not exist.

- [ ] **Step 4: Implement pure gates and snapshot builder**

```python
@dataclass(frozen=True)
class CorrectionGateSummary:
    has_completed_run: bool
    open_count: int
    confirmed_count: int
    expert_count: int
    has_active_request: bool


def validate_correction_send(summary: CorrectionGateSummary) -> None:
    blockers = []
    if not summary.has_completed_run:
        blockers.append("最新一次智慧審查尚未完成")
    if summary.open_count:
        blockers.append(f"尚有 {summary.open_count} 項疑點未判定")
    if summary.expert_count:
        blockers.append(f"尚有 {summary.expert_count} 項專業覆核")
    if not summary.confirmed_count:
        blockers.append("沒有確認成立的疑點")
    if summary.has_active_request:
        blockers.append("已有未完成修正通知")
    if blockers:
        raise AppError("CORRECTION_REQUEST_BLOCKED", "；".join(blockers), 409, {"blockers": blockers})
```

Create item snapshots from server-loaded Findings. Do not accept `finding_ids`, evidence, legal basis, original value, or document key from the client.

- [ ] **Step 5: Implement focused repository and service methods**

`CorrectionRepository` must provide exact methods:

```python
async def next_request_no(self, review_id: UUID) -> int
async def active_for_review(self, review_id: UUID, for_update: bool = False) -> CorrectionRequest | None
async def create_request(self, **values) -> CorrectionRequest
async def create_items(self, rows: list[dict]) -> list[CorrectionRequestItem]
async def get_request(self, correction_request_id: UUID, for_update: bool = False) -> CorrectionRequest | None
async def list_items(self, correction_request_id: UUID) -> list[CorrectionRequestItem]
```

`CorrectionService.send()` must lock Review and request, recompute the gate from current database state, ensure the request is `DRAFT` and based on the latest completed Run, set `SENT` fields, create one case-level `RETURNED_FOR_REVISION` Decision, and update Review status in one transaction.

- [ ] **Step 6: Add schemas and routes**

```python
class CorrectionRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    due_at: datetime


class CorrectionRequestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    correction_request_item_id: UUID
    finding_id: UUID
    finding_code: str
    finding_type: str
    severity: str
    document_id: UUID | None
    document_version: int | None
    page_number: int | None
    reported_text: str | None
    reported_value: str | None
    legal_basis_snapshot: list
    source_evidence_snapshot: list
    issue_summary: str
    requested_correction: str
    recheck_outcome: str
    resulting_finding_id: UUID | None
    rechecked_at: datetime | None


class CorrectionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    correction_request_id: UUID
    review_id: UUID
    request_no: int
    based_on_validation_run_id: UUID
    status: str
    due_at: datetime
    message: str
    base_document_id: UUID
    base_document_version: int
    items: list[CorrectionRequestItemRead]
```

Add `POST /cases/{review_id}/correction-requests`, `GET /correction-requests/{id}`, and `POST /correction-requests/{id}/send` with `review.decide`.

- [ ] **Step 7: Run focused tests**

Run the Step 3 command.

Expected: PASS, including repeated-send 409 and unchanged snapshots after send.

- [ ] **Step 8: Commit correction draft/send**

```bash
git add app/review/corrections.py app/review/correction_repository.py app/review/correction_service.py app/review/schemas.py app/review/router.py app/review/tests/test_corrections.py app/review/tests/test_correction_service.py app/review/tests/test_correction_api.py
git commit -m feat-review-correction-requests
```

---

### Task 5: Register Revised Documents, Recheck, and Complete

**Files:**
- Modify: `app/review/correction_repository.py`
- Modify: `app/review/correction_service.py`
- Modify: `app/review/corrections.py`
- Modify: `app/review/schemas.py`
- Modify: `app/review/router.py`
- Modify: `app/review/service.py`
- Modify: `app/review/tests/test_correction_service.py`
- Modify: `app/review/tests/test_correction_api.py`
- Modify: `app/review/tests/test_workflow_e2e.py`

**Interfaces:**
- Produces: `register_resubmission(request_id, payload, actor_id)`.
- Produces: `recheck(request_id, actor_id) -> tuple[ValidationRun, RiskSummary]`.
- Produces: `complete_review(review_id, reason, actor_id, audit_request_id) -> Decision`.
- Produces: `ReviewCompletionSummary` and `validate_review_completion(reason, summary) -> None`.

- [ ] **Step 1: Write failing ownership and version tests**

```python
@pytest.mark.parametrize("document_case", ["other-case", "same-case-wrong-lineage"])
def test_resubmission_rejects_wrong_document(review_client, sent_request, document_case):
    document = sent_request.documents[document_case]
    response = review_client.post(
        f"/api/v1/review/correction-requests/{sent_request.id}/resubmissions",
        json={"document_id": str(document.id), "document_version": document.version},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CORRECTION_RESUBMISSION_INVALID"
```

Add tests for equal/older version, duplicate resubmission, incomplete trusted fields, `SENT -> RESUBMITTED -> RECHECKING -> RECHECKED`, item outcomes, and history preservation.

- [ ] **Step 2: Write failing completion-gate tests**

Cover latest Run missing, open/confirmed/expert Finding, open missing items, active request, non-RECHECKED historical request, clean latest Run, case lock, and single audit Decision.

Add an HTTP test proving the legacy `POST /cases/{review_id}/decision` route cannot submit `RETURNED_FOR_REVISION`, `APPROVED`, or `REVIEW_COMPLETED` for the new workflow. Those state changes must occur only through correction send and `/complete-review`.

- [ ] **Step 3: Run the correction workflow tests**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_correction_service.py app/review/tests/test_correction_api.py app/review/tests/test_workflow_e2e.py -q
```

Expected: FAIL on missing resubmission, recheck, and completion methods.

- [ ] **Step 4: Implement resubmission validation**

```python
class CorrectionResubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    document_version: int = Field(gt=0)
```

The repository query must join the request Review to `valuation.documents` and require the same `case_id`, `is_active=true`, matching payload version, version greater than `base_document_version`, and the same `document_group_id` as the base document. Store only document ID/version and lifecycle timestamps; never accept extracted field values in this payload.

- [ ] **Step 5: Implement recheck and item outcome mapping**

Set `RECHECKING`, move the Review through `PREPROCESSING`, run existing completeness, and call the existing server-selected trusted-input `create_run`. If completeness blocks, revert the request to `RESUBMITTED` and return the normal missing-item response without creating a Run.

After a completed Run, map each request item:

```python
if resulting_finding is None:
    item.recheck_outcome = "RESOLVED"
    item.resulting_finding_id = None
else:
    item.recheck_outcome = "STILL_PRESENT"
    item.resulting_finding_id = resulting_finding.finding_id
item.rechecked_at = now
```

Use `supersedes_finding_id` first. If no unique supersedes link exists, match only a unique same `validation_rule_id`/finding code lineage; ambiguous matches become `NOT_EVALUATED` and block completion.

- [ ] **Step 6: Implement atomic manual completion**

Add the pure gate first:

```python
@dataclass(frozen=True)
class ReviewCompletionSummary:
    has_completed_run: bool
    open_missing_count: int
    open_finding_count: int
    confirmed_finding_count: int
    expert_finding_count: int
    active_request_count: int
    non_rechecked_request_count: int
    not_evaluated_item_count: int


def validate_review_completion(reason: str, summary: ReviewCompletionSummary) -> None:
    blockers = []
    if not reason.strip():
        blockers.append("完成審查必須填寫理由")
    if not summary.has_completed_run:
        blockers.append("最新一次智慧審查尚未完成")
    if summary.open_missing_count:
        blockers.append(f"仍有 {summary.open_missing_count} 項缺件")
    if summary.open_finding_count:
        blockers.append(f"仍有 {summary.open_finding_count} 項疑點未判定")
    if summary.confirmed_finding_count:
        blockers.append(f"仍有 {summary.confirmed_finding_count} 項疑點待修正")
    if summary.expert_finding_count:
        blockers.append(f"仍有 {summary.expert_finding_count} 項專業覆核")
    if summary.active_request_count or summary.non_rechecked_request_count:
        blockers.append("仍有修正通知尚未完成新版重檢")
    if summary.not_evaluated_item_count:
        blockers.append("仍有修正項目無法判定重檢結果")
    if blockers:
        raise AppError("REVIEW_COMPLETION_BLOCKED", "；".join(blockers), 409, {"blockers": blockers})
```

```python
async def complete_review(self, review_id, reason, actor_id, request_id):
    review = await self.review_repository.get(review_id, for_update=True)
    summary = await self._completion_gate(review)
    validate_review_completion(reason, summary)
    decision = await self.review_repository.create_decision(
        review_id=review.review_id,
        finding_id=None,
        decision="APPROVED",
        reason=reason.strip(),
        decided_by_user_id=actor_id,
        request_id=request_id,
        before_value={"review_status": review.review_status},
        after_value={
            "review_status": "REVIEW_COMPLETED",
            "validation_run_id": str(review.latest_validation_run_id),
        },
    )
    review.review_status = "REVIEW_COMPLETED"
    review.completed_at = datetime.now(UTC)
    return decision
```

Remove `invalid_value_count` from the new completion gate. Formal-value presence must never be a new-flow completion requirement.

Disable the legacy case-decision write path for new operations with 409 `LEGACY_CASE_DECISION_DISABLED`; keep Decision list/read serialization for historical rows. `RETURNED_FOR_REVISION` is created only by `CorrectionService.send()`, and completion is created only by `complete_review()`.

- [ ] **Step 7: Add routes and run focused tests**

Add resubmission, recheck, and `/cases/{review_id}/complete-review` routes with existing `review.execute`/`review.decide` permissions. Run the Step 3 command.

Expected: PASS; the end-to-end test shows old and new versions, Runs, Findings, requests, and Decisions all retained.

- [ ] **Step 8: Commit revised-document loop**

```bash
git add app/review/correction_repository.py app/review/correction_service.py app/review/corrections.py app/review/schemas.py app/review/router.py app/review/service.py app/review/tests/test_correction_service.py app/review/tests/test_correction_api.py app/review/tests/test_workflow_e2e.py
git commit -m feat-review-recheck-corrections
```

---

### Task 6: Add Configurable Deadline Urgency and Queue Ordering

**Files:**
- Create: `app/review/urgency.py`
- Create: `app/review/tests/test_urgency.py`
- Modify: `app/review/sorting.py`
- Modify: `app/review/correction_repository.py`
- Modify: `app/review/schemas.py`
- Modify: `app/review/router.py`
- Modify: `app/review/workbench_repository.py`
- Modify: `app/review/workbench_schemas.py`
- Modify: `app/review/workbench_service.py`
- Modify: `app/review/tests/test_sorting.py`
- Modify: `app/review/tests/test_workbench_api.py`

**Interfaces:**
- Produces: `UrgencyThresholds`, `UrgencyResult`, `classify_urgency(due_at, now, thresholds)`.
- Produces: settings GET/PUT and Workbench `urgency_level`, `remaining_days`, `correction_round`.

- [ ] **Step 1: Write failing boundary tests**

```python
@pytest.mark.parametrize(
    ("days", "level"),
    [(-1, "OVERDUE"), (0, "URGENT"), (3, "URGENT"), (4, "DUE_SOON"), (7, "DUE_SOON"), (8, "NORMAL")],
)
def test_urgency_boundaries(days, level):
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    result = classify_urgency(now + timedelta(days=days), now, UrgencyThresholds(3, 7))
    assert result.level == level
    assert result.remaining_days == days


def test_no_deadline_is_not_set():
    result = classify_urgency(None, datetime.now(UTC), UrgencyThresholds(3, 7))
    assert result == UrgencyResult("NOT_SET", None)
```

Add Pydantic tests for negative values, equal thresholds, and `urgent_days > due_soon_days`.

- [ ] **Step 2: Run urgency and sorting tests to verify failure**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_urgency.py app/review/tests/test_sorting.py app/review/tests/test_workbench_api.py -q
```

Expected: FAIL because urgency interfaces and response fields do not exist.

- [ ] **Step 3: Implement pure urgency calculation**

```python
@dataclass(frozen=True)
class UrgencyThresholds:
    urgent_days: int = 3
    due_soon_days: int = 7


@dataclass(frozen=True)
class UrgencyResult:
    level: Literal["OVERDUE", "URGENT", "DUE_SOON", "NORMAL", "NOT_SET"]
    remaining_days: int | None


def classify_urgency(due_at, now, thresholds):
    if due_at is None:
        return UrgencyResult("NOT_SET", None)
    days = (due_at - now).days
    if due_at < now:
        return UrgencyResult("OVERDUE", days)
    if days <= thresholds.urgent_days:
        return UrgencyResult("URGENT", days)
    if days <= thresholds.due_soon_days:
        return UrgencyResult("DUE_SOON", days)
    return UrgencyResult("NORMAL", days)
```

- [ ] **Step 4: Add settings persistence and API**

Add `get_urgency_settings(for_update=False)` and `update_urgency_settings(...)` to `CorrectionRepository`. Use `review.override_high_risk` as the existing supervisor-level permission for PUT; GET may use `review.execute`. Return exact fields without exposing updater internals unless needed for audit display.

- [ ] **Step 5: Update queue sorting and Workbench aggregation**

The deterministic key must be:

```python
URGENCY_RANK = {"OVERDUE": 0, "URGENT": 1, "DUE_SOON": 2, "NORMAL": 3, "NOT_SET": 4}
return (
    -item.manual_priority,
    URGENCY_RANK[item.urgency_level],
    -item.high_count,
    -item.medium_count,
    item.remaining_days if item.remaining_days is not None else 2**31 - 1,
    item.received_at,
)
```

Add `urgency_level`, `remaining_days`, and `correction_round` to `WorkbenchCaseListItem`. Compute at request time from one settings snapshot; do not persist daily urgency on Review rows.

- [ ] **Step 6: Run focused tests and commit**

Run the Step 2 command.

Expected: PASS for every boundary, settings validation, and queue ordering case.

```bash
git add app/review/urgency.py app/review/sorting.py app/review/correction_repository.py app/review/schemas.py app/review/router.py app/review/workbench_repository.py app/review/workbench_schemas.py app/review/workbench_service.py app/review/tests/test_urgency.py app/review/tests/test_sorting.py app/review/tests/test_workbench_api.py
git commit -m feat-review-deadline-urgency
```

---

### Task 7: Build Immutable Excel and Word Reports

**Authorization required before this task:** `requirements.txt` is outside `app/review/**`.

**Files:**
- Modify: `requirements.txt`
- Modify: `app/review/reports.py`
- Create: `app/review/xlsx_reports.py`
- Create: `app/review/docx_reports.py`
- Create: `app/review/tests/test_xlsx_reports.py`
- Create: `app/review/tests/test_docx_reports.py`
- Modify: `app/review/tests/test_reports.py`

**Interfaces:**
- Produces: `ReportUrgency`, `ReportCorrectionItem`, `ReportCorrectionRequest`, and expanded `ReviewReport` with urgency, document versions, requests, items, and history.
- Produces: `build_review_xlsx(report: ReviewReport) -> bytes`.
- Produces: `build_review_docx(report: ReviewReport) -> bytes`.

- [ ] **Step 1: Add pinned-compatible dependencies**

Add:

```text
openpyxl>=3.1,<4.0
python-docx>=1.1,<2.0
```

Rebuild only through the project’s normal Docker workflow; do not install undeclared global packages.

- [ ] **Step 2: Write failing Excel structure tests**

```python
from io import BytesIO
from openpyxl import load_workbook


def test_xlsx_has_required_sheets_and_no_macros(report_fixture):
    content = build_review_xlsx(report_fixture)
    workbook = load_workbook(BytesIO(content), data_only=False)
    assert workbook.sheetnames == ["案件摘要", "疑點與修正要求", "新版重檢結果", "審查歷程"]
    assert workbook.vba_archive is None


def test_xlsx_finding_rows_contain_evidence_not_formal_value(report_fixture):
    workbook = load_workbook(BytesIO(build_review_xlsx(report_fixture)))
    headers = [cell.value for cell in workbook["疑點與修正要求"][1]]
    assert "原報告頁碼" in headers
    assert "法規依據" in headers
    assert "建議修正方向" in headers
    assert "正式採用值" not in headers
```

- [ ] **Step 3: Write failing Word structure tests**

```python
from io import BytesIO
from docx import Document


def test_docx_contains_required_sections(report_fixture):
    document = Document(BytesIO(build_review_docx(report_fixture)))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    for heading in ["案件基本資料", "風險與期限", "疑點與證據", "修正要求", "新版重檢結果", "最終審查結論"]:
        assert heading in text
    assert "審查人員另訂正式值" not in text
```

Also test AI output is labeled `AI 輔助說明`, sources remain present, and a historical legacy value is labeled `舊流程歷史決策` rather than presented as a new Review action.

- [ ] **Step 4: Run report tests to verify builders are absent**

```bash
docker compose --env-file .env.example build api
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_reports.py app/review/tests/test_xlsx_reports.py app/review/tests/test_docx_reports.py -q
```

Expected: FAIL on missing builders after the dependency build succeeds.

- [ ] **Step 5: Expand immutable report context**

Add these exact Pydantic interfaces, then include `urgency`, `correction_requests`, and `history` on `ReviewReport`:

```python
class ReportUrgency(BaseModel):
    level: str
    remaining_days: int | None
    due_at: datetime | None


class ReportCorrectionItem(BaseModel):
    finding_id: UUID
    finding_code: str
    severity: str
    page_number: int | None
    reported_text: str | None
    reported_value: str | None
    legal_basis: list
    source_evidence: list
    issue_summary: str
    requested_correction: str
    recheck_outcome: str
    resulting_finding_id: UUID | None


class ReportCorrectionRequest(BaseModel):
    correction_request_id: UUID
    request_no: int
    status: str
    due_at: datetime
    message: str
    base_document_id: UUID
    base_document_version: int
    response_document_id: UUID | None
    response_document_version: int | None
    sent_at: datetime | None
    resubmitted_at: datetime | None
    rechecked_at: datetime | None
    items: list[ReportCorrectionItem]


class ReportHistoryEvent(BaseModel):
    event_type: str
    occurred_at: datetime
    actor_id: UUID | None
    reason: str | None
```

`ReviewService.build_report(validation_run_id)` must select only the requested Run and the correction requests whose base or response context belongs to that Run. It must never populate historical output from current latest rows.

- [ ] **Step 6: Implement the Excel builder**

Use `openpyxl.Workbook`, remove the default sheet, create the four sheets in the required order, write fixed Chinese headers, freeze header rows, enable filters, set readable widths, and render all datetimes in Asia/Taipei display format while retaining timezone-aware source values in the report model. Do not add formulas that compute an appraisal value.

- [ ] **Step 7: Implement the Word builder**

Use `docx.Document`, Heading 1/2 sections, tables for case and issue data, explicit evidence and legal-basis labels, and a final audit section. Keep body copy Chinese and business-facing. Do not embed bucket/object keys, UUID-heavy debug data, or raw JSON; structured evidence must render as readable field/value rows.

- [ ] **Step 8: Run report tests and commit**

Run the Step 4 command.

Expected: PASS; both byte streams reopen successfully and contain the specified sections/sheets.

```bash
git add requirements.txt app/review/reports.py app/review/xlsx_reports.py app/review/docx_reports.py app/review/tests/test_reports.py app/review/tests/test_xlsx_reports.py app/review/tests/test_docx_reports.py
git commit -m feat-review-xlsx-docx-reports
```

---

### Task 8: Store and Download Safe Report Artifacts

**Files:**
- Modify: `app/review/schemas.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/router.py`
- Modify: `app/review/workbench_schemas.py`
- Modify: `app/review/workbench_service.py`
- Modify: `app/review/tests/test_report_api.py`
- Modify: `app/review/tests/test_workbench_api.py`

**Interfaces:**
- Produces safe `GeneratedReportRead` with no bucket/object key.
- Produces separate correction-notice and final-report generation routes plus a shared safe download route.
- Consumes `build_review_xlsx` and `build_review_docx`.

- [ ] **Step 1: Write failing API safety and format tests**

```python
@pytest.mark.parametrize(
    ("format_name", "mime_type", "suffix"),
    [
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    ],
)
def test_generate_and_download_report(review_client, completed_run, format_name, mime_type, suffix):
    generated = review_client.post(f"/api/v1/review/runs/{completed_run.id}/reports", json={"format": format_name})
    assert generated.status_code == 201
    body = generated.json()
    assert body["original_filename"].endswith(suffix)
    assert "bucket_name" not in body
    assert "object_key" not in body
    downloaded = review_client.get(f"/api/v1/review/reports/{body['document_id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith(mime_type)
```

Add equivalent format tests for `POST /correction-requests/{id}/reports`, requiring request status `SENT` or later. Add cross-case document access tests, storage upload cleanup on metadata failure, report snapshot version tests, and a test proving a later Run does not change an already generated report.

- [ ] **Step 2: Run report API tests to verify failure**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_report_api.py app/review/tests/test_workbench_api.py -q
```

Expected: FAIL because format routes and safe metadata do not exist.

- [ ] **Step 3: Replace public storage metadata schema**

```python
class GeneratedReportRead(BaseModel):
    document_id: UUID
    case_id: UUID
    document_type: str
    original_filename: str
    mime_type: str
    checksum_sha256: str
    file_size_bytes: int
    version_no: int
```

Keep bucket/object key only in repository-internal dicts. Update the old PDF response to the same safe schema while preserving PDF download compatibility.

- [ ] **Step 4: Generalize report persistence**

Change `save_report_document` to accept `document_type`, `mime_type`, `original_filename`, and format-specific object key while preserving generated version numbering. Add `get_report_document_for_review(document_id, review_id)` that joins through the Review case before returning internal storage metadata.

- [ ] **Step 5: Implement generation and download routes**

Use a format map rather than branching duplicated upload logic:

```python
REPORT_FORMATS = {
    "xlsx": (build_review_xlsx, XLSX_MIME),
    "docx": (build_review_docx, DOCX_MIME),
}
```

Implement two generation routes:

- `POST /correction-requests/{id}/reports`: correction-notice snapshot for a `SENT`, `RESUBMITTED`, `RECHECKING`, or `RECHECKED` request.
- `POST /runs/{run_id}/reports`: final risk report only when the Review is `REVIEW_COMPLETED` and the Run is that Review's latest completed Run.

Correction-notice object keys must use `cases/{case_id}/generated/{document_id}/v{version}/correction-request-{request_no}.{format}`. Final object keys must use `cases/{case_id}/generated/{document_id}/v{version}/review-risk-report.{format}`. On database failure, delete only the exact object just uploaded. Download by `document_id` after case ownership/permission validation; never accept an object key from the client.

- [ ] **Step 6: Run tests and commit**

Run the Step 2 command.

Expected: PASS with no bucket/object key in any API response.

```bash
git add app/review/schemas.py app/review/repository.py app/review/router.py app/review/workbench_schemas.py app/review/workbench_service.py app/review/tests/test_report_api.py app/review/tests/test_workbench_api.py
git commit -m feat-review-safe-report-artifacts
```

---

### Task 9: Replace Workbench Value Selection With Correction Workflow

**Files:**
- Modify: `app/review/test_ui/index.html`
- Modify: `app/review/workbench_schemas.py`
- Modify: `app/review/workbench_service.py`
- Modify: `app/review/tests/test_test_ui.py`
- Modify: `app/review/tests/test_ui_behavior.mjs`
- Modify: `app/review/tests/test_workbench_demo.py`

**Interfaces:**
- Consumes: triage, correction, urgency, recheck, completion, and safe-report APIs.
- Produces: four business tabs `檢核結果`, `修正通知`, `新版重檢`, `報告與歷程`.

- [ ] **Step 1: Write failing static and behavior tests**

```python
def test_ui_removes_reviewer_value_selection(client):
    html = client.get("/api/v1/review/test-ui").text
    for forbidden in ["本項最後採用哪個內容", "維持原申報內容", "採用系統建議內容", "另訂正式內容"]:
        assert forbidden not in html
    for required in ["確認有問題", "排除誤判", "轉專業覆核", "建立修正通知單", "新版重檢", "匯出 Excel", "匯出 Word"]:
        assert required in html
```

Add Node behavior tests for `after_value` never being serialized, triage reason validation, all-Finding triage blockers, sent-request read-only state, urgency labels, report format calls, unsaved-change guards, and completion blockers.

- [ ] **Step 2: Run UI tests to verify old controls fail assertions**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_test_ui.py app/review/tests/test_workbench_demo.py -q
docker compose --env-file .env.example exec -T api node --test app/review/tests/test_ui_behavior.mjs
```

Expected: FAIL because formal-value controls still exist.

- [ ] **Step 3: Update Workbench detail aggregation**

Add correction request/item history and generated report metadata to `WorkbenchCaseDetailRead`. Keep technical IDs and raw JSON inside the default-closed development drawer. The main UI renders readable field/value evidence and only opens the case-owned PDF for the selected Finding.

- [ ] **Step 4: Implement the four-tab workflow**

`檢核結果` shows three triage buttons and reason input. `修正通知` stays disabled until every Finding is triaged and at least one is confirmed. `新版重檢` is read-only while waiting and enables recheck only after a validated resubmission. `報告與歷程` lists immutable Runs/requests/reports and exposes Excel/Word buttons at the allowed stage.

The case list must render separate badges, for example `高風險` and `剩 2 天・緊急`; never label deadline urgency as content risk.

- [ ] **Step 5: Implement completion copy and guards**

Use one button `確認無誤並完成審查`. It is disabled with readable blockers for missing items, open/confirmed/expert Findings, active correction requests, or incomplete recheck outcomes. Do not restore separate `APPROVED` and `REVIEW_COMPLETED` buttons.

- [ ] **Step 6: Run UI tests and commit**

Run the Step 2 commands.

Expected: both commands PASS. Do not call these results browser acceptance.

```bash
git add app/review/test_ui/index.html app/review/workbench_schemas.py app/review/workbench_service.py app/review/tests/test_test_ui.py app/review/tests/test_ui_behavior.mjs app/review/tests/test_workbench_demo.py
git commit -m feat-review-correction-workbench
```

---

### Task 10: Preserve Legacy History, Update Demo Data, and Verify End to End

**Files:**
- Modify: `app/review/demo.py`
- Modify: `app/review/CHANGELOG.md`
- Modify: applicable existing tests under `app/review/tests/`
- Do not modify: untracked `app/review/DEMO_GUIDE.md` without separate approval

**Interfaces:**
- Produces: a deterministic Demo with confirmed/dismissed triage, one correction request, a revised version, a recheck, urgency, and Excel/Word reports.
- Verifies: legacy Decision reads and all approved invariants.

- [ ] **Step 1: Add failing Demo workflow assertions**

Extend Demo tests to assert:

```python
assert seeded.review_status == "REVIEW_REQUIRED"
assert seeded.findings[0].status == "OPEN"
assert revised.document_version > seeded.document_version
assert revised.correction_request.status == "RECHECKED"
assert {item.recheck_outcome for item in revised.correction_request.items} <= {"RESOLVED", "STILL_PRESENT"}
```

Add a legacy fixture with stored `PARTIALLY_ACCEPTED` and `selection_source="REVIEWER"`; verify it renders only as `舊流程歷史決策` and cannot be copied into a new POST.

- [ ] **Step 2: Run Demo and compatibility tests to verify failures**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests/test_demo.py app/review/tests/test_demo_workflow.py app/review/tests/test_workbench_demo.py app/review/tests/test_reports.py -q
```

Expected: FAIL until Demo commands use the new workflow.

- [ ] **Step 3: Update Demo seed/revise/reset ownership**

Keep `APP_ENV=development`, fixed username/case/ruleset ownership, fail-closed reset, and no OCR claim. Seed should stop after a Review-required Run. Revise should use the same correction service methods as production, create the newer official document/field version through the existing Demo-only upstream simulation, register it, and recheck it. Do not bypass gates with direct status SQL.

- [ ] **Step 4: Update tracked changelog only**

Document that Review no longer creates formal values, correction requests are immutable, urgency is separate from risk, and Excel/Word artifacts are run-scoped. Leave the untracked guide untouched.

- [ ] **Step 5: Run the complete Review and project suites**

```bash
docker compose --env-file .env.example exec -T api pytest app/review/tests -q
docker compose --env-file .env.example exec -T api pytest tests app/review/tests -q
```

Expected: both commands exit 0 with zero failures. Record exact pass counts from fresh output; do not reuse historical counts.

- [ ] **Step 6: Run migration and artifact checks**

```bash
docker compose --env-file .env.example exec -T api alembic current
docker compose --env-file .env.example exec -T api alembic heads
docker compose --env-file .env.example exec -T api python -m compileall app/review
git diff --check
```

Expected: current and heads both report `20260830_0008`; compileall and diff check exit 0.

- [ ] **Step 7: Perform real browser acceptance**

Use an actual browser session against `/api/v1/review/test-ui` and complete this sequence:

1. Log in as the Demo reviewer.
2. Confirm one Finding and dismiss one false positive.
3. Verify no value-selection field exists.
4. Create and send a correction request.
5. Verify the Review becomes read-only while waiting.
6. Trigger the Demo revised version.
7. Recheck and inspect resolved/still-present outcomes.
8. Verify risk and deadline urgency are separate.
9. Complete the Review manually only after all blockers clear.
10. Generate and download `.xlsx` and `.docx`, open both, and inspect every sheet/section.

Capture browser evidence separately from Node/static test evidence.

- [ ] **Step 8: Review final Git scope**

```bash
git status --short --branch
git diff --stat origin/feature/review...HEAD
git log --oneline --decorate -12
```

Expected: only approved Review files plus explicitly authorized migration/dependency files changed; `app/review/DEMO_GUIDE.md` remains untracked and unstaged; no push or merge occurred.

- [ ] **Step 9: Commit final Demo and compatibility updates**

```bash
git add app/review/demo.py app/review/CHANGELOG.md app/review/tests
git commit -m test-review-correction-workflow-e2e
```

Do not use `git add .`.

## Plan Completion Criteria

The implementation is complete only when all of the following are fresh and verified:

- No new Review API or UI accepts a formal value or `selection_source`.
- Every correction item came from a human-confirmed latest-Run Finding.
- Sent snapshots are immutable and duplicate requests are idempotently blocked.
- Resubmission ownership, version, and lineage checks pass.
- Old Runs, Findings, Decisions, requests, and reports remain queryable.
- Deadline urgency changes automatically at configured boundaries without rewriting Review rows.
- Manual completion rejects every missing/open/confirmed/expert/active-request blocker and succeeds atomically only when clean.
- Excel and Word artifacts reopen successfully, match the requested Run/request snapshot, and expose no storage internals.
- Full backend suites pass with exact fresh counts.
- Real browser acceptance completes the full correction loop.
- Git scope contains only authorized paths and no push/merge.
