### Task 6: Replace Caller-Supplied Run Data with Server Preflight

**Files:**
- Modify: `app/review/schemas.py`
- Modify: `app/review/repository.py`
- Modify: `app/review/service.py`
- Modify: `app/review/tests/test_runs_api.py`
- Modify: `app/review/tests/test_rerun.py`

**Interfaces:**
- Consumes: trusted repository context and pure policy.
- Produces: empty `RunCreate`, `_resolve_trusted_run_context(review)`, server-built snapshots/findings and unchanged response models.

- [ ] **Step 1: Write failing API security tests**

Change the valid run command to `{}` and assert every old authoritative field is rejected:

```python
def run_payload(_data=None):
    return {}


@pytest.mark.parametrize("forged", [
    {"rule_version_id": str(uuid4())},
    {"validation_rule_id": str(uuid4())},
    {"reported_rate": "-5"},
    {"reported_text": "偽造原文"},
    {"page_number": 3},
    {"document_id": str(uuid4())},
    {"source_evidence": []},
    {"legal_basis": []},
])
def test_run_rejects_caller_owned_authoritative_fields(
    authorized_client, runnable_review, forged
):
    response = authorized_client.post(
        f"/api/v1/review/cases/{runnable_review.review_id}/runs",
        json=forged,
    )
    assert response.status_code == 422
```

Add tests that `{}`:

- returns `TRUSTED_INPUT_MISSING` without a completed extraction;
- returns `TRUSTED_INPUT_UNVERIFIED` for an auto-extracted adjustment rate;
- returns `RULE_SOURCE_UNAVAILABLE` for a draft/unextracted source;
- returns `RULE_SELECTION_CONFLICT` for tied highest-priority versions;
- executes every active applicable rule and stores their IDs in the snapshot;
- never creates a run after any preflight error.

- [ ] **Step 2: Verify RED**

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_runs_api.py app/review/tests/test_rerun.py -q
```

Expected: valid `{}` requests fail validation and old payloads are still accepted.

- [ ] **Step 3: Make `RunCreate` an empty command**

Replace adjustment/expert request models and fields with:

```python
class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Keep `ValidationRunRead` unchanged so existing clients still receive run details and input snapshot.

- [ ] **Step 4: Build one server-owned preflight context**

Add immutable context types to `trusted_inputs.py`:

```python
@dataclass(frozen=True)
class TrustedRunContext:
    document: dict
    extraction_run: dict
    fields: dict[str, TrustedField]
    rule_version: dict
    validation_rules: tuple[dict, ...]
    rule_source: dict
```

Implement `ReviewService._resolve_trusted_run_context(review)` in this order:

1. latest active original document;
2. exact-version latest completed extraction;
3. official fields;
4. case/form context;
5. applicable rule candidates through `select_effective_rule()`;
6. published/extracted knowledge source;
7. every active form-applicable validation rule;
8. all required `target_field_code` values through `required_field_problems()`.

Raise the design error codes before changing review state or creating a run.

- [ ] **Step 5: Create runs from context rather than payload**

Change repository run creation to:

```python
async def create_run(
    self,
    review: Review,
    actor_id: UUID,
    rule_version_id: UUID,
    input_snapshot: dict,
) -> ValidationRun:
```

Set `rule_version_id` and `ruleset_snapshot` from the selected context. Build `input_snapshot` exclusively from server rows. For each validation rule, obtain its report value through `context.fields[rule["target_field_code"]]`; generate finding code from `rule_code` and `extracted_field_id`; generate source evidence from that field row; generate legal basis from the selected rule source.

Support the current deterministic MVP rule codes explicitly:

```python
if rule["rule_code"] == "ADJUSTMENT_RATE":
    # Decimal(normalized_value), configured system_rate/tolerance
elif rule["rule_code"] == "EXPERT_GRADE":
    # str(normalized_value), configured system_grade
else:
    raise AppError(
        "RULE_CONFIGURATION_INVALID",
        f"尚未支援規則：{rule['rule_code']}",
        409,
    )
```

Do not silently count unsupported rules as passed.

- [ ] **Step 6: Verify GREEN and commit**

```powershell
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_runs_api.py app/review/tests/test_rerun.py -q
rtk git add app/review/schemas.py app/review/trusted_inputs.py app/review/repository.py app/review/service.py app/review/tests/test_runs_api.py app/review/tests/test_rerun.py
rtk git commit -m "feat(review): execute server-selected trusted inputs"
```

---

