# Trusted Review Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make review runs consume only server-selected, traceable extracted fields and automatically execute every applicable published rule.

**Architecture:** Alembic `0007` adds immutable extraction-run and extracted-field contracts plus rule-version applicability/source columns. `app/review/trusted_inputs.py` owns pure trust and impact policy, the repository loads database-backed source bundles, and the service performs one preflight before creating a run. Run and rerun requests become empty commands; all evidence, values, rules and legal sources are produced by the server.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL 16, Alembic, psycopg, pytest, Docker Compose.

## Global Constraints

- The only permitted change outside `app/review/**` is `migrations/versions/20260825_0007_add_trusted_review_inputs.py`.
- Do not modify migrations `0001` through `0006`, `app/api/**`, `app/auth/**`, other subsystems, frontend files, root dependencies, Docker Compose or MinIO/PostgreSQL configuration.
- PostgreSQL stores structured metadata and extracted values; MinIO continues to store PDF/image bodies.
- High-impact fields require `VERIFIED + is_official`; low-impact fields require `AUTO_EXTRACTED` or `VERIFIED` plus `is_official`.
- Missing or unverified high-impact input blocks formal analysis and leaves the review out of `ANALYZING`.
- `app/review` is read-only with respect to extraction data; do not add an extraction write API.
- Run callers cannot submit values, evidence, page numbers, document IDs, rule IDs or legal basis.
- Use `rtk` before every shell command and `apply_patch` for file edits.
- Follow RED -> verify RED -> GREEN -> verify GREEN for every behavior change.
- Use frequent, path-scoped commits so existing unrelated user changes are never staged.

---

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

### Task 2: Add the Trusted Extraction and Rule Applicability Schema

**Files:**
- Create: `migrations/versions/20260825_0007_add_trusted_review_inputs.py`
- Modify: `app/review/tests/test_schema_contract.py`

**Interfaces:**
- Consumes: Alembic head `20260825_0006`; existing `valuation.documents`, `valuation.rule_versions`, `knowledge.documents` and `auth.users` tables.
- Produces: `valuation.extraction_runs`, `valuation.extracted_fields`, and rule-version applicability/source columns.

- [ ] **Step 1: Write the failing schema contract**

Add these expectations to `app/review/tests/test_schema_contract.py`:

```python
TRUSTED_INPUT_COLUMNS = {
    ("valuation", "extraction_runs", "extraction_run_id"),
    ("valuation", "extraction_runs", "document_version"),
    ("valuation", "extraction_runs", "status"),
    ("valuation", "extracted_fields", "extracted_field_id"),
    ("valuation", "extracted_fields", "normalized_value"),
    ("valuation", "extracted_fields", "verification_status"),
    ("valuation", "rule_versions", "applicable_case_type"),
    ("valuation", "rule_versions", "applicable_district_code"),
    ("valuation", "rule_versions", "selection_priority"),
    ("valuation", "rule_versions", "source_document_id"),
}


def test_trusted_input_schema_contract(postgres_connection):
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'valuation'
            """
        )
        actual = set(cursor.fetchall())

    assert TRUSTED_INPUT_COLUMNS <= actual
```

- [ ] **Step 2: Verify RED against the current `0006` database**

Run:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_schema_contract.py::test_trusted_input_schema_contract -q
```

Expected: FAIL because `valuation.extraction_runs` and the new columns do not exist.

- [ ] **Step 3: Preflight existing published rules without changing data**

Run:

```powershell
rtk docker compose --env-file .env.example exec -T db psql -U app_user -d land_valuation -Atc "SELECT count(*) FROM valuation.rule_versions WHERE status = 'PUBLISHED'"
```

Expected: `0`. If the result is nonzero, stop this task and report the affected rule-version IDs; do not invent source documents or mutate their status.

- [ ] **Step 4: Create migration `0007`**

Create a normal Alembic module with:

```python
revision: str = "20260825_0007"
down_revision: Union[str, Sequence[str], None] = "20260825_0006"
```

Its `upgrade()` must execute SQL equivalent to the following complete contract:

```sql
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM valuation.rule_versions WHERE status = 'PUBLISHED'
    ) THEN
        RAISE EXCEPTION
            'published rule versions require an explicit knowledge source before 0007';
    END IF;
END
$$;

