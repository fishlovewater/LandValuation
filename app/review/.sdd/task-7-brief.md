### Task 7: Update the Fixed-Case Workflow and Historical Reports

**Files:**
- Modify: `app/review/tests/test_workflow_e2e.py`
- Modify: `app/review/tests/test_report_api.py`
- Modify: `app/review/tests/test_reports.py` only if the pure report fixture requires the new evidence keys
- Modify: `app/review/reports.py` only if report serialization drops trusted evidence fields

**Interfaces:**
- Consumes: empty run command and server-created snapshots/findings from Task 6.
- Produces: one full fixed-case demonstration with immutable old-run evidence after a verified revision and rerun.

- [ ] **Step 1: Rewrite E2E fixture data before production changes**

The fixture must create:

- original document v1 with completed extraction run 1;
- verified official `adjustment_rate=-12` and `expert_grade=B` rows;
- published knowledge document with completed extraction and approval audit;
- applicable published rule version with source link and priority;
- F01 form instance;
- original document v2 with completed extraction run 1 and verified revised values before rerun.

Run and rerun calls must send `{}`.

Assert run 1 snapshot contains v1 extracted-field IDs; after v2 and rerun, run 1 still contains v1 IDs while run 2 contains v2 IDs and new findings link through `supersedes_finding_id`.

- [ ] **Step 2: Verify RED**

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_workflow_e2e.py app/review/tests/test_report_api.py -q
```

Expected: fixture/API mismatches until all trusted source setup and report serialization are correct.

- [ ] **Step 3: Make the minimal report compatibility changes**

Keep report generation run-scoped. Preserve these evidence keys without reading current extraction rows at report time:

```python
{
    "extracted_field_id": "...",
    "document_id": "...",
    "document_version": 1,
    "page": 3,
    "field_path": "adjustment_rate",
    "excerpt": "調整率 -12%",
    "verification_status": "VERIFIED",
}
```

Reports must serialize the finding/snapshot stored for the requested run; they must not substitute latest document or field data.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_workflow_e2e.py app/review/tests/test_report_api.py app/review/tests/test_reports.py -q
rtk git add app/review/tests/test_workflow_e2e.py app/review/tests/test_report_api.py app/review/tests/test_reports.py app/review/reports.py
rtk git commit -m "test(review): verify trusted workflow history"
```

Stage only files that actually changed; omit unchanged paths from `git add`.

---

