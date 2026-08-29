# Review Finding Decision Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Review workbench show compact, Chinese, decision-oriented finding cards; preserve the reviewer's location after saving; expose readable rule names instead of technical identifiers; and provide inline validation feedback.

**Architecture:** Enrich immutable finding `legal_basis` snapshots when a validation run is created by selecting readable rule-version metadata from existing tables. Keep the single-file development workbench, but add small pure presentation/validation helpers, explicit active-tab and expanded-finding state, and summary/detail rendering driven by existing finding status and decision history. Backend compatibility values remain intact while new expert-review choices disappear from the product-facing UI.

**Tech Stack:** FastAPI, SQLAlchemy async repository, PostgreSQL JSONB snapshots, plain HTML/CSS/JavaScript, Node built-in test runner, pytest.

## Global Constraints

- Modify only `app/review/**`.
- Do not add migrations, Vue, React, npm dependencies, OCR, Textract, PDF.js, PDF text highlighting, notifications, expert directories, or assignment workflows.
- Keep UUIDs, SHA-256 hashes, coordinates, source IDs, and object storage details out of the reviewer-facing main UI.
- Preserve run-scoped evidence snapshots and existing backend `EXPERT_REVIEW` compatibility values.
- Do not claim that source text was extracted from the displayed PDF by this Review subsystem.
- Use exact stored `rule_name`, `version_name`, `version_no`, and effective dates; do not invent display names in the frontend.
- Keep `/api/v1/review/test-ui` and the existing authenticated PDF content endpoint.
- Do not merge or push unless the user asks.

---

## File Structure

- Modify `app/review/repository.py`: return readable rule-set/version metadata with each selected rule version.
- Modify `app/review/service.py`: persist readable rule and version fields in each new finding's immutable `legal_basis` snapshot.
- Modify `app/review/test_ui/index.html`: hide technical trace fields, render compact finding cards and Chinese statuses, preserve UI state, remove new expert-review choices, and show inline validation.
- Modify `app/review/tests/test_runs_api.py`: prove newly created findings contain exact database-backed readable rule metadata.
- Modify `app/review/tests/test_ui_behavior.mjs`: test pure labels, filtering, card state, and validation decisions.
- Modify `app/review/tests/test_test_ui.py`: assert the delivered HTML structure and absence of product-facing expert options or technical labels.

---

### Task 1: Persist Readable Rule Metadata in Finding Evidence

**Files:**
- Modify: `app/review/tests/test_runs_api.py:122-175,367-380`
- Modify: `app/review/repository.py:244-258`
- Modify: `app/review/service.py:449-463`

**Interfaces:**
- Consumes: `ReviewRepository.list_rule_candidates() -> list[dict]` and each active validation rule returned by `list_active_rules()` with `rule_name`.
- Produces: each finding `legal_basis[0]` with `rule_name: str`, `rule_code: str`, `rule_set_code: str`, `version_name: str`, `version_no: int`, `document_version: int`, `effective_from: str | None`, and `effective_to: str | None`, while retaining existing trace fields in the stored snapshot.

- [ ] **Step 1: Write the failing API assertion**

Update the fixture's two human-readable rule names and assert exact persisted metadata:

```python
rule_names = {
    "ADJUSTMENT_RATE": "調整率一致性檢核",
    "EXPERT_GRADE": "級距一致性檢核",
}

# In the INSERT tuple, replace rule_code as rule_name with:
rule_names[rule_code]

# After loading the first finding:
legal_basis = finding["legal_basis"][0]
assert legal_basis["rule_name"] == "調整率一致性檢核"
assert legal_basis["rule_code"] == "ADJUSTMENT_RATE"
assert legal_basis["rule_set_code"].startswith("RUN_RULES_")
assert legal_basis["version_name"] == "Run Test Rules"
assert legal_basis["version_no"] == 1
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
rtk docker compose --env-file .env.example run --rm --build api pytest app/review/tests/test_runs_api.py::test_create_run_uses_trusted_server_inputs -q
```

Expected: FAIL because `legal_basis` does not yet contain `rule_name`, `rule_set_code`, `version_name`, or `version_no`.

- [ ] **Step 3: Select readable rule-version fields**

Change `list_rule_candidates()` to select the existing columns:

```sql
SELECT rule_version_id, rule_set_code, version_no, version_name,
       status, effective_from, effective_to,
       applicable_case_type, applicable_district_code,
       selection_priority, source_document_id
FROM valuation.rule_versions
ORDER BY selection_priority DESC, rule_version_id
```

