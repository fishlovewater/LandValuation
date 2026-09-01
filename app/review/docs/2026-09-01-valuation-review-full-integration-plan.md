# Valuation and Review Full Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 `origin/feature/valuation` 的完整輔助估價能力整合進 Review 基礎，並以不可變 Submission Snapshot 串接送審、退回、重送及核准。

**Architecture:** `valuation.*` 保有案件、文件、擷取、表單、計算、規則、檢核及 Submission 的權威資料；`review.*` 只消費指定 Submission 的 Snapshot，保存審查 Run、finding、決策、退回與報告。Alembic 保留 Review 至 `20260830_0008` 的歷史，再用四支新 migration 移植 Valuation 最終 schema 及 handoff。

**Tech Stack:** Python 3.13、FastAPI、Pydantic v2、SQLAlchemy 2 async、Alembic、PostgreSQL 16/pgvector、MinIO、pytest、Docker Compose、原生 HTML/JavaScript Review workbench。

## Global Constraints

- 工作分支固定為 `feature/integrate-valuation-review`；基準是 `feature/review@f17e984`，Valuation 來源是 `origin/feature/valuation@61611a5`。
- 不修改、merge、rebase、刪除或 push `feature/review`、`origin/feature/valuation`、`main`；未經使用者明確同意不 push 或 merge 整合分支。
- Review Alembic `20260823_0001` 至 `20260830_0008` 不得改寫。
- 共用 schema、欄位、provider、狀態及 constraint 以 Valuation 最終演進為準；不得保留第二套 Review extraction source of truth。
- PostgreSQL 只存結構化資料、metadata、法規文字、向量及 object key；PDF、圖片、附件和原始法規文件本體只存 MinIO。
- MinIO object key 必須是 versioned relative key，不得保存固定 localhost URL，不得覆寫歷史物件。
- 正式數值使用 `Decimal`；Snapshot 以固定十進位字串序列化，不得經 float。
- Submission、Run、finding、decision、correction request 及報告歷史不可覆寫。
- 測試必須使用隔離 PostgreSQL database、隔離 MinIO bucket/prefix 及一次性容器；無論成功失敗都清理，最後驗證零殘留。
- PostgreSQL migration/cleanup 使用管理連線；API 與行為測試使用 `land_valuation_app` 群組成員的 runtime 連線，兩者不得共用角色。
- 不把 Demo/fake rows 寫進 migration 或開發資料庫。
- 每個任務依 TDD 執行，先看到指定失敗，再寫最小實作；每個任務只提交其列出的檔案。

---

## File and responsibility map

### Upstream Valuation import

- `app/valuation/**`: 從 `origin/feature/valuation@61611a5` 移植估價 domain；保留其內部模組邊界。
- `app/ai_assistant/**`: 移植 Valuation 使用的 AI assistant provider、tool 及 session flow。
- `app/api/router.py`: 同時註冊 auth、Valuation、AI assistant 與 Review routers。
- `app/core/config.py`: 合併 Review 設定與 OCR/Textract/AI/Maps 設定，不能整檔覆蓋。
- `app/storage/service.py`, `app/storage/paths.py`: 合併 versioned object path 能力，保留 Review 既有下載/預覽契約。
- `requirements.txt`, `Dockerfile.api`: 取兩分支依賴聯集；保留 `python-docx`，加入 OCR/PDF 依賴。

### New integration boundary

- `app/valuation/submissions/schemas.py`: submit command/response 與 Snapshot typed contract。
- `app/valuation/submissions/snapshot.py`: canonical Snapshot 建立、Decimal normalization、SHA-256 fingerprint。
- `app/valuation/submissions/repository.py`: case/review locks、idempotency lookup、Submission persistence。
- `app/valuation/submissions/service.py`: readiness gate 與單一送審 transaction。
- `app/valuation/submissions/router.py`: `POST /valuation/cases/{case_id}/submit-for-review`。
- `app/valuation/models.py`: `ReviewSubmissionRecord` 及 Valuation status/model 對齊。
- `app/review/models.py`: `latest_submission_id` 與 `validation_runs.submission_id` ORM mapping。
- `app/review/repository.py`, `app/review/service.py`: Review 一律從鎖定的 Submission Snapshot 建立 Run。
- `app/review/correction_service.py`: 退回/重送狀態同步，但不直接改正式 Valuation 值。
- `app/review/workbench_repository.py`, `app/review/workbench_schemas.py`: queue/detail 顯示 submission number 及 submitted time。

### Database

- `migrations/versions/20260901_0009_canonical_valuation_extraction.py`
- `migrations/versions/20260901_0010_valuation_forms_calculation_reports.py`
- `migrations/versions/20260901_0011_valuation_rule_pack_sources.py`
- `migrations/versions/20260901_0012_valuation_review_submission_handoff.py`

### Verification

- `docker-compose.integration.yml`: 一次性 PostgreSQL、MinIO、migration、API test stack，不宣告 named external volume。
- `scripts/run-integration-tests.ps1`: 產生 run ID，啟動、測試、清理、殘留檢查。
- `tests/integration/**`: migration、schema contract、submission E2E 與 MinIO immutability。
- `tests/test_valuation_*.py`, `tests/test_*report*.py`: Valuation upstream regression tests。
- `app/review/tests/**`: Review regression、snapshot scope、correction/resubmission 與 UI contract。

---

### Task 1: Isolated PostgreSQL and MinIO integration harness

**Files:**
- Create: `docker-compose.integration.yml`
- Create: `scripts/run-integration-tests.ps1`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/schema_assertions.py`
- Create: `tests/integration/sql/001_runtime_role.sql`
- Create: `tests/integration/test_environment_isolation.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Docker Engine and the existing `Dockerfile.api` / `Dockerfile.migrations`.
- Produces: `scripts/run-integration-tests.ps1 -PytestArgs <string>`; fixtures `db_cursor`, `admin_cursor`, and `alembic_to(revision: str)`; environment variables `TEST_RUN_ID`, `POSTGRES_DB`, `APP_POSTGRES_USER`, `MINIO_BUCKET`; guaranteed `docker compose down --volumes --remove-orphans` in `finally`.

- [ ] **Step 1: Write the failing isolation test**

