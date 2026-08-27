### Task 4: Load a Server-Owned Run Context

**Files:**
- Modify: `app/review/repository.py`
- Create: `app/review/tests/test_trusted_repository.py`

**Interfaces:**
- Consumes: `review.case_id` and the schema from Task 2.
- Produces: `get_case_rule_context(case_id)`, `get_latest_original_document(case_id)`, `get_latest_completed_extraction(document_id, version_no)`, `list_official_extracted_fields(extraction_run_id)`, `list_rule_candidates()`, `list_active_rules(rule_version_id, form_codes)`, and `get_rule_source(document_id)`.

- [ ] **Step 1: Write failing repository integration tests**

Seed two active original-document versions, one completed extraction per version, official fields, published/draft rule versions, F01/F02 forms and published/unpublished knowledge documents. Assert:

```python
document = await repository.get_latest_original_document(case_id)
assert document["version_no"] == 2

extraction = await repository.get_latest_completed_extraction(
    document["document_id"], document["version_no"]
)
assert extraction["status"] == "COMPLETED"

fields = await repository.list_official_extracted_fields(
    extraction["extraction_run_id"]
)
assert {row["field_code"] for row in fields} == {
    "adjustment_rate", "expert_grade"
}

context = await repository.get_case_rule_context(case_id)
assert context["case_type"] == "LAND"
assert context["district_code"] == "F01"
assert context["form_codes"] == frozenset({"F01"})
```

Also assert a completed extraction for another case/document cannot be returned for the selected document.

- [ ] **Step 2: Verify RED**

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_repository.py -q
```

Expected: attribute failures for the new repository methods.

- [ ] **Step 3: Implement parameterized, server-owned queries**

Use SQLAlchemy `text()` with bound UUID parameters. Required selection predicates are:

```sql
-- Latest active original report
WHERE case_id = :case_id AND document_type = 'original' AND is_active = true
ORDER BY version_no DESC, uploaded_at DESC, document_id DESC
LIMIT 1

-- Latest completed extraction for the exact document row/version
WHERE document_id = :document_id
  AND document_version = :document_version
  AND status = 'COMPLETED'
ORDER BY run_no DESC, completed_at DESC, extraction_run_id DESC
LIMIT 1

-- Official fields only
WHERE extraction_run_id = :extraction_run_id AND is_official = true

-- Case rule context
SELECT c.case_type, c.district_code, c.valuation_base_date,
       coalesce(array_agg(DISTINCT fi.form_code)
           FILTER (WHERE fi.form_code IS NOT NULL AND fi.form_status <> 'VOID'),
           ARRAY[]::varchar[]) AS form_codes
FROM valuation.cases c
LEFT JOIN valuation.form_instances fi ON fi.case_id = c.case_id
WHERE c.case_id = :case_id
GROUP BY c.case_id
```

`list_rule_candidates()` must return candidate versions with applicability, priority and source ID; `list_active_rules()` must include every active rule whose `target_form_code` is NULL or in the provided form set; `get_rule_source()` must return checksum/version/effective dates only when extraction and publication statuses are both usable.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_repository.py -q
rtk git add app/review/repository.py app/review/tests/test_trusted_repository.py
rtk git commit -m "feat(review): load trusted run context"
```

---

