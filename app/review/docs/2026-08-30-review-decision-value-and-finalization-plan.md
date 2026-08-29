# Review Final Value and Atomic Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace abstract Finding acceptance labels with explicit final-value choices and make case approval a single, guarded transition to `REVIEW_COMPLETED`.

**Architecture:** Keep the existing decision enums and JSONB storage. Build server-owned `after_value` records from the locked Finding, compute an approval gate from the latest Run and its current decisions, and let one `APPROVED` request atomically create the audit decision and finish the Review. The plain JavaScript workbench maps readable choices to the existing API values and derives the same blocker summary for immediate feedback.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async repository, PostgreSQL JSONB, plain HTML/CSS/JavaScript, pytest, Node built-in test runner.

## Global Constraints

- Modify only `app/review/**`.
- Do not modify or stage the user-owned untracked `app/review/DEMO_GUIDE.md`.
- Do not add a migration or change another subsystem.
- Do not overwrite source Valuation data or original MinIO documents.
- Preserve readable historical `ACCEPTED`, `REJECTED`, `PARTIALLY_ACCEPTED`, `APPROVED`, and `REVIEW_COMPLETED` records.
- Use TDD: observe every new test fail before adding its implementation.
- Run every shell command with the `rtk` prefix.

---

### Task 1: Server-owned final value records

**Files:**
- Modify: `app/review/decisions.py`
- Modify: `app/review/service.py`
- Test: `app/review/tests/test_decisions.py`
- Test: `app/review/tests/test_rerun.py`
- Test: `app/review/tests/test_workflow_e2e.py`

**Interfaces:**
- Consumes: existing `FindingDecisionCommand`, locked `Finding` fields, and `FindingDecisionRequest.after_value`.
- Produces: `FindingValueContext` and `build_finding_after_value(command, context) -> dict[str, Any] | None`.
- Stored final-value shape: `{"selection_source": "REPORTED|SYSTEM|REVIEWER", "field_path": str | None, "value": str}`.

- [ ] **Step 1: Write failing pure-domain tests**

Add tests covering all four choices:

```python
@pytest.mark.parametrize(
    ("decision", "source", "expected"),
    [
        ("REJECTED", "REPORTED", "-12"),
        ("ACCEPTED", "SYSTEM", "-5"),
        ("PARTIALLY_ACCEPTED", "REVIEWER", "-7"),
    ],
)
def test_build_finding_after_value_uses_explicit_source(decision, source, expected):
    command = FindingDecisionCommand(
        decision=decision,
        reason="人工覆核",
        after_value={"value": "-7"} if decision == "PARTIALLY_ACCEPTED" else None,
    )
    context = FindingValueContext(
        field_path="comparables[0].adjustment_rate",
        reported_value="-12",
        system_value="-5",
    )

    assert build_finding_after_value(command, context) == {
        "selection_source": source,
        "field_path": context.field_path,
        "value": expected,
    }


def test_supplement_has_no_final_value():
    command = FindingDecisionCommand("REQUIRES_SUPPLEMENT", "請補正")
    context = FindingValueContext("field", "original", "system")
    assert build_finding_after_value(command, context) is None


def test_system_choice_rejects_missing_system_value():
    with pytest.raises(AppError) as raised:
        build_finding_after_value(
            FindingDecisionCommand("ACCEPTED", "採用系統建議"),
            FindingValueContext("field", "original", None),
        )
    assert raised.value.code == "REVIEW_DECISION_INVALID"
```

- [ ] **Step 2: Run the domain tests and confirm the missing-interface failure**

Run:

```powershell
rtk pytest app/review/tests/test_decisions.py -q
```

Expected: FAIL because `FindingValueContext` and `build_finding_after_value` do not exist.

- [ ] **Step 3: Implement the final-value builder**

Add this focused interface in `decisions.py` and reuse `_has_meaningful_value`:

```python
@dataclass(frozen=True)
class FindingValueContext:
    field_path: str | None
    reported_value: Any
    system_value: Any


def build_finding_after_value(
    command: FindingDecisionCommand,
    context: FindingValueContext,
) -> dict[str, Any] | None:
    validate_finding_decision(command)
    if command.decision == "REQUIRES_SUPPLEMENT":
        return None
    if command.decision == "REJECTED":
        source, value = "REPORTED", context.reported_value
    elif command.decision == "ACCEPTED":
        source, value = "SYSTEM", context.system_value
    elif command.decision == "PARTIALLY_ACCEPTED":
        source = "REVIEWER"
        value = command.after_value.get("value") if command.after_value else None
    else:
        return command.after_value
    if not _has_meaningful_value(value):
        raise AppError(
            "REVIEW_DECISION_INVALID",
            "所選內容沒有可用的正式採用值",
            409,
        )
    return {
        "selection_source": source,
        "field_path": context.field_path,
        "value": str(value).strip(),
    }
```