```python
# tests/integration/test_environment_isolation.py
import os


def test_integration_environment_is_run_scoped():
    run_id = os.environ["TEST_RUN_ID"]
    assert run_id.startswith("vr-")
    assert os.environ["POSTGRES_DB"] == f"land_valuation_test_{run_id.replace('-', '_')}"
    assert os.environ["MINIO_BUCKET"] == f"land-valuation-test-{run_id}"
    assert os.environ.get("APP_ENV") == "test"
```

- [ ] **Step 2: Verify that the harness does not exist yet**

Run: `Test-Path scripts/run-integration-tests.ps1`

Expected: `False`.

- [ ] **Step 3: Add an ephemeral Compose stack**

Create `docker-compose.integration.yml` with project-scoped services named `db`, `minio`, `minio-init`, `migrate`, and `test`; do not set `container_name`, and use anonymous/project volumes only. The test service command is:

```yaml
command: ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
environment:
  APP_ENV: test
  TEST_RUN_ID: ${TEST_RUN_ID}
  POSTGRES_DB: ${POSTGRES_DB}
  MINIO_BUCKET: ${MINIO_BUCKET}
```

The `minio-init` service creates exactly `${MINIO_BUCKET}`. The `test` service bind-mounts the current checkout read-only at `/workspace` and uses `/tmp` for pytest temporary files.

PostgreSQL starts with a migration-owner account. `tests/integration/sql/001_runtime_role.sql` creates the NOLOGIN group `land_valuation_app` and the run-scoped `${APP_POSTGRES_USER}` member through the DB init wrapper. `migrate` uses the owner URL; `test` and API behavior use the runtime URL. The two URLs must differ by username.

- [ ] **Step 4: Add database contract fixtures**

`tests/integration/conftest.py` creates the default rollback-safe `db_cursor` from runtime `DATABASE_URL`, creates `admin_cursor` from `MIGRATION_DATABASE_URL`, asserts the usernames differ, and exposes this exact migration fixture using the migration URL:

```python
@pytest.fixture
def alembic_to():
    def migrate(revision: str, *, expect_success: bool = True):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            capture_output=True,
            text=True,
        )
        assert (result.returncode == 0) is expect_success, result.stdout + result.stderr
        return result
    return migrate
```

`tests/integration/schema_assertions.py` implements `table_exists`, `column_names`, `unique_columns`, `numeric_precision_scale`, and `check_accepts` by querying `information_schema` and `pg_catalog`; no test may infer schema from ORM metadata.

- [ ] **Step 5: Add cleanup and residue assertions**

The PowerShell script must use this control structure:

```powershell
param([string]$PytestArgs = "")
$runId = "vr-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
$project = "valuation-review-$runId"
$env:TEST_RUN_ID = $runId
$env:POSTGRES_DB = "land_valuation_test_" + $runId.Replace("-", "_")
$env:MINIO_BUCKET = "land-valuation-test-$runId"
$env:APP_ENV = "test"
$env:PYTEST_ARGS = $PytestArgs
try {
    docker compose -p $project -f docker-compose.integration.yml up --build --abort-on-container-exit --exit-code-from test
    if ($LASTEXITCODE -ne 0) { throw "integration tests failed" }
}
finally {
    docker compose -p $project -f docker-compose.integration.yml down --volumes --remove-orphans
    $residue = docker ps -a --filter "label=com.docker.compose.project=$project" --format "{{.ID}}"
    if ($residue) { throw "test containers remain: $residue" }
    $volumes = docker volume ls --filter "label=com.docker.compose.project=$project" --format "{{.Name}}"
    if ($volumes) { throw "test volumes remain: $volumes" }
}
```

Pass `$PytestArgs` to the test service through an explicit `PYTEST_ARGS` environment variable; never build a PowerShell command with `Invoke-Expression`.

- [ ] **Step 6: Run only the isolation test**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_environment_isolation.py"`

Expected: `1 passed`, followed by no matching containers or volumes.

- [ ] **Step 7: Commit the harness**

```bash
git add .gitignore docker-compose.integration.yml scripts/run-integration-tests.ps1 tests/integration/conftest.py tests/integration/schema_assertions.py tests/integration/sql/001_runtime_role.sql tests/integration/test_environment_isolation.py
git commit -m "test(integration): add isolated postgres and minio harness"
```

---

### Task 2: Import Valuation runtime without overwriting Review

**Files:**
- Create: `app/valuation/**`
- Create: `app/ai_assistant/**`
- Create: `app/core/swagger_docs.py`
- Create: `app/storage/paths.py`
- Create: `tests/test_integration_surface.py`
- Create: Valuation tests listed by `git ls-tree -r --name-only origin/feature/valuation tests`
- Modify: `app/api/router.py`
- Modify: `app/core/config.py`
- Modify: `app/storage/service.py`
- Modify: `requirements.txt`
- Modify: `Dockerfile.api`
- Modify: `.env.example`

**Interfaces:**
- Consumes: exact upstream files from `origin/feature/valuation@61611a5`.
- Produces: all upstream Valuation routes under `/api/v1/valuation`, AI assistant routes under `/api/v1/ai-assistant`, and existing Review routes unchanged under `/api/v1/review`.

- [ ] **Step 1: Add a failing router coexistence test**

```python
# tests/test_integration_surface.py
from app.main import create_app


def test_valuation_and_review_routes_coexist():
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/valuation/cases" in paths
    assert "/api/v1/review/workbench/cases" in paths
    assert "/api/v1/ai-assistant/sessions" in paths
```

- [ ] **Step 2: Run the test and observe the missing Valuation route**

Run: `python -m pytest tests/test_integration_surface.py -q`

Expected: FAIL because `/api/v1/valuation/cases` is absent.

- [ ] **Step 3: Restore only upstream-owned directories and tests**