- [ ] **Step 4: Add readable values to the immutable legal snapshot**

Extend `_legal_basis()` without removing current audit keys:

```python
{
    "rule_version_id": str(context.rule_version["rule_version_id"]),
    "rule_set_code": context.rule_version["rule_set_code"],
    "version_name": context.rule_version["version_name"],
    "version_no": context.rule_version["version_no"],
    "rule_code": rule["rule_code"],
    "rule_name": rule["rule_name"],
    "document_id": str(context.rule_source["document_id"]),
    "document_version": context.rule_source["version_no"],
    "checksum_sha256": context.rule_source["checksum_sha256"],
    "effective_from": ReviewService._json_value(
        context.rule_source["effective_from"]
    ),
    "effective_to": ReviewService._json_value(
        context.rule_source["effective_to"]
    ),
}
```

- [ ] **Step 5: Run focused backend tests and verify GREEN**

Run:

```powershell
rtk docker compose --env-file .env.example run --rm --build api pytest app/review/tests/test_runs_api.py app/review/tests/test_rule_selection.py -q
```

Expected: all tests pass; the finding evidence contains database-backed Chinese rule names and version data.

- [ ] **Step 6: Commit Task 1**

```powershell
rtk git add app/review/repository.py app/review/service.py app/review/tests/test_runs_api.py
rtk git commit -m "feat(review): expose readable rule evidence"
```

---

### Task 2: Define Reviewer-Facing Labels and Hide Technical Trace Fields

**Files:**
- Modify: `app/review/tests/test_ui_behavior.mjs`
- Modify: `app/review/test_ui/index.html:40-56`

**Interfaces:**
- Consumes: `finding.status`, `finding.legal_basis`, and exact readable fields produced by Task 1.
- Produces: `findingStatusLabel(value) -> str`, `severityLabel(value) -> str`, `displayEvidenceValue(key, value) -> str`, and `flattenDisplayData(value) -> Array<{label: str, value: str}>`.

- [ ] **Step 1: Export the new pure helpers from the Node test harness**

Extend the return list passed to `new Function()`:

```javascript
return {
  redactForLog,
  findingDecisionBody,
  validateFindingDecision,
  startOutcomeMessage,
  workbenchCasesPath,
  copyDemoCommand,
  documentTypeLabel,
  findingDecisionLabel,
  caseDecisionLabel,
  findingStatusLabel,
  severityLabel,
  flattenDisplayData,
  requiresAfterValue,
  documentContentPath,
  pdfPageTarget,
  requestLogSummary,
};
```

- [ ] **Step 2: Write failing presentation tests**

Add:

```javascript
test("finding cards use Chinese decision and risk labels", () => {
  assert.equal(logic.findingStatusLabel("OPEN"), "待決策");
  assert.equal(logic.findingStatusLabel("ACCEPTED"), "已決策：採納疑點");
  assert.equal(
    logic.findingStatusLabel("EXPERT_REVIEW"),
    "專業覆核（既有資料）",
  );
  assert.equal(logic.severityLabel("HIGH"), "高風險");
  assert.equal(logic.severityLabel("MEDIUM"), "中風險");
});

test("review evidence hides trace keys and localizes legal fields", () => {
  assert.deepEqual(
    logic.flattenDisplayData([
      {
        rule_name: "調整率一致性檢核",
        version_name: "2026 年正式版",
        version_no: 3,
        effective_from: "2026-01-01",
        effective_to: null,
        bounding_box: { left: 0.1 },
        checksum_sha256: "a".repeat(64),
        rule_version_id: "technical-id",
        source_id: "source-id",
      },
    ]),
    [
      { label: "規則名稱", value: "調整率一致性檢核" },
      { label: "規則版本", value: "2026 年正式版" },
      { label: "版次", value: "3" },
      { label: "生效日期", value: "2026-01-01" },
      { label: "有效截止日", value: "持續有效" },
    ],
  );
});
```

- [ ] **Step 3: Run Node tests and verify RED**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: FAIL because the new helpers and trace-key filtering do not exist.

- [ ] **Step 4: Implement exact Chinese labels and filtering**

Use:

