# Review Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the synchronous review run APIs with `200 OK` and preserve a complete, review-local history of previous and current work.

**Architecture:** Keep run execution synchronous and change only the FastAPI response contract. Exercise the contract through the existing database-backed API and end-to-end tests, then record the maintenance and prior implementation milestones inside `app/review`.

**Tech Stack:** Python 3.13, FastAPI, pytest, PostgreSQL, Docker Compose, Markdown, Git.

## Global Constraints

- Modify only `app/review/**`.
- Do not modify root `pytest.ini`; run Review tests with the explicit path `app/review/tests`.
- Do not add a worker queue, new review rules, Bedrock wiring, notifications, or other subsystem features.
- Preserve all existing response models, database behavior, snapshots, findings, decisions, rerun history, and reports.
- Use `rtk` for shell commands.

---

### Task 1: Define the synchronous HTTP response contract

**Files:**
- Modify: `app/review/tests/test_runs_api.py`
- Modify: `app/review/tests/test_rerun.py`
- Modify: `app/review/tests/test_workflow_e2e.py`
- Modify: `app/review/router.py`

**Interfaces:**
- Consumes: existing synchronous `ReviewService.create_run()` and `ReviewService.rerun()` results.
- Produces: `POST .../runs` and `POST .../rerun` success responses with status `200` and unchanged `ValidationRunRead` bodies.

- [ ] **Step 1: Change successful run and rerun assertions to 200**

Replace every successful assertion of this form in the three test files:

```python
assert response.status_code == 202
```

with the equivalent assertion for the actual synchronous contract:

```python
assert response.status_code == 200
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
rtk docker exec land_valuation_api pytest -q app/review/tests/test_runs_api.py app/review/tests/test_rerun.py app/review/tests/test_workflow_e2e.py
```

Expected: the successful run and rerun cases fail because the router still returns `202`.

- [ ] **Step 3: Apply the minimal router change**

Change both decorators in `app/review/router.py` from:

```python
status_code=status.HTTP_202_ACCEPTED,
```

to:

```python
status_code=status.HTTP_200_OK,
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the same focused command. Expected: all focused tests pass; only the existing Starlette/httpx deprecation warning may remain.

---

### Task 2: Consolidate Review history and scope records

**Files:**
- Create: `app/review/CHANGELOG.md`
- Modify: `app/review/OUTSIDE_REVIEW_CHANGES.md`
- Modify: `app/review/.sdd/progress.md`
- Modify: `app/review/.sdd/final-review-fixes-report.md`
- Track: existing files under `app/review/.sdd/`

**Interfaces:**
- Consumes: Git history, `.sdd/progress.md`, existing task reports, and the approved maintenance design.
- Produces: one readable chronological project log plus accurate detailed implementation records.

- [ ] **Step 1: Create the user-facing Review changelog**

Record these verified phases in reverse chronological order:

```markdown
# Review 子系統變更紀錄

## 2026-08-27 - 同步 API 契約與紀錄整理
## 2026-08-25 - 可信輸入與規則自動選擇
## 2026-08-25 - Review MVP 閉環
```

For each phase, list delivered behavior, representative commit IDs, verification evidence, and explicit boundaries between implemented and deferred work.

- [ ] **Step 2: Correct the external-change record**

Move migration `0006` and `0007` from “已核准、尚未完成” to completed history, and add a 2026-08-27 entry stating that no new path outside `app/review/**` was changed and `pytest.ini` remained untouched.

- [ ] **Step 3: Finish the SDD summary records**

Append the maintenance result to `progress.md`. Complete `final-review-fixes-report.md` with scope, prior fixes, verification, remaining non-blocking warning, and final commit status. Do not rewrite the detailed historical task reports or diff artifacts.

---

### Task 3: Verify and commit the Review maintenance

**Files:**
- Verify: all modified and untracked paths under `app/review/**`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: a clean Review-only commit with reproducible verification evidence.

- [ ] **Step 1: Run the complete Review test suite**

Run:

```powershell
rtk docker exec land_valuation_api pytest -q app/review/tests
```

Expected: all Review tests pass; the known Starlette/httpx deprecation warning may remain.

- [ ] **Step 2: Verify scope and formatting**

Run a whitespace check against the live code, current tests, and current maintenance records:

```powershell
rtk git diff --cached --check -- app/review/router.py app/review/tests app/review/CHANGELOG.md app/review/OUTSIDE_REVIEW_CHANGES.md app/review/docs/2026-08-27-review-maintenance-plan.md app/review/.sdd/progress.md app/review/.sdd/final-review-fixes-report.md
rtk git status --short
```

Expected: no whitespace errors in live/current files, and every uncommitted path begins with `app/review/`. Historical `.sdd/*.diff` files preserve exact prior patch text and are not whitespace-normalized.

- [ ] **Step 3: Commit the current Review changes**

Run:

```powershell
rtk git add app/review
rtk git commit -m "fix(review): align synchronous run responses"
```

- [ ] **Step 4: Verify the final commit and worktree**

Run:

```powershell
rtk git log -2 --oneline
rtk git status --short
```

Expected: the maintenance commit follows the design commit, and the worktree has no remaining changes.