```bash
git restore --source origin/feature/valuation -- app/valuation app/ai_assistant app/core/swagger_docs.py app/storage/paths.py
git restore --source origin/feature/valuation -- tests/test_ai_provider.py tests/test_auto_workflow.py tests/test_complete_draft_pdf.py tests/test_confirmation_export_excel.py tests/test_day4_day5_operations.py tests/test_document_workflow.py tests/test_extraction_provider.py tests/test_f01_f04.py tests/test_f03_ai_schemas.py tests/test_facility_service.py tests/test_field_analysis.py tests/test_formal_report_calculation.py tests/test_formal_report_service_guards.py tests/test_google_maps_client.py tests/test_official_form_templates.py tests/test_official_pdf_builder.py tests/test_pdf_errors.py tests/test_report_packages.py tests/test_report_page_schemas.py tests/test_report_page_service.py tests/test_rule_ai_extraction.py tests/test_rule_coverage.py tests/test_rule_pack_schemas.py tests/test_rule_pack_sources.py tests/test_swagger_docs.py tests/test_three_page_draft_pdf.py tests/test_valuation_routes.py tests/test_valuation_schemas.py tests/test_valuation_service.py
```

Do not restore shared files wholesale.

- [ ] **Step 4: Merge the API router explicitly**

`app/api/router.py` must keep `review_router` and add every upstream router:

```python
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(valuation_router, prefix="/valuation", tags=["valuation"])
api_router.include_router(document_router, prefix="/valuation", tags=["valuation-documents"])
api_router.include_router(extraction_router, prefix="/valuation", tags=["valuation-extraction"])
api_router.include_router(report_package_router, prefix="/valuation", tags=["valuation-report-packages"])
api_router.include_router(operations_router, prefix="/valuation", tags=["valuation-operations"])
api_router.include_router(rule_pack_router, prefix="/valuation", tags=["valuation-rule-packs"])
api_router.include_router(facilities_router, prefix="/valuation", tags=["valuation-facilities"])
api_router.include_router(automation_router, prefix="/valuation", tags=["valuation-auto-workflow"])
api_router.include_router(ai_assistant_router, prefix="/ai-assistant", tags=["ai-assistant"])
api_router.include_router(review_router)
```

- [ ] **Step 5: Merge dependencies and configuration**

Use the union of both branches. `requirements.txt` must retain these Review dependencies while adding upstream requirements:

```text
python-docx>=1.1,<2.0
python-dotenv>=1.0,<2.0
httpx2>=2.0,<3.0
pypdf>=5.0,<7.0
openpyxl>=3.1,<4.0
reportlab>=4.2,<5.0
boto3>=1.35,<2.0
```

Merge all OCR/Textract/AI/Maps fields and validators from upstream `app/core/config.py` into the Review version. Add matching variables to `.env.example`. Add Poppler, Tesseract Traditional Chinese/English, and `fonts-wqy-zenhei` to `Dockerfile.api` in one apt layer.

- [ ] **Step 6: Run coexistence and upstream unit tests**

Run: `python -m pytest tests/test_integration_surface.py tests/test_valuation_schemas.py tests/test_extraction_provider.py tests/test_field_analysis.py tests/test_formal_report_calculation.py tests/test_rule_pack_schemas.py -q`

Expected: all selected tests PASS; Review route remains registered.

- [ ] **Step 7: Commit the runtime import**

```bash
git add app/valuation app/ai_assistant app/api/router.py app/core/config.py app/core/swagger_docs.py app/storage requirements.txt Dockerfile.api .env.example tests
git commit -m "feat(valuation): import appraisal assistant runtime"
```

---

### Task 3: Migration 0009 canonical extraction and AI assistant schema

**Files:**
- Create: `migrations/versions/20260901_0009_canonical_valuation_extraction.py`
- Create: `tests/integration/test_migration_0009_extraction.py`
- Modify: `app/valuation/models.py`
- Modify: `app/review/trusted_inputs.py`
- Modify: `app/review/tests/test_trusted_inputs.py`

**Interfaces:**
- Consumes: Review head `20260830_0008`; upstream final DDL from Valuation migrations `0005`, `0006`, `0007`, `0008`, `0015`, `0016`.
- Produces: canonical `valuation.document_extractions`, canonical `valuation.extracted_fields`, assistant session/message tables; Review trusted input reads APPLIED `confirmed_value`.

- [ ] **Step 1: Write failing schema assertions**

```python
def test_canonical_extraction_contract(db_cursor):
    assert column_names(db_cursor, "valuation", "document_extractions") >= {
        "extraction_id", "extraction_status", "provider", "document_id"
    }
    assert column_names(db_cursor, "valuation", "extracted_fields") >= {
        "extraction_id", "form_code", "field_name", "extracted_value",
        "source_page", "source_text", "analysis_provider", "field_status",
        "confirmed_value", "confirmed_by_user_id", "confirmed_at",
        "applied_form_instance_id", "applied_at",
    }
    assert not table_exists(db_cursor, "valuation", "extraction_runs")
    assert unique_columns(db_cursor, "valuation", "extracted_fields") == {
        ("extraction_id", "form_code", "field_name")
    }
```

Add a second test that inserts a non-Demo legacy extraction row at `0008` and expects the `0009` upgrade to fail with `non-demo legacy extraction data prevents migration`.

- [ ] **Step 2: Verify failure at Review head**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0009_extraction.py"`

Expected: FAIL because migration `20260901_0009` and canonical tables do not exist.

- [ ] **Step 3: Build a single post-0008 migration**

Set:

```python
revision = "20260901_0009"
down_revision = "20260830_0008"
```

Before dropping legacy tables, execute a guarded block equivalent to:

```sql
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM valuation.extraction_runs er
    JOIN valuation.cases c ON c.case_id = er.case_id
    WHERE c.case_no <> 'DEMO-REVIEW-001'
  ) THEN
    RAISE EXCEPTION 'non-demo legacy extraction data prevents migration';
  END IF;
END $$;
```

Delete only `DEMO-REVIEW-001` Review dependencies in FK-safe order, drop the legacy `valuation.extracted_fields` then `valuation.extraction_runs`, and port the exact final upgrade DDL from:

```text
20260825_0005_f03_assistant_workflow.py
20260825_0006_add_local_ocr_provider.py
20260825_0007_add_field_analysis_provenance.py
20260826_0008_allow_codex_candidate_provenance.py
20260828_0015_allow_xlsx_extraction_provider.py
20260830_0016_scope_extracted_fields_by_form.py
```