```javascript
const findingStatusLabels = {
  OPEN: "待決策",
  ACCEPTED: "已決策：採納疑點",
  PARTIALLY_ACCEPTED: "已決策：部分採納",
  REJECTED: "已決策：不採納",
  REQUIRES_SUPPLEMENT: "待補件",
  EXPERT_REVIEW: "專業覆核（既有資料）",
};
const severityLabels = {
  CRITICAL: "重大風險",
  HIGH: "高風險",
  MEDIUM: "中風險",
  LOW: "低風險",
};
const evidenceKeyLabels = {
  document_version: "法規文件版本",
  page_number: "頁碼",
  verification_status: "確認狀態",
  raw_text: "原始文字",
  field_path: "欄位位置",
  field_code: "欄位名稱",
  normalized_value: "正式值",
  reported_value: "申報值",
  system_value: "系統值",
  rule_name: "規則名稱",
  rule_code: "規則代碼",
  version_name: "規則版本",
  version_no: "版次",
  title: "法規名稱",
  document_code: "法規代碼",
  article: "條文",
  section: "章節",
  excerpt: "引用內容",
  effective_from: "生效日期",
  effective_to: "有效截止日",
  applicability: "適用說明",
  source_reference: "來源依據",
};
const hiddenEvidenceKeys = new Set([
  "bounding_box",
  "checksum_sha256",
  "rule_version_id",
  "rule_set_code",
  "source_id",
  "document_id",
  "validation_rule_id",
  "extracted_field_id",
  "extraction_run_id",
  "knowledge_document_id",
]);
const displayEvidenceValue = (key, value) =>
  key === "effective_to" && !value
    ? "持續有效"
    : value === null || value === undefined || value === ""
      ? "未提供"
      : value === "VERIFIED"
        ? "已確認"
        : String(value);
const findingStatusLabel = (value) => findingStatusLabels[value] || value;
const severityLabel = (value) => severityLabels[value] || value;
```

Update `flattenDisplayData()` to call `displayEvidenceValue(key, item)` after checking `hiddenEvidenceKeys`.

- [ ] **Step 5: Run Node tests and verify GREEN**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: all Node tests pass and technical trace rows are absent from the returned display rows.

- [ ] **Step 6: Commit Task 2**

```powershell
rtk git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs
rtk git commit -m "feat(review): simplify reviewer evidence labels"
```

---

### Task 3: Render Compact Finding Cards and Preserve Review Position

**Files:**
- Modify: `app/review/tests/test_ui_behavior.mjs`
- Modify: `app/review/tests/test_test_ui.py`
- Modify: `app/review/test_ui/index.html:7-18,31-35,65-75`

**Interfaces:**
- Consumes: Task 2 labels, `state.current.findings`, `state.current.decisions`, and existing `loadDocumentPreview(finding)`.
- Produces: `findingActionLabel(status) -> str`, `latestFindingDecision(decisions, findingId) -> object | null`, `state.activeTab: str`, and `state.expandedFindingIds: Set<string>`.

- [ ] **Step 1: Write failing pure-state tests**

Export and test:

```javascript
test("finding action reflects whether a decision exists", () => {
  assert.equal(logic.findingActionLabel("OPEN"), "開始審核");
  assert.equal(logic.findingActionLabel("ACCEPTED"), "查看決策");
  assert.equal(logic.findingActionLabel("REQUIRES_SUPPLEMENT"), "查看決策");
});

test("latest finding decision is selected by timestamp", () => {
  const latest = logic.latestFindingDecision(
    [
      { finding_id: "f-1", reason: "第一次", decided_at: "2026-01-01T00:00:00Z" },
      { finding_id: "f-2", reason: "別筆", decided_at: "2026-01-03T00:00:00Z" },
      { finding_id: "f-1", reason: "第二次", decided_at: "2026-01-02T00:00:00Z" },
    ],
    "f-1",
  );
  assert.equal(latest.reason, "第二次");
});
```

- [ ] **Step 2: Write failing static delivery assertions**

In `test_test_ui.py`, add:

```python
assert 'data-toggle-finding="${f.finding_id}"' in response.text
assert 'data-finding-detail="${f.finding_id}"' in response.text
assert "findingStatusLabel(f.status)" in response.text
assert "state.activeTab" in response.text
assert "state.expandedFindingIds" in response.text
assert '<option value="EXPERT_REVIEW">' not in response.text
```