CREATE TABLE valuation.extraction_runs (
    extraction_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    document_id uuid NOT NULL,
    document_version integer NOT NULL,
    run_no integer NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'PENDING',
    extractor_name varchar(100) NOT NULL,
    extractor_version varchar(100),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    error_code varchar(100),
    error_message text,
    CONSTRAINT fk_extraction_runs_document
        FOREIGN KEY (case_id, document_id)
        REFERENCES valuation.documents(case_id, document_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_extraction_runs_document_version_run
        UNIQUE (document_id, document_version, run_no),
    CONSTRAINT ck_extraction_runs_document_version CHECK (document_version > 0),
    CONSTRAINT ck_extraction_runs_run_no CHECK (run_no > 0),
    CONSTRAINT ck_extraction_runs_status CHECK (
        status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')
    ),
    CONSTRAINT ck_extraction_runs_completion CHECK (
        (status IN ('PENDING', 'PROCESSING') AND completed_at IS NULL)
        OR (status = 'COMPLETED' AND completed_at IS NOT NULL
            AND error_code IS NULL AND error_message IS NULL)
        OR (status = 'FAILED' AND completed_at IS NOT NULL
            AND nullif(btrim(error_code), '') IS NOT NULL)
    ),
    CONSTRAINT ck_extraction_runs_times CHECK (
        completed_at IS NULL OR completed_at >= started_at
    )
);

CREATE TABLE valuation.extracted_fields (
    extracted_field_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_run_id uuid NOT NULL,
    field_code varchar(100) NOT NULL,
    field_path varchar(500) NOT NULL,
    value_type varchar(20) NOT NULL,
    raw_text text NOT NULL,
    normalized_value jsonb NOT NULL,
    page_number integer NOT NULL,
    bounding_box jsonb,
    confidence numeric(7,6),
    verification_status varchar(20) NOT NULL DEFAULT 'AUTO_EXTRACTED',
    verified_by_user_id uuid,
    verified_at timestamptz,
    is_official boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_extracted_fields_run
        FOREIGN KEY (extraction_run_id)
        REFERENCES valuation.extraction_runs(extraction_run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_extracted_fields_verified_by
        FOREIGN KEY (verified_by_user_id) REFERENCES auth.users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT uq_extracted_fields_run_path
        UNIQUE (extraction_run_id, field_code, field_path),
    CONSTRAINT ck_extracted_fields_type CHECK (
        value_type IN ('DECIMAL', 'TEXT', 'DATE', 'BOOLEAN', 'JSON')
    ),
    CONSTRAINT ck_extracted_fields_page CHECK (page_number > 0),
    CONSTRAINT ck_extracted_fields_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    ),
    CONSTRAINT ck_extracted_fields_verification CHECK (
        verification_status IN ('AUTO_EXTRACTED', 'VERIFIED', 'REJECTED')
    ),
    CONSTRAINT ck_extracted_fields_verifier CHECK (
        (verification_status = 'VERIFIED'
            AND verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)
        OR (verification_status <> 'VERIFIED'
            AND verified_by_user_id IS NULL AND verified_at IS NULL)
    ),
    CONSTRAINT ck_extracted_fields_official CHECK (
        NOT is_official OR verification_status <> 'REJECTED'
    ),
    CONSTRAINT ck_extracted_fields_text CHECK (
        nullif(btrim(field_code), '') IS NOT NULL
        AND nullif(btrim(field_path), '') IS NOT NULL
        AND nullif(btrim(raw_text), '') IS NOT NULL
    )
);

CREATE INDEX idx_extraction_runs_document_latest
    ON valuation.extraction_runs(document_id, document_version, run_no DESC);
CREATE INDEX idx_extracted_fields_run_official
    ON valuation.extracted_fields(extraction_run_id, field_code)
    WHERE is_official = true;

ALTER TABLE valuation.rule_versions
    ADD COLUMN applicable_case_type varchar(50),
    ADD COLUMN applicable_district_code varchar(20),
    ADD COLUMN selection_priority integer NOT NULL DEFAULT 0,
    ADD COLUMN source_document_id uuid,
    ADD CONSTRAINT ck_rule_versions_selection_priority
        CHECK (selection_priority >= 0),
    ADD CONSTRAINT fk_rule_versions_source_document
        FOREIGN KEY (source_document_id)
        REFERENCES knowledge.documents(document_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    ADD CONSTRAINT ck_rule_versions_published_source CHECK (
        status <> 'PUBLISHED' OR source_document_id IS NOT NULL
    );

CREATE INDEX idx_rule_versions_selection
    ON valuation.rule_versions(
        status, applicable_case_type, applicable_district_code,
        effective_from, selection_priority DESC
    );
```

`downgrade()` must drop `idx_rule_versions_selection`, the four rule-version constraints/columns, both extraction indexes, `valuation.extracted_fields`, then `valuation.extraction_runs`, in dependency-safe order.

- [ ] **Step 5: Build and validate migration on an isolated database**

Run each command separately:

```powershell
rtk docker compose --env-file .env.example build migrate
rtk docker compose --env-file .env.example exec -T db createdb -U app_user land_valuation_migration_test_0007
rtk docker compose --env-file .env.example run --rm -e POSTGRES_DB=land_valuation_migration_test_0007 migrate alembic upgrade head
rtk docker compose --env-file .env.example run --rm -e POSTGRES_DB=land_valuation_migration_test_0007 migrate alembic downgrade 20260825_0006
rtk docker compose --env-file .env.example run --rm -e POSTGRES_DB=land_valuation_migration_test_0007 migrate alembic upgrade head
```

Expected: all Alembic commands exit 0 and end at `20260825_0007`.

- [ ] **Step 6: Apply `0007` to the main development database and verify GREEN**

Run:

```powershell
rtk docker compose --env-file .env.example run --rm migrate alembic upgrade head
rtk docker compose --env-file .env.example exec -T db psql -U app_user -d land_valuation -Atc "SELECT version_num FROM alembic_version"
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_schema_contract.py -q
```

Expected: revision is `20260825_0007`; schema tests pass.

- [ ] **Step 7: Commit the schema contract**

```powershell
rtk git add migrations/versions/20260825_0007_add_trusted_review_inputs.py app/review/tests/test_schema_contract.py
rtk git commit -m "feat(review): add trusted extraction schema"
```

---

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