The final provider check is `LOCAL_PDF`, `LOCAL_OCR`, `LOCAL_XLSX`, `TEXTRACT`; the final unique constraint is `(extraction_id, form_code, field_name)`.

- [ ] **Step 4: Switch Review trusted inputs to canonical APPLIED fields**

The repository query must select only:

```sql
WHERE ef.case_id = :case_id
  AND ef.field_status = 'APPLIED'
  AND ef.confirmed_value IS NOT NULL
```

Map Review values from `ef.form_code`, `ef.field_name`, `ef.confirmed_value`, `ef.source_page`, and `ef.source_text`. Remove all reads of `extraction_run_id`, legacy `field_code`, and legacy normalized-value columns.

- [ ] **Step 5: Run migration and trusted-input tests**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0009_extraction.py app/review/tests/test_trusted_inputs.py"`

Expected: PASS, including the destructive-data guard.

- [ ] **Step 6: Commit 0009**

```bash
git add migrations/versions/20260901_0009_canonical_valuation_extraction.py app/valuation/models.py app/review/trusted_inputs.py app/review/tests/test_trusted_inputs.py tests/integration/test_migration_0009_extraction.py
git commit -m "feat(db): add canonical valuation extraction schema"
```

---

### Task 4: Migration 0010 forms, calculations, validation, and reports

**Files:**
- Create: `migrations/versions/20260901_0010_valuation_forms_calculation_reports.py`
- Create: `tests/integration/test_migration_0010_forms_reports.py`
- Modify: `app/valuation/models.py`

**Interfaces:**
- Consumes: `20260901_0009`; upstream final DDL from Valuation `0009`, `0010`, and `75dcc9441ca7`.
- Produces: request-correlated calculation/validation events, complete report schema, expanded form codes, benchmark latitude/longitude.

- [ ] **Step 1: Write failing final-schema tests**

Assert exact contracts for `form_instances.form_content`, supported form-code check, comparison display order, factor-level FKs, `comparison_analyses.calculation_snapshot`, `request_id` indexes, and `benchmark_lands.latitude/longitude Numeric(10,7)`.

```python
def test_benchmark_coordinates_are_decimal(db_cursor):
    assert numeric_precision_scale(db_cursor, "valuation", "benchmark_lands", "latitude") == (10, 7)
    assert numeric_precision_scale(db_cursor, "valuation", "benchmark_lands", "longitude") == (10, 7)
```

- [ ] **Step 2: Verify failure at 0009**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0010_forms_reports.py"`

Expected: FAIL on missing `form_content` or coordinate columns.

- [ ] **Step 3: Port the final DDL into one linear migration**

Set `revision = "20260901_0010"` and `down_revision = "20260901_0009"`. Port upgrade effects from:

```text
20260826_0009_day4_day5_workflow.py
20260826_0010_complete_report_day1.py
75dcc9441ca7_add_latitude_and_longitude_to_benchmark_.py
```

Do not copy their old revision IDs. Preserve all FK, check, unique index, JSON object checks, request correlation indexes, and comments. Downgrade reverses only objects created by this migration and first blocks downgrade when incompatible rows exist.

- [ ] **Step 4: Run focused Valuation calculation/report tests**

Run: `python -m pytest tests/test_day4_day5_operations.py tests/test_f01_f04.py tests/test_formal_report_calculation.py tests/test_report_packages.py tests/test_official_pdf_builder.py -q`

Expected: all selected tests PASS.

- [ ] **Step 5: Run the real migration test**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0010_forms_reports.py"`

Expected: PASS.

- [ ] **Step 6: Commit 0010**

```bash
git add migrations/versions/20260901_0010_valuation_forms_calculation_reports.py app/valuation/models.py tests/integration/test_migration_0010_forms_reports.py
git commit -m "feat(db): add valuation forms calculations and reports"
```

---

### Task 5: Migration 0011 versioned rule-pack sources

**Files:**
- Create: `migrations/versions/20260901_0011_valuation_rule_pack_sources.py`
- Create: `tests/integration/test_migration_0011_rule_sources.py`
- Modify: `app/valuation/models.py`

**Interfaces:**
- Consumes: `20260901_0010`; upstream final DDL from Valuation `0011`–`0014`.
- Produces: rule applicability, multiple sources, draft effective-date state, `EXAMPLE_REFERENCE` document classification.

- [ ] **Step 1: Write failing rule-source contract tests**

```python
def test_rule_source_contract(db_cursor):
    assert table_exists(db_cursor, "valuation", "rule_version_sources")
    assert column_names(db_cursor, "valuation", "rule_versions") >= {
        "jurisdiction_code", "district_scope", "land_use_types", "formula_code",
        "rounding_code", "import_status", "import_summary",
        "verified_by_user_id", "verified_at", "effective_date_status",
    }
    assert check_accepts(db_cursor, "knowledge", "documents", "document_type", "EXAMPLE_REFERENCE")
```

- [ ] **Step 2: Verify failure at 0010**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0011_rule_sources.py"`

Expected: FAIL because `rule_version_sources` is absent.

- [ ] **Step 3: Port final rule-source DDL**

Set `revision = "20260901_0011"` and `down_revision = "20260901_0010"`. Port final upgrade effects, comments and downgrade guards from:

```text
20260827_0011_rule_pack_sources.py
20260827_0012_multi_source_rule_packs.py
20260827_0013_rule_pack_draft_dates.py
20260827_0014_example_reference_policy.py
```

The implementation must retain one-primary-source uniqueness, source order uniqueness, JSON type checks, New Taipei jurisdiction constraint, verification pairing, and draft-date consistency.

- [ ] **Step 4: Run rule tests and migration test**

Run: `python -m pytest tests/test_rule_pack_schemas.py tests/test_rule_pack_sources.py tests/test_rule_coverage.py tests/test_rule_ai_extraction.py -q`

Expected: PASS.

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0011_rule_sources.py"`

Expected: PASS.

- [ ] **Step 5: Commit 0011**

```bash
git add migrations/versions/20260901_0011_valuation_rule_pack_sources.py app/valuation/models.py tests/integration/test_migration_0011_rule_sources.py
git commit -m "feat(db): add versioned rule pack sources"
```

---