Keep `EXPERT_REVIEW` readable for historical/API compatibility; it does not produce a new final value.

- [ ] **Step 4: Make `ReviewService.decide_finding` own reported/system values**

Build context from the locked Finding, never from caller-provided reported/system values:

```python
def _first_present(*values):
    return next((value for value in values if value is not None), None)


command = FindingDecisionCommand(
    payload.decision,
    payload.reason,
    payload.after_value,
)
after_value = build_finding_after_value(
    command,
    FindingValueContext(
        field_path=finding.field_path,
        reported_value=_first_present(
            finding.reported_value,
            finding.reported_adjustment_rate,
            finding.reported_grade,
        ),
        system_value=_first_present(
            finding.system_adjustment_rate,
            finding.system_grade,
        ),
    ),
)
resulting_status = validate_finding_decision(command)
```

Pass `after_value or {"status": resulting_status}` to `create_decision`. Update partial-decision integration payloads to use `{"value": "-7"}` and assert the normalized JSON structure.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
rtk pytest app/review/tests/test_decisions.py app/review/tests/test_rerun.py app/review/tests/test_workflow_e2e.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the independently working value contract**

```powershell
rtk git add app/review/decisions.py app/review/service.py app/review/tests/test_decisions.py app/review/tests/test_rerun.py app/review/tests/test_workflow_e2e.py
rtk git commit -m "feat(review): record explicit final value choices"
```

---

### Task 2: Complete-finding gate and atomic case finalization

**Files:**
- Modify: `app/review/decisions.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/service.py`
- Modify: `app/review/workbench_repository.py`
- Test: `app/review/tests/test_decisions.py`
- Test: `app/review/tests/test_rerun.py`
- Test: `app/review/tests/test_workflow_e2e.py`

**Interfaces:**
- Consumes: locked `Review`, latest `ValidationRun`, open Missing Items, latest Run Findings, and their decision `after_value` records.
- Produces: expanded `ReviewGateSummary` with `has_completed_run`, `open_missing_count`, `unresolved_finding_count`, `invalid_value_count`, and `blockers`.
- `APPROVED` request result: one `APPROVED` decision plus Review status `REVIEW_COMPLETED` and non-null `completed_at` in one transaction.

- [ ] **Step 1: Replace high-risk-only unit tests with complete gate tests**

Add explicit tests:

```python
@pytest.mark.parametrize(
    "summary",
    [
        ReviewGateSummary(False, 0, 0, 0),
        ReviewGateSummary(True, 1, 0, 0),
        ReviewGateSummary(True, 0, 1, 0),
        ReviewGateSummary(True, 0, 0, 1),
    ],
)
def test_any_incomplete_gate_blocks_approval(summary):
    with pytest.raises(AppError) as raised:
        validate_case_decision(CaseDecisionCommand("APPROVED", "擬核定"), summary)
    assert raised.value.code == "REVIEW_DECISION_INVALID"


def test_complete_gate_allows_approval():
    assert validate_case_decision(
        CaseDecisionCommand("APPROVED", "擬核定"),
        ReviewGateSummary(True, 0, 0, 0),
    ) == "APPROVED"
```

Remove the override-bypass expectation: workbench approval must satisfy every gate.

- [ ] **Step 2: Run tests and confirm the old summary contract fails**

```powershell
rtk pytest app/review/tests/test_decisions.py -q
```

Expected: FAIL because `ReviewGateSummary` still contains only `unresolved_high_count`.

- [ ] **Step 3: Implement the expanded gate summary and validation details**

Use this shape in `decisions.py`:

```python
@dataclass(frozen=True)
class ReviewGateSummary:
    has_completed_run: bool
    open_missing_count: int
    unresolved_finding_count: int
    invalid_value_count: int

    def blockers(self) -> list[str]:
        items = []
        if not self.has_completed_run:
            items.append("最新一次智慧審查尚未完成")
        if self.open_missing_count:
            items.append(f"仍有 {self.open_missing_count} 項缺件")
        if self.unresolved_finding_count:
            items.append(f"仍有 {self.unresolved_finding_count} 項疑點未完成")
        if self.invalid_value_count:
            items.append(f"仍有 {self.invalid_value_count} 項缺少正式採用內容")
        return items
```

For `APPROVED`, reject whenever `summary.blockers()` is non-empty and return the list in `AppError.details["blockers"]`.

- [ ] **Step 4: Build the gate from the locked latest state**

In `ReviewService`, load only current data:

