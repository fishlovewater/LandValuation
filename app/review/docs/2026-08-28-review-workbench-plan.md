# Review 審查人員工作台實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 以正式 Review View API 與單檔 development UI，讓審查人員不需操作 UUID 或理解 HTTP 細節即可完成待審清單、建案、智慧審查、決策、複查與報告流程。

**Architecture:** 新增獨立的 workbench schema、repository 與 service，聚合既有 Review 能力但不複製規則計算。`router.py` 只負責 JWT／權限與 HTTP 邊界；`test_ui/index.html` 消費 View API；Demo revise 由 CLI 與 development-only HTTP route 共用同一函式。

**Tech Stack:** Python 3.13、FastAPI、Pydantic v2、SQLAlchemy async、PostgreSQL、pytest、原生 HTML/CSS/JavaScript。

## Global Constraints

- 只修改 `app/review/**`；不新增 migration，不修改 main router、Compose、根目錄依賴或其他子系統。
- PostgreSQL 只保存結構化資料與 object metadata；MinIO 保存檔案本體；不得保存固定 localhost URL。
- 所有正式工作台 API 使用既有 JWT 與 `review.execute`／`review.decide` 權限。
- 不建立 Vue/React/npm runtime；`/api/v1/review/test-ui` 維持 development-only。
- 規則計算、完整性、run、rerun、決策與報告一律重用既有 deterministic service。

---

### Task 1: 工作台查詢模型與聚合查詢

**Files:**
- Create: `app/review/workbench_schemas.py`
- Create: `app/review/workbench_repository.py`
- Create: `app/review/workbench_service.py`
- Create: `app/review/tests/test_workbench_service.py`

**Interfaces:**
- Produces: `WorkbenchRepository.summary_rows()`、`list_cases(query)`、`list_eligible_cases(q, limit)`、`case_detail(review_id)`。
- Produces: `WorkbenchService.summary()`、`list_cases(q, status_filter, risk_level, limit, offset)`、`eligible_cases(q, limit)`、`detail(review_id)`。

- [x] **Step 1: Write failing service tests**

```python
async def test_summary_maps_status_groups_and_open_totals(workbench_service):
    result = await workbench_service.summary()
    assert result.status_counts["pending"] == 1
    assert result.open_finding_count == 2

async def test_list_cases_preserves_case_labels_and_latest_run(workbench_service):
    result = await workbench_service.list_cases("WB-001", "RECEIVED", None, 20, 0)
    assert result.items[0].case_no == "WB-001"
    assert result.items[0].latest_run.run_no == 2

async def test_detail_returns_documents_runs_findings_decisions_and_versions(workbench_service, review_id):
    result = await workbench_service.detail(review_id)
    assert result.documents[0].version_no == 1
    assert result.version_diffs[0].field_code == "adjustment_rate"
    assert result.runs[0].findings[0].finding_code == "RULE:RATE"
```

- [x] **Step 2: Run tests and verify RED**

Run: `pytest app/review/tests/test_workbench_service.py -q`

Expected: collection fails because `app.review.workbench_service` does not exist.

- [x] **Step 3: Add exact Pydantic response contracts**

Define `WorkbenchSummaryRead`, `WorkbenchCaseListItem`, `WorkbenchCaseList`, `EligibleCaseRead`, `WorkbenchDocumentRead`, `FieldVersionDiffRead`, and `WorkbenchCaseDetailRead`. UUIDs remain response metadata but are never user-entered by the UI.

- [x] **Step 4: Add parameterized SQL aggregation**

Use SQLAlchemy `text()` with bound `q`, `status`, `risk_level`, `limit`, and `offset`; join only case summary, reviewer display name, latest run, missing items, documents, findings, risks, decisions, and generated report metadata. Eligible cases use a correlated `NOT EXISTS` query against `review.reviews` by `case_id`.

- [x] **Step 5: Implement minimal mapping service and verify GREEN**

Run: `pytest app/review/tests/test_workbench_service.py -q`

Expected: PASS.

### Task 2: 工作台 View API 與開始智慧審查