### Task 6: Migration 0012 immutable Submission handoff schema

**Files:**
- Create: `migrations/versions/20260901_0012_valuation_review_submission_handoff.py`
- Create: `tests/integration/test_migration_0012_submission.py`
- Modify: `app/valuation/models.py`
- Modify: `app/review/models.py`
- Modify: `app/valuation/schemas.py`
- Modify: `app/review/schemas.py`

**Interfaces:**
- Consumes: `20260901_0011`.
- Produces: `valuation.review_submissions`; `review.reviews.latest_submission_id`; `valuation.validation_runs.submission_id`; handoff statuses and DB immutability trigger.

- [ ] **Step 1: Write failing handoff schema tests**

```python
def test_submission_schema(db_cursor):
    assert column_names(db_cursor, "valuation", "review_submissions") == {
        "submission_id", "review_id", "case_id", "submission_no",
        "submitted_by_user_id", "submitted_at", "source_validation_run_id",
        "source_report_document_id", "input_snapshot", "input_fingerprint",
        "supersedes_submission_id", "request_id",
    }
    assert unique_columns(db_cursor, "valuation", "review_submissions") >= {
        ("review_id", "submission_no"), ("case_id", "request_id")
    }
```

Add tests that an `UPDATE` and `DELETE` executed through `db_cursor` both fail with `review submissions are immutable`, the same cleanup through `admin_cursor` succeeds only in the isolated test database, and the composite supersedes FK rejects a Submission from another Review.

- [ ] **Step 2: Verify failure at 0011**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0012_submission.py"`

Expected: FAIL because `review_submissions` is absent.

- [ ] **Step 3: Implement exact handoff DDL**

Set:

```python
revision = "20260901_0012"
down_revision = "20260901_0011"
```

Create the 12-column table from the approved design, including `CHECK (submission_no > 0)`, `CHECK (input_fingerprint ~ '^[0-9a-f]{64}$')`, `CHECK (jsonb_typeof(input_snapshot) = 'object')`, unique `(review_id, submission_no)`, unique `(case_id, request_id)`, unique `(review_id, submission_id)`, and composite self-FK `(review_id, supersedes_submission_id)`.

Add nullable `review.reviews.latest_submission_id`, then its FK after table creation. Add nullable `valuation.validation_runs.submission_id` plus index and FK. Expand Valuation case status constraint with `IN_REVIEW`, `REVISION_REQUIRED`, `REVIEW_COMPLETED`; retain Review `RETURNED_FOR_REVISION`.

Create a trigger function that raises `review submissions are immutable` on `UPDATE OR DELETE` when `pg_has_role(current_user, 'land_valuation_app', 'MEMBER')` is true. The migration-owner role is not a member, so downgrade and verified isolated cleanup can remove test history. Downgrade drops trigger, FKs, columns and table in reverse dependency order and blocks if integrated Submission rows exist.

- [ ] **Step 4: Add matching ORM and Pydantic types**

```python
class ReviewSubmissionRecord(Base):
    __tablename__ = "review_submissions"
    __table_args__ = {"schema": "valuation"}
    submission_id: Mapped[UUID]
    review_id: Mapped[UUID]
    case_id: Mapped[UUID]
    submission_no: Mapped[int]
    input_snapshot: Mapped[dict]
    input_fingerprint: Mapped[str]
```

Add all remaining columns with exact nullability from the design. Add `latest_submission_id` to `Review` and `submission_id` to `ValidationRun`; do not add write methods for historic Submission mutation.

- [ ] **Step 5: Run schema and ORM tests**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_migration_0012_submission.py app/review/tests/test_schema_contract.py"`

Expected: PASS.

- [ ] **Step 6: Commit 0012**

```bash
git add migrations/versions/20260901_0012_valuation_review_submission_handoff.py app/valuation/models.py app/valuation/schemas.py app/review/models.py app/review/schemas.py tests/integration/test_migration_0012_submission.py app/review/tests/test_schema_contract.py
git commit -m "feat(db): add immutable valuation review submissions"
```

---

### Task 7: Canonical Snapshot and submit-for-review command

**Files:**
- Create: `app/valuation/submissions/__init__.py`
- Create: `app/valuation/submissions/schemas.py`
- Create: `app/valuation/submissions/snapshot.py`
- Create: `app/valuation/submissions/repository.py`
- Create: `app/valuation/submissions/service.py`
- Create: `app/valuation/submissions/router.py`
- Create: `tests/test_submission_snapshot.py`
- Create: `tests/test_submission_service.py`
- Create: `tests/test_submission_api.py`
- Modify: `app/api/router.py`
- Modify: `app/auth/service.py`

**Interfaces:**
- Consumes: APPLIED `confirmed_value`, formal calculations, completed source validation run, report document metadata, application user and request ID.
- Produces: `SubmissionService.submit(case_id: UUID, command: SubmitForReviewCommand, actor: User) -> SubmitForReviewResult`; canonical `snapshot_bytes()` and `snapshot_fingerprint()`.

- [ ] **Step 1: Write failing Decimal canonicalization tests**

```python
def test_snapshot_decimal_is_stable_string():
    snapshot = build_submission_snapshot(
        case_version=3,
        applied_fields=[{"form_code": "F03", "field_name": "unit_price", "confirmed_value": Decimal("123.4500")}],
        calculations={"total": Decimal("246.9000")},
        documents=[],
        validation={},
    )
    assert snapshot["applied_fields"][0]["confirmed_value"] == "123.4500"
    assert snapshot["calculations"]["total"] == "246.9000"
    assert snapshot_fingerprint(snapshot) == snapshot_fingerprint(snapshot)
```

Also assert dictionary input order does not affect the fingerprint and that float input raises `TypeError("float is not allowed in submission snapshots")`.

- [ ] **Step 2: Run and observe missing module failure**

Run: `python -m pytest tests/test_submission_snapshot.py -q`

Expected: FAIL with `ModuleNotFoundError: app.valuation.submissions`.

- [ ] **Step 3: Implement the typed command and canonical encoder**

