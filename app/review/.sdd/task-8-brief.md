### Task 8: Record the Approved External Change and Perform Final Verification

**Files:**
- Modify: `app/review/OUTSIDE_REVIEW_CHANGES.md`
- Verify: all changed files and live services

**Interfaces:**
- Consumes: completed Tasks 1 through 7 and the user's explicit approval for `0007`.
- Produces: auditable scope record, clean migration-test cleanup and evidence-backed completion status.

- [ ] **Step 1: Update the external-change ledger**

Add item 7 with:

- file `migrations/versions/20260825_0007_add_trusted_review_inputs.py`;
- approval recorded on 2026-08-25;
- reason: trusted extracted values and automatic rule selection;
- exact database revision after apply;
- isolated upgrade/downgrade/upgrade result;
- statement that no other outside-review file changed.

- [ ] **Step 2: Run the complete verification suite**

Run:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest tests app/review/tests -q
rtk git diff --check
rtk docker compose --env-file .env.example exec -T db psql -U app_user -d land_valuation -Atc "SELECT version_num FROM alembic_version"
rtk docker compose --env-file .env.example ps
```

Expected:

- all root and review tests pass;
- only the pre-existing explicit skip remains;
- revision is `20260825_0007`;
- API, PostgreSQL and MinIO are healthy;
- whitespace check is clean.

- [ ] **Step 3: Drop only the verified isolated migration database**

First confirm the exact database name:

```powershell
rtk docker compose --env-file .env.example exec -T db psql -U app_user -d postgres -Atc "SELECT datname FROM pg_database WHERE datname = 'land_valuation_migration_test_0007'"
```

Expected: exactly `land_valuation_migration_test_0007`.

Then remove that isolated database only:

```powershell
rtk docker compose --env-file .env.example exec -T db dropdb -U app_user land_valuation_migration_test_0007
```

- [ ] **Step 4: Request focused code review**

Request review of:

- authoritative-input provenance;
- inability to omit rules;
- published knowledge-source enforcement;
- migration upgrade/downgrade safety;
- transaction/state behavior on all preflight errors;
- report/run historical immutability.

Fix Critical and Important findings with new failing regression tests before claiming completion.

- [ ] **Step 5: Commit the ledger and any reviewed corrections**

```powershell
rtk git add app/review/OUTSIDE_REVIEW_CHANGES.md app/review
rtk git commit -m "docs(review): record trusted input migration"
```

Before committing, run `rtk git status --short` and verify no unapproved path is staged. Do not stage another migration or any path outside the approved `0007` and `app/review/**`.
