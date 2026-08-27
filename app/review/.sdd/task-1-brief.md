### Task 1: Freeze the Verified Review Security Baseline

**Files:**
- Modify: none
- Verify: current uncommitted `app/review/**` changes

**Interfaces:**
- Consumes: the already implemented decision-gate, server-owned rule-value, latest-run risk and negative-weight fixes.
- Produces: a clean committed baseline before the trusted-input contract replaces the transitional RunCreate format.

- [ ] **Step 1: Verify only allowed paths are dirty**

Run:

```powershell
rtk git status --short
rtk git diff --check
```

Expected: every modified path begins with `app/review/`; whitespace check has no output.

- [ ] **Step 2: Re-run the verified baseline tests**

Run:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest tests app/review/tests -q
```

Expected: `81 passed, 1 skipped`; the existing Starlette TestClient/httpx deprecation warning may remain and must be reported rather than hidden.

- [ ] **Step 3: Commit only the baseline review files**

Run:

```powershell
rtk git add app/review/OUTSIDE_REVIEW_CHANGES.md app/review/decisions.py app/review/recalculation.py app/review/repository.py app/review/risks.py app/review/schemas.py app/review/service.py app/review/tests/test_cases_api.py app/review/tests/test_recalculation.py app/review/tests/test_rerun.py app/review/tests/test_runs_api.py app/review/tests/test_workflow_e2e.py
rtk git commit -m "fix(review): harden run and decision boundaries"
```

Expected: one commit containing no paths outside `app/review/**`.

---