```python
class SubmitForReviewCommand(BaseModel):
    request_id: UUID
    expected_case_version: int = Field(ge=1)
    source_validation_run_id: UUID
    source_report_document_id: UUID


def snapshot_bytes(snapshot: dict) -> bytes:
    normalized = normalize_snapshot_value(snapshot)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def snapshot_fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(snapshot_bytes(snapshot)).hexdigest()
```

`normalize_snapshot_value` recursively preserves Decimal scale with `format(value, "f")`, sorts mapping keys through JSON encoding, converts UUID/datetime to strings, and rejects float.

- [ ] **Step 4: Write failing service tests for authorization, readiness, lock, and idempotency**

Cover: wrong owner/permission → 403; stale version → 409; non-completed source run → 422; report not owned by case/version → 404; missing APPLIED values → 422; first submit creates Review + Submission; retry returns same IDs; reused request with different inputs → 409; concurrent request yields one Submission.

- [ ] **Step 5: Implement one transaction in the service**

The repository interface is fixed:

```python
class SubmissionRepository:
    async def lock_case(self, case_id: UUID):
        raise NotImplementedError
    async def find_by_request(self, case_id: UUID, request_id: UUID):
        raise NotImplementedError
    async def lock_review_for_case(self, case_id: UUID):
        raise NotImplementedError
    async def load_submission_inputs(self, case_id: UUID, command: SubmitForReviewCommand):
        raise NotImplementedError
    async def create_review(self, case_id: UUID, actor_id: UUID):
        raise NotImplementedError
    async def create_submission(self, record: ReviewSubmissionRecord):
        raise NotImplementedError
    async def record_case_event(self, case_id: UUID, event_type: str, request_id: UUID, data: dict):
        raise NotImplementedError
```

`SubmissionService.submit` locks first, checks `expected_case_version`, derives Snapshot server-side, creates or reuses Review, assigns `submission_no`, writes Submission, sets `latest_submission_id`, transitions case to `IN_REVIEW`, writes `SUBMITTED_FOR_REVIEW`, flushes once, and commits through the request session boundary. It never accepts a client Snapshot.

- [ ] **Step 6: Add the API route and permission**

```python
@router.post(
    "/cases/{case_id}/submit-for-review",
    response_model=SubmitForReviewResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_for_review(case_id: UUID, payload: SubmitForReviewCommand, session: DbSession, user=Depends(require_permissions("valuation.submit_review"))):
    return await SubmissionService(session).submit(case_id, payload, user)
```

Register this router under `/valuation`. Add `valuation.submit_review` to permission codes and the appraiser role seed without granting it to Review-only users.

- [ ] **Step 7: Run snapshot, service, and API tests**

Run: `python -m pytest tests/test_submission_snapshot.py tests/test_submission_service.py tests/test_submission_api.py -q`

Expected: PASS.

- [ ] **Step 8: Commit the submit command**

```bash
git add app/valuation/submissions app/api/router.py app/auth/service.py tests/test_submission_snapshot.py tests/test_submission_service.py tests/test_submission_api.py
git commit -m "feat(valuation): submit immutable snapshots for review"
```

---

### Task 8: Scope Review queue and Runs to the latest Submission

**Files:**
- Modify: `app/review/repository.py`
- Modify: `app/review/service.py`
- Modify: `app/review/workbench_repository.py`
- Modify: `app/review/workbench_schemas.py`
- Modify: `app/review/workbench_service.py`
- Modify: `app/review/tests/test_runs_api.py`
- Modify: `app/review/tests/test_service.py`
- Create: `app/review/tests/test_submission_scope.py`
- Modify: `app/review/tests/test_workbench_service.py`

**Interfaces:**
- Consumes: `review.latest_submission_id` and immutable `valuation.review_submissions.input_snapshot`.
- Produces: every new Review Run has `submission_id`; queue/detail exposes `submission_no`, `submitted_at`; rule evaluation never reads live APPLIED values.

- [ ] **Step 1: Write failing snapshot-scope tests**

Create Submission 1 with `unit_price=100`, then change live APPLIED field to `999` before starting Review Run. Assert:

```python
assert run.submission_id == submission_1.submission_id
assert run.input_snapshot["applied_fields"][0]["confirmed_value"] == "100"
assert finding.reported_value == "100"
```

Add a queue test asserting `submission_no` and `submitted_at` come from `latest_submission_id`, not a max query over mutable case data.

- [ ] **Step 2: Run and observe live-data mismatch**

Run: `python -m pytest app/review/tests/test_runs_api.py app/review/tests/test_workbench_service.py -q`

Expected: FAIL because Run has no `submission_id` and current code builds input from live trusted inputs.

- [ ] **Step 3: Replace Run input loading**

Add repository methods:

```python
async def get_latest_submission_for_review(self, review_id: UUID, for_update: bool = False):
    raise NotImplementedError

async def create_run(self, *, review_id: UUID, submission_id: UUID, input_snapshot: dict, actor_id: UUID, run_no: int):
    raise NotImplementedError
```

`ReviewService.create_run` must lock Review, load exactly `latest_submission_id`, deep-copy the Submission Snapshot into `run.input_snapshot`, set `run.submission_id`, and pass only that snapshot to deterministic rule builders. If the latest Submission is missing, return `409 REVIEW_SUBMISSION_REQUIRED`.

- [ ] **Step 4: Add workbench projection fields**

```python
class WorkbenchSubmissionRead(BaseModel):
    submission_id: UUID
    submission_no: int
    submitted_at: datetime
```

Add `submission: WorkbenchSubmissionRead` to case detail and `submission_no` to queue rows. Join through `reviews.latest_submission_id`; never expose `input_snapshot`, bucket, object key, or presigned URL in queue responses.

- [ ] **Step 5: Run Review tests**

Run: `python -m pytest app/review/tests/test_runs_api.py app/review/tests/test_service.py app/review/tests/test_submission_scope.py app/review/tests/test_workbench_service.py -q`

Expected: PASS, including the live-data mutation test.

- [ ] **Step 6: Commit Review submission scope**

```bash
git add app/review/repository.py app/review/service.py app/review/workbench_repository.py app/review/workbench_schemas.py app/review/workbench_service.py app/review/tests/test_runs_api.py app/review/tests/test_service.py app/review/tests/test_submission_scope.py app/review/tests/test_workbench_service.py
git commit -m "feat(review): scope review runs to submitted snapshots"
```