**Files:**
- Modify: `app/review/workbench_schemas.py`
- Modify: `app/review/workbench_service.py`
- Modify: `app/review/router.py`
- Create: `app/review/tests/test_workbench_api.py`

**Interfaces:**
- Produces: `GET /review/workbench/summary`。
- Produces: `GET /review/workbench/cases` 與 `GET /review/workbench/cases/{review_id}`。
- Produces: `GET /review/workbench/eligible-cases`。
- Produces: `POST /review/workbench/cases/{review_id}/start` returning `BLOCKED` or `COMPLETED`.

- [x] **Step 1: Write failing API tests**

```python
def test_workbench_requires_review_execute_permission(client):
    assert client.get("/api/v1/review/workbench/summary").status_code == 401

def test_summary_list_eligible_and_detail_contracts(authorized_client, review_id):
    assert authorized_client.get("/api/v1/review/workbench/summary").status_code == 200
    assert authorized_client.get("/api/v1/review/workbench/cases").status_code == 200
    assert authorized_client.get("/api/v1/review/workbench/eligible-cases").status_code == 200
    assert authorized_client.get(f"/api/v1/review/workbench/cases/{review_id}").status_code == 200

def test_start_blocked_does_not_create_run(authorized_client, blocked_review_id, postgres_connection):
    response = authorized_client.post(f"/api/v1/review/workbench/cases/{blocked_review_id}/start")
    assert response.json()["outcome"] == "BLOCKED"
    assert response.json()["run"] is None

def test_start_ready_returns_completed_run_findings_and_risk(authorized_client, ready_review_id):
    response = authorized_client.post(f"/api/v1/review/workbench/cases/{ready_review_id}/start")
    assert response.json()["outcome"] == "COMPLETED"
    assert response.json()["run"]["run_status"] == "COMPLETED"
```

- [x] **Step 2: Run tests and verify RED**

Run: `pytest app/review/tests/test_workbench_api.py -q`

Expected: endpoints return 404.

- [x] **Step 3: Implement start orchestration**

```python
result, review, items = await review_service.check_completeness(review_id, actor_id)
completeness = WorkbenchCompletenessRead.from_result(result, review, items)
if not result.ready:
    return WorkbenchStartRead(outcome="BLOCKED", completeness=completeness, run=None)
run, risk = await review_service.create_run(review_id, actor_id)
findings = await review_service.list_findings(run.validation_run_id)
return WorkbenchStartRead(outcome="COMPLETED", completeness=completeness, run=run, findings=findings, risk_summary=risk)
```

- [x] **Step 4: Add routes with existing permission dependencies and verify GREEN**

Run: `pytest app/review/tests/test_workbench_api.py -q`

Expected: PASS; blocked path has no new run and complete path returns the synchronous result.

### Task 3: Demo seed Review 與 development revise HTTP API

**Files:**
- Modify: `app/review/demo.py`
- Modify: `app/review/router.py`
- Create: `app/review/tests/test_workbench_demo.py`
- Modify: `app/review/tests/test_demo_workflow.py`

**Interfaces:**
- `seed_demo()` returns `review_id` and inserts one `RECEIVED` Review for the owned Demo case.
- `POST /review/demo/revise` calls the existing idempotent `revise_demo()` only in development.

- [x] **Step 1: Write failing seed and route tests**

```python
def test_seed_creates_received_review_visible_to_workbench(postgres_connection):
    seeded = seed_demo()
    assert seeded["review_id"]
    assert seeded_review_status(postgres_connection, seeded["review_id"]) == "RECEIVED"

def test_demo_revise_route_is_development_only_and_idempotent(development_client):
    assert development_client.post("/api/v1/review/demo/revise").json()["created"] is True
    assert development_client.post("/api/v1/review/demo/revise").json()["created"] is False

def test_demo_revise_rejects_ownership_collision(development_client, ownership_collision):
    response = development_client.post("/api/v1/review/demo/revise")
    assert response.status_code == 409
```

- [x] **Step 2: Run tests and verify RED**

