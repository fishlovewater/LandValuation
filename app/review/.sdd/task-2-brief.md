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