---

### Task 9: Return, resubmit, and approval state synchronization

**Files:**
- Modify: `app/review/correction_service.py`
- Modify: `app/review/service.py`
- Modify: `app/valuation/submissions/service.py`
- Modify: `app/valuation/submissions/repository.py`
- Modify: `app/review/tests/test_correction_service.py`
- Modify: `app/review/tests/test_workflow_e2e.py`
- Modify: `tests/test_submission_service.py`

**Interfaces:**
- Consumes: Review decision, correction request, current Submission and locked case/review rows.
- Produces: atomic mapping `RETURNED_FOR_REVISION ↔ REVISION_REQUIRED`, next Submission with `supersedes_submission_id`, and atomic `REVIEW_COMPLETED` on both sides.

- [ ] **Step 1: Write failing lifecycle tests**

Assert this exact timeline:

```text
submission 1 / IN_REVIEW
→ Review RETURNED_FOR_REVISION + Valuation REVISION_REQUIRED
→ new Valuation case/form/document version
→ submission 2 / supersedes submission 1 / IN_REVIEW
→ new Review Run scoped to submission 2
→ Review REVIEW_COMPLETED + Valuation REVIEW_COMPLETED
```

Also assert Submission 1, its Run, findings, decisions, correction request, report document metadata, and MinIO object hash are byte-for-byte unchanged.

- [ ] **Step 2: Run and observe missing cross-system state changes**

Run: `python -m pytest app/review/tests/test_correction_service.py app/review/tests/test_workflow_e2e.py tests/test_submission_service.py -q`

Expected: FAIL because existing correction flow updates Review only.

- [ ] **Step 3: Synchronize return in one transaction**

When a correction request is sent, lock Review and its case, verify current status is reviewable, then set:

```python
review.review_status = "RETURNED_FOR_REVISION"
case.case_status = "REVISION_REQUIRED"
```

Record one correlated case event containing `review_id`, `submission_id`, and `correction_request_id`. Do not change finding decisions or formal Valuation values.

- [ ] **Step 4: Enforce resubmission lineage**

`SubmissionService.submit` accepts a case in `REVISION_REQUIRED` only when the submitted case version is newer than the previous Snapshot version. It reuses the locked Review, sets `submission_no = previous.submission_no + 1`, sets `supersedes_submission_id = previous.submission_id`, and updates `latest_submission_id` atomically.

- [ ] **Step 5: Synchronize approval in one transaction**

After the existing full approval gate succeeds, lock the linked case and set both Review and Valuation to `REVIEW_COMPLETED`, preserving the existing finding final-value rules. A stale `latest_submission_id` or a Run belonging to an older Submission returns `409 REVIEW_SUBMISSION_STALE`.

- [ ] **Step 6: Run lifecycle tests**

Run: `python -m pytest app/review/tests/test_correction_service.py app/review/tests/test_workflow_e2e.py tests/test_submission_service.py -q`

Expected: PASS.

- [ ] **Step 7: Commit lifecycle synchronization**

```bash
git add app/review/correction_service.py app/review/service.py app/valuation/submissions/service.py app/valuation/submissions/repository.py app/review/tests/test_correction_service.py app/review/tests/test_workflow_e2e.py tests/test_submission_service.py
git commit -m "feat(review): synchronize correction and approval lifecycle"
```

---

### Task 10: Workbench submission visibility and action refresh

**Files:**
- Modify: `app/review/test_ui/index.html`
- Modify: `app/review/tests/test_ui_behavior.mjs`
- Modify: `app/review/tests/test_test_ui.py`

**Interfaces:**
- Consumes: workbench queue/detail submission projection and existing correction/recheck API.
- Produces: Chinese business-facing Submission version display; state-changing actions refresh summary, queue, and detail.

- [ ] **Step 1: Add failing UI contract tests**

```javascript
assert.equal(logic.submissionLabel({submission_no: 2}), "送審版本 2")
assert.equal(logic.submissionLabel(null), "尚未正式送審")
```

Static source assertions must require visible text `送審版本` and forbid rendering `input_snapshot`, `object_key`, or raw JSON.

- [ ] **Step 2: Run and observe missing helper**

Run: `node --test app/review/tests/test_ui_behavior.mjs`

Expected: FAIL because `submissionLabel` is not exported by the harness.

- [ ] **Step 3: Implement minimal UI changes**

Add a queue/detail badge showing submission number and submitted time. Keep existing machine-result labels and human-handling labels unchanged. After submit-related refresh, correction send, recheck, and case decision, call all three:

```javascript
await Promise.all([loadSummary(), loadCases(), loadCaseDetail(activeReviewId)])
```

Do not show Snapshot JSON or expose storage metadata.

- [ ] **Step 4: Run UI static tests**

Run: `node --test app/review/tests/test_ui_behavior.mjs`

Expected: PASS.

Run: `python -m pytest app/review/tests/test_test_ui.py -q`

Expected: PASS.

- [ ] **Step 5: Commit UI visibility**

```bash
git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs app/review/tests/test_test_ui.py
git commit -m "feat(review-ui): show immutable submission versions"
```

---

### Task 11: Development-only Demo rebuild on canonical data

**Files:**
- Modify: `app/review/demo.py`
- Modify: `app/review/tests/test_demo.py`
- Modify: `app/review/DEMO_GUIDE.md` only if the file exists in this integration worktree at execution time and the user explicitly approves bringing it into scope.

**Interfaces:**
- Consumes: canonical Valuation extraction, APPLIED fields, Submission API/service and Review queue.
- Produces: `python -m app.review.demo seed|revise|reset` that can create and completely delete one development Demo without migration seed data.

- [ ] **Step 1: Write failing canonical Demo tests**

Assert seed creates `document_extractions`, APPLIED `extracted_fields`, a formal report document, Submission 1 and one Review; assert it creates zero rows in legacy `extraction_runs`. Assert reset deletes Demo Review/Valuation rows and Demo MinIO objects, then a second reset succeeds idempotently.

- [ ] **Step 2: Run and observe legacy-table dependency**

Run: `python -m pytest app/review/tests/test_demo.py -q`