- [ ] **Step 3: Run focused UI tests and verify RED**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk pytest app/review/tests/test_test_ui.py -q
```

Expected: FAIL because compact cards, persistent state, and option removal are not implemented.

- [ ] **Step 4: Add explicit UI state and pure helpers**

Extend the existing `state` object:

```javascript
activeTab: "overview",
expandedFindingIds: new Set(),
```

Add:

```javascript
const findingActionLabel = (status) =>
  status === "OPEN" ? "開始審核" : "查看決策";
function latestFindingDecision(decisions, findingId) {
  return decisions
    .filter((item) => item.finding_id === findingId)
    .sort((a, b) => String(b.decided_at).localeCompare(String(a.decided_at)))[0] || null;
}
```

- [ ] **Step 5: Render each finding as summary plus conditional detail**

For each finding, compute:

```javascript
const expanded = state.expandedFindingIds.has(f.finding_id);
const latestDecision = latestFindingDecision(d.decisions, f.finding_id);
const decided = f.status !== "OPEN";
```

Add a focused renderer and use it inside each card:

```javascript
function renderFindingDetail(f, sourceDocument, latestDecision) {
  const decided = f.status !== "OPEN";
  const decisionContent = decided
    ? latestDecision
      ? `<section class="decision-record">
        <h4>${esc(findingDecisionLabel(latestDecision.decision))}</h4>
        <p>${esc(latestDecision.reason || "未提供決策理由")}</p>
        ${latestDecision.after_value
          ? renderStructuredContent(latestDecision.after_value, "未提供採納後內容。")
          : ""}
        <p>${esc(date(latestDecision.decided_at))}</p>
      </section>`
      : `<section class="decision-record">
          <h4>${esc(findingStatusLabel(f.status))}</h4>
          <p>此為既有狀態，未提供可顯示的決策紀錄。</p>
        </section>`
    : `<div class="decision-box">
        <label class="field">決策理由
          <textarea data-finding-reason="${f.finding_id}" required></textarea>
        </label>
        <label class="field hidden" data-partial-value-box="${f.finding_id}">
          採納後的正式值（部分採納時必填）
          <input data-finding-after-value="${f.finding_id}" placeholder="請輸入採納後的正式值">
        </label>
        <div class="actions">
          <select data-finding-decision="${f.finding_id}" aria-label="疑點決策">
            <option value="ACCEPTED">採納疑點</option>
            <option value="PARTIALLY_ACCEPTED">部分採納</option>
            <option value="REJECTED">不採納</option>
            <option value="REQUIRES_SUPPLEMENT">要求補件</option>
          </select>
          <button class="btn small" data-decide-finding="${f.finding_id}" type="button">儲存疑點決策</button>
        </div>
      </div>`;
  return `<div class="actions">
      <button class="btn secondary small" data-view-source="${f.finding_id}" type="button" ${f.document_id ? "" : "disabled"}>
        ${f.page_number ? `查看原文件第 ${f.page_number} 頁` : "查看原文件"}
      </button>
    </div>
    <section class="evidence-block">
      <h4>原始文字與證據</h4>
      <p><strong>原始文字：</strong>${esc(f.reported_text)}</p>
      ${renderStructuredContent(f.source_evidence, "未提供結構化證據。")}
    </section>
    <section class="evidence-block">
      <h4>法規依據</h4>
      ${renderStructuredContent(f.legal_basis, "未提供法規依據。")}
    </section>
    ${decisionContent}`;
}
```

Render an article containing:

```html
<article class="record finding-card ${expanded ? "expanded" : ""}">
  <div class="finding-summary">
    <span class="badge ${f.severity.toLowerCase()}">${esc(severityLabel(f.severity))}</span>
    <span class="decision-status">${esc(findingStatusLabel(f.status))}</span>
    <h3>${esc(f.title)}</h3>
    <p>${esc(f.description)}</p>
    <p>申報值：${esc(f.reported_value)}　系統值：${esc(f.system_adjustment_rate || f.system_grade)}</p>
    <p>${esc(sourceDocument?.original_filename || "未連結原文件")} · 文件第 ${esc(f.document_version)} 版／第 ${esc(f.page_number)} 頁</p>
    <button class="btn secondary small" data-toggle-finding="${f.finding_id}" aria-expanded="${expanded}" type="button">
      ${expanded ? "收起詳細資料" : findingActionLabel(f.status)}
    </button>
  </div>
  <div class="finding-detail ${expanded ? "" : "hidden"}" data-finding-detail="${f.finding_id}">
    ${renderFindingDetail(f, sourceDocument, latestDecision)}
  </div>
