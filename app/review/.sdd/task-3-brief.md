### Task 3: Implement Pure Trust and Rule-Selection Policy

**Files:**
- Create: `app/review/trusted_inputs.py`
- Modify: `app/review/rule_selection.py`
- Create: `app/review/tests/test_trusted_inputs.py`
- Modify: `app/review/tests/test_rule_selection.py`

**Interfaces:**
- Consumes: extracted-field rows and rule-version candidate rows loaded by the repository.
- Produces: `TrustedField`, `trusted_fields_by_code()`, `required_field_problems()`, and form-set-aware `select_effective_rule()`.

- [ ] **Step 1: Write failing trust-policy tests**

Create tests using this wished-for interface:

```python
from app.review.trusted_inputs import (
    TrustedField,
    required_field_problems,
    trusted_fields_by_code,
)


def field(code, status="VERIFIED", official=True):
    return TrustedField(
        extracted_field_id="field-1",
        field_code=code,
        field_path=code,
        raw_text="來源原文",
        normalized_value="-12",
        value_type="DECIMAL",
        page_number=3,
        verification_status=status,
        is_official=official,
    )


def test_high_impact_field_requires_verified_official_value():
    fields = trusted_fields_by_code([field("adjustment_rate", "AUTO_EXTRACTED")])
    problems = required_field_problems({"adjustment_rate"}, fields)
    assert problems[0].code == "TRUSTED_INPUT_UNVERIFIED"


def test_low_impact_field_accepts_auto_extracted_official_value():
    fields = trusted_fields_by_code([field("property_description", "AUTO_EXTRACTED")])
    assert required_field_problems({"property_description"}, fields) == ()


def test_rejected_or_nonofficial_field_is_missing():
    fields = trusted_fields_by_code([field("adjustment_rate", "REJECTED", False)])
    assert required_field_problems({"adjustment_rate"}, fields)[0].code == "TRUSTED_INPUT_MISSING"
```

Extend rule-selection tests so `select_effective_rule(..., form_codes={"F01", "F03"})` accepts a candidate whose `form_code` is in the set and ignores candidates for `F02`.

- [ ] **Step 2: Verify RED**

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_inputs.py app/review/tests/test_rule_selection.py -q
```

Expected: import/signature failures because the policy does not exist yet.

- [ ] **Step 3: Implement the minimal pure policy**

Create immutable dataclasses:

```python
HIGH_IMPACT_FIELD_CODES = frozenset({
    "adjustment_rate",
    "comparison_price",
    "recalculated_price",
    "final_valuation",
    "expert_grade",
    "legal_basis",
})


@dataclass(frozen=True)
class TrustedField:
    extracted_field_id: str
    field_code: str
    field_path: str
    raw_text: str
    normalized_value: object
    value_type: str
    page_number: int
    verification_status: str
    is_official: bool


@dataclass(frozen=True)
class TrustedInputProblem:
    code: str
    field_code: str


def trusted_fields_by_code(fields):
    return {item.field_code: item for item in fields if item.is_official}


def required_field_problems(required_codes, fields):
    problems = []
    for code in sorted(required_codes):
        item = fields.get(code)
        if item is None or item.verification_status == "REJECTED":
            problems.append(TrustedInputProblem("TRUSTED_INPUT_MISSING", code))
        elif (
            code in HIGH_IMPACT_FIELD_CODES
            and item.verification_status != "VERIFIED"
        ):
            problems.append(TrustedInputProblem("TRUSTED_INPUT_UNVERIFIED", code))
    return tuple(problems)
```

Change `select_effective_rule()` to accept `form_codes: frozenset[str]` and match `candidate.form_code is None or candidate.form_code in form_codes`.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_inputs.py app/review/tests/test_rule_selection.py -q
rtk git add app/review/trusted_inputs.py app/review/rule_selection.py app/review/tests/test_trusted_inputs.py app/review/tests/test_rule_selection.py
rtk git commit -m "feat(review): define trusted input policy"
```

Expected: policy tests pass and the commit contains only `app/review/**`.

---