Expected: FAIL because existing Demo writes legacy extraction structures or creates Review directly.

- [ ] **Step 3: Rebuild seed/revise/reset through canonical services**

Seed must call the same confirmation/APPLIED, formal calculation/report and `SubmissionService.submit` paths as production. Revise must create new Valuation versions and Submission 2. Reset must resolve exact Demo IDs/object keys from database ownership relationships before deleting and must refuse to act outside `APP_ENV=development`.

- [ ] **Step 4: Run Demo tests in isolated infrastructure**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "app/review/tests/test_demo.py"`

Expected: PASS, followed by zero run-ID containers/volumes and no Demo rows in the test database before it is removed.

- [ ] **Step 5: Commit Demo rebuild**

```bash
git add app/review/demo.py app/review/tests/test_demo.py
git commit -m "test(review): rebuild demo on canonical valuation data"
```

Do not stage `DEMO_GUIDE.md` unless the user separately authorizes it.

---

### Task 12: Full migration cycle, cross-subsystem E2E, browser acceptance, and zero-residue proof

**Files:**
- Create: `tests/integration/test_valuation_review_e2e.py`
- Create: `tests/integration/test_minio_submission_immutability.py`
- Create: `scripts/backup-and-verify.ps1`
- Create: `app/review/docs/2026-09-01-valuation-review-integration-verification.md`
- Modify: `scripts/run-integration-tests.ps1`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: reproducible verification record for upgrade/downgrade/upgrade, full workflow, browser acceptance, health and cleanup.

- [ ] **Step 1: Write the complete E2E test before running it**

The test must execute this public-service/API sequence without direct fixture shortcuts:

```text
create case
→ upload PDF/XLSX to unique MinIO keys
→ extract candidates
→ confirm and APPLIED
→ create formal forms/calculation/validation/report
→ submit-for-review (Submission 1)
→ Review Run/findings/decisions
→ correction request and return
→ new Valuation/document/form versions
→ submit-for-review (Submission 2)
→ Review Run/findings/decisions
→ approve
→ generate Review Excel/Word/PDF reports
```

Capture hashes for Submission 1 Snapshot, Run input, findings, decisions and MinIO objects before resubmission; compare the same records after approval and require equality.

- [ ] **Step 2: Add and run a readable backup gate**

`scripts/backup-and-verify.ps1` accepts `-Container`, `-Database`, `-User`, and `-OutputDirectory`; it resolves the output path, creates one timestamped custom-format backup with `pg_dump -Fc`, copies it from the DB container, and runs `pg_restore --list` against the copied file. It exits nonzero if the file is empty or the archive list lacks `TABLE DATA` entries.

Run against the isolated database first:

```powershell
pwsh -File scripts/backup-and-verify.ps1 -Container $integrationDbContainer -Database $env:POSTGRES_DB -User $env:POSTGRES_USER -OutputDirectory $env:TEMP
```

Expected: `backup readable` and an absolute `.dump` path. Delete only this isolated test backup after verification. Before any development-database migration, run the same script into a user-approved persistent backup directory and retain that file until the integration is accepted.

- [ ] **Step 3: Add explicit migration cycling**

The integration script must run:

```bash
alembic upgrade 20260830_0008
alembic upgrade 20260901_0012
alembic downgrade 20260830_0008
alembic upgrade 20260901_0012
alembic current
alembic heads
```

Expected: both final commands report only `20260901_0012 (head)` after the final upgrade. Before downgrade, run a dedicated fixture cleanup that deletes only isolated test records; never downgrade a database containing accepted history.

- [ ] **Step 4: Run all Python and Node tests in the isolated stack**

Run: `pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests app/review/tests"`

Expected: all Python tests PASS except explicitly documented environment skips; cleanup reports no containers or volumes.

Run: `node --test app/review/tests/test_ui_behavior.mjs`

Expected: all Node tests PASS.

- [ ] **Step 5: Perform real browser acceptance**

Rebuild the integration API image, open `/api/v1/review/test-ui`, and execute the full Submission 1 → correction → Submission 2 → approval workflow. Verify Network responses use the expected IDs/statuses; verify the queue, summary and detail all refresh after each state change; verify PDF page preview; verify no raw JSON/object key is visible.

Record exact browser steps, observed status transitions and report downloads in `app/review/docs/2026-09-01-valuation-review-integration-verification.md`. Do not call this complete from static Node tests alone.

- [ ] **Step 6: Verify service health and zero residue**

Record:

```text
GET /health/live = 200
GET /health/ready = 200
PostgreSQL pg_isready = accepting connections
MinIO mc ready = success
matching test containers = 0
matching test volumes = 0
matching test buckets/prefixes = 0
matching test databases = 0
```

If any cleanup assertion is nonzero, the task fails even if feature tests passed.

- [ ] **Step 7: Update operating documentation**

Document the submit endpoint request/response, handoff statuses, migration sequence, backup/readability check, downgrade limitation, isolated test command, and the rule that Review reads Submission Snapshot rather than live latest values.

- [ ] **Step 8: Run final verification before claiming completion**

Run: `git diff --check`

Expected: no output.

Run: `git status --short`

Expected: only the intended verification/README/test files for this task before commit.

- [ ] **Step 9: Commit verification artifacts**

```bash
git add tests/integration/test_valuation_review_e2e.py tests/integration/test_minio_submission_immutability.py scripts/backup-and-verify.ps1 scripts/run-integration-tests.ps1 app/review/docs/2026-09-01-valuation-review-integration-verification.md README.md
git commit -m "test(integration): verify valuation review lifecycle"
```

---

## Final acceptance gate

Before requesting merge or push approval, independently verify:

- `git log feature/review..feature/integrate-valuation-review` contains only integration-branch commits.
- `git status` in the original `feature/review` checkout still shows the user's pre-existing `AGENTS.md`, `.serena/`, and `app/review/DEMO_GUIDE.md` untouched.
- Alembic has one head: `20260901_0012`.
- Valuation and Review full suites pass from the source-mounted isolated stack.
- Browser acceptance was actually performed and recorded.
- PostgreSQL/MinIO/API health is green.
- No test database, MinIO object/bucket, container or volume remains.
- No merge or push occurs until the user explicitly approves it.
