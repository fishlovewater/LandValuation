### Task 5: Block Completeness on Missing or Unverified Trusted Inputs

**Files:**
- Modify: `app/review/completeness.py`
- Modify: `app/review/service.py`
- Modify: `app/review/tests/test_completeness_api.py`

**Interfaces:**
- Consumes: repository methods from Task 4 and policy functions from Task 3.
- Produces: trusted missing-item conversion used by `ReviewService.check_completeness()`.

- [ ] **Step 1: Write failing completeness tests**

Add three API cases:

```python
def test_completeness_blocks_when_completed_extraction_is_missing(...):
    response = client.post(f"/api/v1/review/cases/{review_id}/completeness-check")
    assert response.json()["review_status"] == "PENDING_MATERIALS"
    assert "TRUSTED_INPUT_MISSING" in {
        item["item_code"] for item in response.json()["items"]
    }


def test_completeness_blocks_auto_extracted_high_impact_field(...):
    response = client.post(f"/api/v1/review/cases/{review_id}/completeness-check")
    assert "TRUSTED_INPUT_UNVERIFIED_ADJUSTMENT_RATE" in {
        item["item_code"] for item in response.json()["items"]
    }


def test_completeness_accepts_verified_high_impact_fields(...):
    response = client.post(f"/api/v1/review/cases/{review_id}/completeness-check")
    assert response.json()["review_status"] == "READY_FOR_REVIEW"
```

Fixtures must create a published source document, one applicable rule version and all active rules before expecting readiness.

- [ ] **Step 2: Verify RED**

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_completeness_api.py -q
```

Expected: old completeness logic incorrectly reports ready without trusted inputs.

- [ ] **Step 3: Add trusted preflight to completeness**

Add a converter with an explicit result type:

```python
def trusted_problem_to_missing(problem: TrustedInputProblem) -> MissingRequirement:
    suffix = problem.field_code.upper()
    return MissingRequirement(
        item_code=f"{problem.code}_{suffix}",
        item_name=f"正式檢核欄位：{problem.field_code}",
        document_category="original",
        field_path=problem.field_code,
        blocked_rule_codes=frozenset({"TRUSTED_INPUT_REQUIRED"}),
    )
```

In `check_completeness()`, run existing document/base-field checks first. If they pass, resolve document, extraction, rule set and required rule field codes without creating a validation run. Merge the trusted missing requirements into the existing `CompletenessResult` before `sync_missing_items()` and state transition.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_completeness.py app/review/tests/test_completeness_api.py -q
rtk git add app/review/completeness.py app/review/service.py app/review/tests/test_completeness_api.py
rtk git commit -m "feat(review): require verified formal inputs"
```

---