</article>
```

When `decided` is true, replace the editable form with a read-only decision record showing `findingDecisionLabel(latestDecision.decision)`, reason, formal value when present, and decision time. Existing `EXPERT_REVIEW` records use `findingStatusLabel()` and remain read-only.

- [ ] **Step 6: Preserve tab and expanded-card state across reloads**

Make panel and tab rendering compare against `state.activeTab` rather than hard-code overview:

```javascript
const panel = (name, html) =>
  `<section class="tab-panel ${state.activeTab === name ? "" : "hidden"}" data-panel="${name}">${html}</section>`;
const tabClass = (name) => `tab ${state.activeTab === name ? "active" : ""}`;
```

Use `class="${tabClass("overview")}"`, `class="${tabClass("findings")}"`, `class="${tabClass("versions")}"`, and `class="${tabClass("report")}"` for the four tab buttons. On tab click:

```javascript
state.activeTab = button.dataset.tab;
```

On finding toggle:

```javascript
const id = button.dataset.toggleFinding;
const willExpand = !state.expandedFindingIds.has(id);
if (willExpand) state.expandedFindingIds.add(id);
else state.expandedFindingIds.delete(id);
button.setAttribute("aria-expanded", String(willExpand));
$(`[data-finding-detail="${id}"]`).classList.toggle("hidden", !willExpand);
button.textContent = willExpand
  ? "收起詳細資料"
  : findingActionLabel(state.current.findings.find((f) => f.finding_id === id).status);
if (willExpand) await loadDocumentPreview(
  state.current.findings.find((f) => f.finding_id === id),
);
```

Remove automatic first-document loading when merely opening the findings tab. Before saving a finding decision set:

```javascript
state.activeTab = "findings";
state.expandedFindingIds.add(id);
```

Then call `await loadDetail(reviewId)` as before.

- [ ] **Step 7: Remove new expert-review choices and style card states**

Delete `<option value="EXPERT_REVIEW">轉專家覆核</option>` from both finding and case decision selects. Keep `EXPERT_REVIEW` display labels only for historical data. Add focused CSS for `.finding-summary`, `.finding-detail`, `.decision-status`, `.finding-inline-error`, `[aria-invalid="true"]`, and mobile layout; reuse existing colors and spacing tokens.

- [ ] **Step 8: Run focused UI tests and verify GREEN**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk pytest app/review/tests/test_test_ui.py -q
```

Expected: all tests pass; no new expert option exists and persistent card/tab structures are delivered.

- [ ] **Step 9: Commit Task 3**

```powershell
rtk git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs app/review/tests/test_test_ui.py
rtk git commit -m "feat(review): streamline finding decision cards"
```

---

### Task 4: Add Inline Decision Validation and Success Feedback

**Files:**
- Modify: `app/review/tests/test_ui_behavior.mjs`
- Modify: `app/review/tests/test_test_ui.py`
- Modify: `app/review/test_ui/index.html:54-57,69-75`

**Interfaces:**
- Consumes: `findingDecisionBody(reviewId, finding, decision, reason, afterValue)` and Task 3 expanded card state.
- Produces: `validateFindingDecision(decision, reason, afterValue) -> {reason?: str, afterValue?: str}` and `showFindingErrors(findingId, errors) -> boolean` where `true` means submission is blocked.

- [ ] **Step 1: Write failing validation tests**

Add:

```javascript
test("finding validation returns field-specific Chinese errors", () => {
  assert.deepEqual(logic.validateFindingDecision("ACCEPTED", "", ""), {
    reason: "請填寫決策理由。",
  });
  assert.deepEqual(
    logic.validateFindingDecision("PARTIALLY_ACCEPTED", "同意部分內容", ""),
    { afterValue: "請填寫採納後的正式值。" },
  );
  assert.deepEqual(
    logic.validateFindingDecision("PARTIALLY_ACCEPTED", "同意部分內容", "-7"),
    {},
  );
});
```

- [ ] **Step 2: Run the Node test and verify RED**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: FAIL because `validateFindingDecision` is not defined.

- [ ] **Step 3: Implement pure validation and retain payload protection**

Add:

```javascript
function validateFindingDecision(decision, reason, afterValue) {
  const errors = {};
  if (!reason.trim()) errors.reason = "請填寫決策理由。";
  if (decision === "PARTIALLY_ACCEPTED" && !afterValue.trim()) {
    errors.afterValue = "請填寫採納後的正式值。";
  }
  return errors;
}
```