```python
async def _approval_gate_summary(self, review) -> ReviewGateSummary:
    run = (
        await self.repository.get_run(review.latest_validation_run_id)
        if review.latest_validation_run_id
        else None
    )
    missing = await self.repository.list_missing_items(review.review_id, open_only=True)
    findings = await self.repository.list_findings(review.latest_validation_run_id) if run else []
    decisions = {
        item.finding_id: item
        for item in await self.repository.list_decisions(review.review_id)
        if item.finding_id is not None
    }
    unresolved = [
        item for item in findings
        if item.status in {"OPEN", "REQUIRES_SUPPLEMENT", "EXPERT_REVIEW"}
    ]
    final_statuses = {"ACCEPTED", "REJECTED", "PARTIALLY_ACCEPTED"}
    invalid_values = [
        item for item in findings
        if item.status in final_statuses
        and not _decision_has_final_value(decisions.get(item.finding_id))
    ]
    return ReviewGateSummary(
        has_completed_run=bool(run and run.run_status == "COMPLETED"),
        open_missing_count=len(missing),
        unresolved_finding_count=len(unresolved),
        invalid_value_count=len(invalid_values),
    )
```

Implement `_decision_has_final_value` with the same meaningful-value rule used by Task 1. The locked Review and transaction boundary remain in `decide_case`.

- [ ] **Step 5: Atomically finish an approved Review**

For `payload.decision == "APPROVED"`:

```python
summary = await self._approval_gate_summary(review)
validate_case_decision(command, summary)
ensure_transition(before_status, "APPROVED")
ensure_transition("APPROVED", "REVIEW_COMPLETED")
review.review_status = "REVIEW_COMPLETED"
review.completed_at = datetime.now(UTC)
after_value = {
    "review_status": "REVIEW_COMPLETED",
    "validation_run_id": str(review.latest_validation_run_id),
}
```

Create exactly one decision whose `decision` remains `APPROVED`. Leave return/revision and supplement transitions unchanged. Update `current_risk_counts` and workbench `open_finding_count` so `PARTIALLY_ACCEPTED` with a valid final value is no longer counted as unresolved.

- [ ] **Step 6: Update integration tests for one-step completion and all-severity blocking**

Cover these exact outcomes:

```python
approved = authorized_client.post(
    f"/api/v1/review/cases/{review_id}/decision",
    json={"decision": "APPROVED", "reason": "核定並完成審查"},
)
assert approved.status_code == 201
assert authorized_client.get(
    f"/api/v1/review/cases/{review_id}"
).json()["review_status"] == "REVIEW_COMPLETED"
case_decisions = [
    item for item in authorized_client.get(
        f"/api/v1/review/cases/{review_id}/decisions"
    ).json()
    if item["finding_id"] is None
]
assert [item["decision"] for item in case_decisions] == ["APPROVED"]
```

Also create a MEDIUM or LOW `OPEN` Finding on the latest Run and assert approval returns 409 with `details.blockers`. Assert a terminal Finding lacking standardized `after_value.value` also returns 409.

- [ ] **Step 7: Run focused backend tests**

```powershell
rtk pytest app/review/tests/test_decisions.py app/review/tests/test_rerun.py app/review/tests/test_workflow_e2e.py app/review/tests/test_workbench_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit the atomic gate**

```powershell
rtk git add app/review/decisions.py app/review/repository.py app/review/service.py app/review/workbench_repository.py app/review/tests/test_decisions.py app/review/tests/test_rerun.py app/review/tests/test_workflow_e2e.py app/review/tests/test_workbench_api.py
rtk git commit -m "feat(review): finalize approved cases atomically"
```

---

### Task 3: Reviewer-facing choices and blocker feedback

**Files:**
- Modify: `app/review/test_ui/index.html`
- Modify: `app/review/tests/test_ui_behavior.mjs`
- Modify: `app/review/tests/test_test_ui.py`

**Interfaces:**
- Consumes: existing workbench case detail (`runs`, `missing_items`, `findings`, `decisions`) and existing decision endpoints.
- Produces: `approvalBlockers(detail) -> string[]`, readable choice labels, a custom-value-only input, and one `APPROVED` request labeled「核定並完成審查」.

- [ ] **Step 1: Write failing Node behavior tests**

Export `approvalBlockers` from the testable logic block and replace old label expectations:

```javascript
test("finding choices describe the final adopted content", () => {
  assert.equal(logic.findingDecisionLabel("REJECTED"), "維持原申報內容");
  assert.equal(logic.findingDecisionLabel("ACCEPTED"), "採用系統建議內容");
  assert.equal(logic.findingDecisionLabel("PARTIALLY_ACCEPTED"), "另訂正式內容");
  assert.equal(logic.findingDecisionLabel("REQUIRES_SUPPLEMENT"), "資料不足，要求補件");
});