Run: `pytest app/review/tests/test_workbench_demo.py app/review/tests/test_demo_workflow.py -q`

Expected: seed has no `review_id` and route returns 404.

- [x] **Step 3: Insert the Review in the existing seed transaction**

Insert `review.reviews(case_id, review_status, started_by_user_id, received_at)` with `RECEIVED`; return the generated `review_id`. Keep reset cleanup order unchanged and scoped to the owned Demo case.

- [x] **Step 4: Add the hidden development route and verify GREEN**

Map `DemoError` ownership/not-found errors to the existing application error envelope without exposing the route outside development.

Run: `pytest app/review/tests/test_workbench_demo.py app/review/tests/test_demo_workflow.py -q`

Expected: PASS.

### Task 4: 審查人員單檔工作台

**Files:**
- Modify: `app/review/test_ui/index.html`
- Modify: `app/review/tests/test_test_ui.py`

**Interfaces:**
- Consumes: `/review/workbench/summary`、`/cases`、`/eligible-cases`、`/cases/{review_id}`、`/start` and existing decision/rerun/report APIs.
- Produces: login view, case queue, case workspace, create-review dialog, version/run/report tabs, and a default-closed development drawer.

- [x] **Step 1: Replace old console assertions with failing workbench assertions**

Assert business labels and stable hooks: `login-view`, `workbench-shell`, `case-list`, `case-detail`, `eligible-case-dialog`, `finding-list`, `version-diff`, `report-panel`, `developer-drawer`; assert no `Case ID`, `Review ID`, `API Base`, or editable JWT field.

- [x] **Step 2: Run tests and verify RED**

Run: `pytest app/review/tests/test_test_ui.py -q`

Expected: FAIL on missing workbench hooks and old technical input labels.

- [x] **Step 3: Build the minimal accessible workbench**

Use semantic buttons/forms/dialog/details, `sessionStorage` for JWT only, status banners with `aria-live`, disabled run actions while pending, keyboard-visible focus, responsive single-column layout below 760px, and `prefers-reduced-motion`.

- [x] **Step 4: Add business error handling and development evidence drawer**

401 clears token and returns to login; 403/404/409/422/500 preserve appropriate screen/form state. Store method/path/status/elapsed/payload only in the default-closed drawer and never log passwords or authorization headers.

- [x] **Step 5: Verify GREEN**

Run: `pytest app/review/tests/test_test_ui.py -q`

Expected: PASS.

### Task 5: 整合驗收與文件紀錄

**Files:**
- Modify: `app/review/CHANGELOG.md`
- Modify: `app/review/docs/2026-08-28-review-workbench-plan.md`

- [x] **Step 1: Run focused workbench tests**

Run: `pytest app/review/tests/test_workbench_service.py app/review/tests/test_workbench_api.py app/review/tests/test_workbench_demo.py app/review/tests/test_test_ui.py -q`

Expected: all PASS.

- [x] **Step 2: Run the complete Review suite**

Run: `pytest app/review/tests -q`

Expected: all PASS; no ordinary F01 fixture pollution.

- [x] **Step 3: Verify scope and contracts**

Run: `git status --short` and `git diff --check`.

Expected: only `app/review/**` changed; no whitespace errors, migrations, root dependency changes, fixed localhost object URLs, or new frontend runtime.

- [x] **Step 4: Record the fresh verification result**

Update this plan's checkboxes and `app/review/CHANGELOG.md` with the actual test count and any remaining warnings; do not merge or push.

## 實作結果

- 實作檔案與設計邊界一致，另新增 `test_workbench_service.py` 鎖定 document lineage 比較。
- 工作台清單為避免只載入前 100 筆，新增向後相容的 `status_group` 查詢參數與伺服器端分頁。
- 獨立 code review 後補強 JWT log redaction、BLOCKED 狀態、部分採納 `after_value`、證據／法規／決策歷程及 `document_group_id` 分組。
- Fresh verification：`158 passed, 1 warning`；Python compile 與 JavaScript syntax check 通過。
- 唯一 warning 為既有 Starlette TestClient/httpx deprecation；未 merge、未 push。