Keep `findingDecisionBody()` defensive by calling the validator and throwing the first error if a caller bypasses the UI.

- [ ] **Step 4: Render inline error targets**

Under the reason textarea and partial-value input render:

```html
<p class="finding-inline-error" data-finding-error-reason="${f.finding_id}" aria-live="polite"></p>
<p class="finding-inline-error" data-finding-error-after-value="${f.finding_id}" aria-live="polite"></p>
```

Implement `showFindingErrors()` to clear old messages, set new messages, apply `aria-invalid="true"`, focus the first invalid field, call `announce("請完成標示的必填欄位。", true)`, and return `true`. When no errors remain, remove `aria-invalid` and return `false`.

Add the delivery assertions to `test_test_ui.py`:

```python
assert 'class="finding-inline-error"' in response.text
assert "data-finding-error-reason" in response.text
assert "data-finding-error-after-value" in response.text
assert 'aria-live="polite"' in response.text
```

- [ ] **Step 5: Block invalid submission locally and announce success**

In the finding decision click branch:

```javascript
const errors = validateFindingDecision(decision, reason, afterValue);
if (showFindingErrors(id, errors)) return;
const body = findingDecisionBody(reviewId, finding, decision, reason, afterValue);
state.activeTab = "findings";
state.expandedFindingIds.add(id);
await request(`/review/findings/${id}/decisions`, { method: "POST", body });
await loadDetail(reviewId);
await loadSummary();
announce("疑點決策已儲存。", false);
```

Do not send an API request when local validation fails.

- [ ] **Step 6: Run all UI tests and verify GREEN**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk pytest app/review/tests/test_test_ui.py -q
```

Expected: all tests pass; validation errors are field-specific and the delivered HTML contains inline live regions.

- [ ] **Step 7: Commit Task 4**

```powershell
rtk git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs app/review/tests/test_test_ui.py
rtk git commit -m "fix(review): keep finding validation in context"
```

---

### Task 5: Full Regression and Browser Acceptance

**Files:**
- Verify only: `app/review/**`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: fresh automated and manual evidence that the approved workflow works without expanding scope.

- [ ] **Step 1: Run the complete Review backend suite from a rebuilt image**

Run:

```powershell
rtk docker compose --env-file .env.example run --rm --build api pytest app/review/tests -q
```

Expected: all Review tests pass. The existing Starlette TestClient deprecation warning may remain; no new warnings or failures are accepted.

- [ ] **Step 2: Run the complete Node behavior suite**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Check repository scope and formatting**

Run:

```powershell
rtk git diff --check
rtk git status --short --branch
rtk git diff --name-only HEAD~4..HEAD
```

Expected: no whitespace errors; only `app/review/**` files are changed by these tasks.

- [ ] **Step 4: Recreate the local API and seed a fresh demo**

Run:

```powershell
rtk docker compose --env-file .env.example up -d --build --force-recreate api
rtk docker compose --env-file .env.example exec -T api python -m app.review.demo seed
```

Expected: API is healthy and the seed command returns the local demo URL plus one-time credentials.

- [ ] **Step 5: Complete browser acceptance at `/api/v1/review/test-ui`**

Verify all of the following:

1. Finding cards initially show only Chinese risk, title, values, source page, status, and action.
2. Opening a card loads the corresponding PDF page; merely opening the tab does not download a PDF.
3. Legal basis shows database-backed rule name, version name, version number, and Chinese effective period.
4. `bounding_box`, SHA-256, UUIDs, and source IDs do not appear in the reviewer content.
5. Neither decision select offers a new expert-review action; historical expert status remains readable.
6. Empty reason shows an inline error, focuses the textarea, and sends no POST request.
7. Partial acceptance without a formal value shows its own inline error.
8. Successful save remains on the findings tab, keeps the same card open, shows the decision status, and announces success.
9. Developer request entries remain individually collapsed and credentials remain redacted.
10. Browser console contains no application-origin errors.

- [ ] **Step 6: Commit any acceptance-only correction, if a failing acceptance check required one**

Only if Step 5 exposed a defect, first add a failing automated regression test, apply the minimal correction, rerun Steps 1-5, then commit the exact affected `app/review/**` files:

```powershell
rtk git add app/review
rtk git commit -m "fix(review): address finding workflow acceptance"
```

If no defect was found, do not create an empty commit.