test("approval blockers include every current unfinished item", () => {
  assert.deepEqual(
    logic.approvalBlockers({
      runs: [{ run_status: "COMPLETED" }],
      missing_items: [],
      findings: [{ finding_id: "f-1", status: "OPEN" }],
      decisions: [],
    }),
    ["尚有 1 項疑點未決策或待處理"],
  );
});

test("approved choice is a single final action", () => {
  assert.match(html, />核定並完成審查</);
  assert.doesNotMatch(html, /<option value="REVIEW_COMPLETED">/);
});
```

- [ ] **Step 2: Run Node and static UI tests and observe failure**

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk pytest app/review/tests/test_test_ui.py -q
```

Expected: FAIL on old labels, missing `approvalBlockers`, and the old `REVIEW_COMPLETED` option.

- [ ] **Step 3: Implement readable Finding choices**

Use these labels and body rules inside the testable block:

```javascript
const findingDecisionLabels = {
  REJECTED: "維持原申報內容",
  ACCEPTED: "採用系統建議內容",
  PARTIALLY_ACCEPTED: "另訂正式內容",
  REQUIRES_SUPPLEMENT: "資料不足，要求補件",
  EXPERT_REVIEW: "專業覆核（既有資料）",
};

function findingDecisionBody(reviewId, finding, decision, reason, value) {
  const errors = validateFindingDecision(decision, reason, value);
  const firstError = errors.reason || errors.afterValue;
  if (firstError) throw new Error(firstError);
  const body = { review_id: reviewId, decision, reason };
  if (decision === "PARTIALLY_ACCEPTED") body.after_value = { value };
  return body;
}
```

Change the question to「本項最後採用哪個內容？」and the conditional field to「正式採用內容（選擇另訂時必填）」. Keep original/system values visible above the choices.

- [ ] **Step 4: Derive and render approval blockers**

Implement a pure function using latest-detail data:

```javascript
function approvalBlockers(detail) {
  const blockers = [];
  const latest = detail.runs.at(-1);
  if (!latest || latest.run_status !== "COMPLETED") blockers.push("最新一次智慧審查尚未完成");
  if (detail.missing_items.length) blockers.push(`仍有 ${detail.missing_items.length} 項缺件`);
  const unresolved = detail.findings.filter(item =>
    ["OPEN", "REQUIRES_SUPPLEMENT", "EXPERT_REVIEW"].includes(item.status),
  );
  if (unresolved.length) blockers.push(`尚有 ${unresolved.length} 項疑點未決策或待處理`);
  return blockers;
}
```

Render the blocker list beside the case action. Disable「核定並完成審查」when blockers exist; keep return/revision and supplement available. Re-evaluate disabled state when the case-decision select changes.

- [ ] **Step 5: Merge the case action**

The select must contain only:

```html
<option value="RETURNED_FOR_REVISION">退回修正</option>
<option value="SUPPLEMENT_REQUIRED">要求補件</option>
<option value="APPROVED">核定並完成審查</option>
```

For `APPROVED`, show one confirmation message「核定後案件將直接完成審查，確定送出？」and send one request to `/review/cases/{review_id}/decision`. Completed cases render actions as read-only; historical `APPROVED` cases show the compatibility message from the design.

- [ ] **Step 6: Run UI tests**

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk pytest app/review/tests/test_test_ui.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit the UI behavior**

```powershell
rtk git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs app/review/tests/test_test_ui.py
rtk git commit -m "feat(review): clarify final choices and case completion"
```

---

### Task 4: Full regression and documentation consistency

**Files:**
- Modify only if needed for verified expectation changes: `app/review/CHANGELOG.md`
- Do not modify: `app/review/DEMO_GUIDE.md`

- [ ] **Step 1: Run the complete Review backend suite in the project container**

```powershell
rtk docker compose --env-file .env.example run --rm --build api pytest app/review/tests -q
```

Expected: all Review pytest tests pass with no failures.

- [ ] **Step 2: Run the complete Node UI behavior suite**

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: all Node tests pass.

- [ ] **Step 3: Check formatting and the exact diff**

```powershell
rtk git diff --check
rtk git status --short
rtk git diff --stat
```

Expected: no whitespace errors; every changed path is inside `app/review/**`; `app/review/DEMO_GUIDE.md` remains untracked and unstaged.

- [ ] **Step 4: Record verified behavior and commit only tracked implementation files**

Add a short `CHANGELOG.md` entry containing the actual backend and Node test counts observed in Steps 1–2, then:

```powershell
rtk git add app/review/CHANGELOG.md
rtk git commit -m "docs(review): record atomic approval verification"
```

- [ ] **Step 5: Final verification from committed state**

```powershell
rtk git log -5 --oneline
rtk git status --short
```

Expected: implementation commits are present; the only pre-existing unrelated worktree item is the untracked `app/review/DEMO_GUIDE.md`.
