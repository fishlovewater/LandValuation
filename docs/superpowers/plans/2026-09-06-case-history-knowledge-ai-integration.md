# Case History and Knowledge AI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Case History and Knowledge AI subsystem boundaries to `feature/integrate-valuation-review` without replacing that branch's fields, models, routes, dependencies, or migration chain.

**Architecture:** Selectively import subsystem-owned files from the pinned source commits, then hand-merge only the shared integration points. Keep `KnowledgeDocumentRecord` as the single `knowledge.documents` mapper, add `KnowledgeChunk`, and preserve all current Valuation, Review, Auth, AI Assistant, storage, and Swagger behavior.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL, Alembic, MinIO, Pydantic 2, pytest, Docker Compose, PowerShell.

## Global Constraints

- Execute in `C:\Users\User\project\LandValuationAssistant-worktrees\feature-integrate-valuation-review` from target commit `fa2304f` or its direct descendant.
- Import Case History only from `feature/case-history` commit `e6b00e009d7d70f1f8731c3ce4b5d26257191c04`.
- Import Knowledge AI only from `origin/feature/knowledgeai` commit `01d0443c0713127aab6986f86fe8c6f6373650ef`.
- Do not merge either source branch wholesale and do not import any source migration.
- Preserve the integration branch's existing Valuation, Review, Auth, AI Assistant, Swagger, storage, and Alembic behavior.
- Preserve untracked `.serena/` and `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md`; never stage them.
- `KnowledgeDocumentRecord` remains the only mapper for `knowledge.documents`; compatibility is provided through `KnowledgeDocument = KnowledgeDocumentRecord`.
- MinIO persistence stores bucket plus object key only; no localhost URL or persistent presigned URL may be stored.
- Development seeds remain explicit commands and never run at application startup.
- `rtk` was unavailable during planning; use the raw commands below unless it is installed before execution.

---

## File map

**Case History-owned additions**

- `app/history/**`: read-only repository, service, schemas, permissions, router, development seed, test UI, tests, fixtures, and README.

**Knowledge AI-owned additions**

- `app/knowledge/ai_contract.py`: provider-neutral evidence contract.
- `app/knowledge/bedrock_provider.py`: Bedrock adapter.
- `app/knowledge/codex_provider.py`: local Codex CLI adapter.
- `app/knowledge/case_repository.py`: read-only case and review context queries.
- `app/knowledge/context_service.py`: case and review permission boundary.
- `app/knowledge/policy.py`: review visibility policy.
- `app/knowledge/provider_factory.py`: provider selection.
- `app/knowledge/repository.py`: document and chunk retrieval.
- `app/knowledge/router.py`: authenticated Knowledge endpoints.
- `app/knowledge/runtime_extraction.py`: request-scoped MinIO text extraction.
- `app/knowledge/schemas.py`: API and provider contracts.
- `app/knowledge/service.py`: ranking, evidence validation, and safe responses.
- `scripts/run_local_api.py`: Windows local API support.
- `app/KNOWLEDGE_AI_README.md`: subsystem operation guide.
- `tests/test_codex_provider.py`, `tests/test_knowledge_context_service.py`, `tests/test_knowledge_policy.py`, `tests/test_knowledge_router.py`, `tests/test_knowledge_safety.py`, `tests/test_runtime_extraction.py`: imported subsystem tests.

**Hand-merged integration files**

- `app/api/router.py`: add History and Knowledge routers without removing existing routers.
- `app/core/config.py`: add Knowledge-specific settings without duplicating shared Bedrock settings.
- `app/knowledge/models.py`: preserve the target document mapper and add chunk compatibility.
- `app/storage/service.py`: add restricted Knowledge object listing while preserving upload, download, delete, existence, and presigned-download methods.
- `.env.example`: append Knowledge settings while preserving all existing variables.
- `tests/test_integration_surface.py`: prove old and new routes coexist.
- `tests/test_storage.py`: prove restricted object-listing policy.

`app/main.py`, `requirements.txt`, and all `migrations/versions/**` files are expected to remain unchanged. The target already contains compatible `boto3` and `pypdf` requirements.

---

### Task 1: Integrate the Case History boundary

**Files:**

- Create: `app/history/**` from source commit `e6b00e0`
- Modify: `app/api/router.py`
- Modify: `tests/test_integration_surface.py`
- Test: `app/history/tests/test_demo_contract.py`
- Test: `app/history/tests/test_permissions.py`
- Test: `app/history/tests/test_service.py`
- Test: `app/history/tests/test_test_ui.py`

**Interfaces:**

- Consumes: existing `CurrentUser`, `DbSession`, `Storage`, Valuation/Review tables, and `StorageService.download(object_key)`.
- Produces: `router: APIRouter` with `/history/test-ui`, `/history/cases`, `/history/cases/{case_id}`, and `/history/documents/{document_id}/download`.

- [ ] **Step 1: Import only the History tests and deterministic fixtures**

```powershell
git restore --source=e6b00e009d7d70f1f8731c3ce4b5d26257191c04 -- app/history/tests app/history/test_data
```

- [ ] **Step 2: Run a test to verify the production package is still missing**

```powershell
.\.venv\Scripts\python.exe -m pytest -q app/history/tests/test_permissions.py
```

Expected: collection fails because `app.history.permissions` is not present.

- [ ] **Step 3: Import the complete subsystem-owned directory**

```powershell
git restore --source=e6b00e009d7d70f1f8731c3ce4b5d26257191c04 -- app/history
```

Do not restore any other path from this source commit.

- [ ] **Step 4: Extend the route coexistence test before mounting the router**

Add this assertion to `test_valuation_and_review_routes_coexist()` in `tests/test_integration_surface.py`:

```python
assert "/api/v1/history/cases" in paths
```

- [ ] **Step 5: Run the route test and verify it fails**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_integration_surface.py::test_valuation_and_review_routes_coexist
```

Expected: FAIL because `/api/v1/history/cases` is absent.

- [ ] **Step 6: Mount History without altering existing route registrations**

Add the import beside the other router imports in `app/api/router.py`:

```python
from app.history.router import router as history_router
```

Add this registration after Auth and before the existing feature routers:

```python
api_router.include_router(history_router)
```

Do not add another `/history` prefix because the source router already owns it.

- [ ] **Step 7: Run the History and surface tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q app/history/tests tests/test_integration_surface.py
```

Expected: all selected tests PASS; the source baseline previously contained 14 History test cases after parametrization.

- [ ] **Step 8: Commit only the History integration**

```powershell
git add app/history app/api/router.py tests/test_integration_surface.py
git commit -m "feat: integrate case history subsystem"
```

---

### Task 2: Integrate Knowledge AI with one document mapper

**Files:**

- Create: `app/knowledge/ai_contract.py`
- Create: `app/knowledge/bedrock_provider.py`
- Create: `app/knowledge/case_repository.py`
- Create: `app/knowledge/codex_provider.py`
- Create: `app/knowledge/context_service.py`
- Create: `app/knowledge/policy.py`
- Create: `app/knowledge/provider_factory.py`
- Create: `app/knowledge/repository.py`
- Create: `app/knowledge/router.py`
- Create: `app/knowledge/runtime_extraction.py`
- Create: `app/knowledge/schemas.py`
- Create: `app/knowledge/service.py`
- Preserve: `app/knowledge/__init__.py`
- Preserve: `app/knowledge/source_policy.py`
- Modify: `app/knowledge/models.py`
- Modify: `app/core/config.py`
- Create: `tests/test_codex_provider.py`
- Create: `tests/test_knowledge_context_service.py`
- Create: `tests/test_knowledge_policy.py`
- Create: `tests/test_knowledge_safety.py`
- Create: `tests/test_runtime_extraction.py`

**Interfaces:**

- Consumes: target `KnowledgeDocumentRecord`, existing case/review schema, `Settings`, and `StorageService`.
- Produces: `KnowledgeDocument` compatibility alias, `KnowledgeChunk` mapper, safe retrieval services, provider adapters, and `router: APIRouter`.

- [ ] **Step 1: Import Knowledge tests first**

```powershell
git restore --source=01d0443c0713127aab6986f86fe8c6f6373650ef -- tests/test_codex_provider.py tests/test_knowledge_context_service.py tests/test_knowledge_policy.py tests/test_knowledge_safety.py tests/test_runtime_extraction.py
```

- [ ] **Step 2: Verify a pure Knowledge test fails before implementation is imported**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_knowledge_safety.py
```

Expected: collection fails because the Knowledge service and schemas are absent.

- [ ] **Step 3: Import only Knowledge-owned application files that do not exist in the target**

```powershell
git restore --source=01d0443c0713127aab6986f86fe8c6f6373650ef -- app/knowledge/ai_contract.py app/knowledge/bedrock_provider.py app/knowledge/case_repository.py app/knowledge/codex_provider.py app/knowledge/context_service.py app/knowledge/policy.py app/knowledge/provider_factory.py app/knowledge/repository.py app/knowledge/router.py app/knowledge/runtime_extraction.py app/knowledge/schemas.py app/knowledge/service.py
```

Do not restore `app/knowledge/__init__.py`, `app/knowledge/models.py`, or
`app/knowledge/source_policy.py`; all three target files remain authoritative.

- [ ] **Step 4: Add a failing mapper compatibility test**

Create `tests/test_knowledge_model_compatibility.py`:

```python
from app.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentRecord


def test_knowledge_document_uses_the_integration_mapper() -> None:
    assert KnowledgeDocument is KnowledgeDocumentRecord
    assert KnowledgeDocumentRecord.__table__.fullname == "knowledge.documents"
    assert KnowledgeChunk.__table__.fullname == "knowledge.chunks"
```

- [ ] **Step 5: Run the mapper test and verify it fails**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_knowledge_model_compatibility.py
```

Expected: collection fails because `KnowledgeChunk` and `KnowledgeDocument` do not yet exist.

- [ ] **Step 6: Extend the target model without redefining `knowledge.documents`**

In `app/knowledge/models.py`, extend the SQLAlchemy imports:

```python
from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, func
```

Append this class and alias after `KnowledgeDocumentRecord`:

```python
class KnowledgeChunk(Base):
    __tablename__ = "chunks"
    __table_args__ = {"schema": "knowledge"}

    chunk_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("knowledge.documents.document_id")
    )
    chunk_no: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(300))
    article_no: Mapped[str | None] = mapped_column(String(100))
    token_count: Mapped[int | None] = mapped_column(Integer)
    content_checksum_sha256: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


KnowledgeDocument = KnowledgeDocumentRecord
```

Do not rename the target's `KnowledgeDocumentRecord.metadata_` attribute; imported Knowledge code does not consume the document metadata attribute directly.

- [ ] **Step 7: Add the provider settings needed by the Knowledge core**

Add these fields after the existing MinIO settings in `app/core/config.py`:

```python
knowledge_answer_provider: str = "codex_cli"
knowledge_ai_max_source_characters: int = Field(default=60000, ge=2000, le=200000)
codex_cli_command: str = "codex"
codex_cli_model: str | None = None
codex_cli_timeout_seconds: int = Field(default=180, ge=10, le=900)
bedrock_timeout_seconds: int = Field(default=60, ge=10, le=900)
bedrock_max_tokens: int = Field(default=1200, ge=100, le=8000)
bedrock_temperature: float = Field(default=0, ge=0, le=1)
```

Keep the existing `bedrock_region` and `bedrock_model_id` fields exactly once;
do not remove OCR, Textract, Gemini, maps, or Valuation AI settings and
validators.

- [ ] **Step 8: Run the mapper and pure Knowledge tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_knowledge_model_compatibility.py tests/test_codex_provider.py tests/test_knowledge_policy.py tests/test_knowledge_safety.py tests/test_runtime_extraction.py
```

Expected: all selected tests PASS.

- [ ] **Step 9: Run the existing Valuation rule-source tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_rule_pack_sources.py tests/test_rule_ai_extraction.py
```

Expected: PASS, proving the original `KnowledgeDocumentRecord` write/read flow still works.

- [ ] **Step 10: Commit the Knowledge core and compatibility model**

```powershell
git add app/core/config.py app/knowledge tests/test_codex_provider.py tests/test_knowledge_context_service.py tests/test_knowledge_model_compatibility.py tests/test_knowledge_policy.py tests/test_knowledge_safety.py tests/test_runtime_extraction.py
git commit -m "feat: integrate knowledge AI core"
```

---

### Task 3: Hand-merge Knowledge runtime integration points

**Files:**

- Modify: `app/api/router.py`
- Modify: `app/storage/service.py`
- Modify: `.env.example`
- Create: `scripts/run_local_api.py`
- Create: `app/KNOWLEDGE_AI_README.md`
- Create: `tests/test_knowledge_router.py`
- Modify: `tests/test_integration_surface.py`
- Modify: `tests/test_storage.py`

**Interfaces:**

- Consumes: Knowledge `router`, target `Settings`, target `StorageService`, and existing custom Swagger application setup.
- Produces: `/api/v1/knowledge/*`, `Settings.knowledge_answer_provider`, `StorageService.list_objects("knowledge/")`, and a Windows-compatible local API entry point.

- [ ] **Step 1: Import runtime integration tests**

```powershell
git restore --source=01d0443c0713127aab6986f86fe8c6f6373650ef -- tests/test_knowledge_router.py
```

- [ ] **Step 2: Extend integration tests before shared-file changes**

Add these assertions to `test_valuation_and_review_routes_coexist()` in `tests/test_integration_surface.py`:

```python
assert "/api/v1/knowledge/search" in paths
assert "/api/v1/knowledge/ask" in paths
assert "/api/v1/knowledge/provider-status" in paths
assert "/api/v1/knowledge/cases/{case_id}/context" in paths
```

Extend the existing import in `tests/test_storage.py`:

```python
from app.storage.service import StorageService, validate_object_key
```

Then append this test:

```python
@pytest.mark.asyncio
async def test_object_listing_is_restricted_to_knowledge_prefix() -> None:
    service = object.__new__(StorageService)
    with pytest.raises(ValueError, match="knowledge/"):
        await service.list_objects("cases/")
```

- [ ] **Step 3: Run the new tests and verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_integration_surface.py tests/test_storage.py
```

Expected: FAIL because Knowledge routes and `StorageService.list_objects` are absent.

- [ ] **Step 4: Add restricted MinIO inventory support**

Insert this method in `StorageService` without modifying `delete`, `object_exists`, or `presigned_download_url`:

```python
async def list_objects(self, prefix: str) -> list:
    if prefix != "knowledge/":
        raise ValueError("only the knowledge/ prefix may be listed")
    try:
        return await run_in_threadpool(
            lambda: list(
                self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
            )
        )
    except S3Error as exc:
        raise StorageError("無法列出 MinIO 知識文件") from exc
```

- [ ] **Step 5: Mount the Knowledge router while preserving all existing routers**

Add this import to `app/api/router.py`:

```python
from app.knowledge.router import router as knowledge_router
```

Add this registration without changing any existing registration:

```python
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
```

- [ ] **Step 6: Append Knowledge environment examples**

Append this block after the MinIO settings in `.env.example`; do not remove or replace existing entries:

```dotenv
# Knowledge AI development provider. Use evidence_only when Codex CLI is unavailable.
KNOWLEDGE_ANSWER_PROVIDER=codex_cli
KNOWLEDGE_AI_MAX_SOURCE_CHARACTERS=60000
CODEX_CLI_COMMAND=codex
# CODEX_CLI_MODEL=
CODEX_CLI_TIMEOUT_SECONDS=180
BEDROCK_TIMEOUT_SECONDS=60
BEDROCK_MAX_TOKENS=1200
BEDROCK_TEMPERATURE=0
```

- [ ] **Step 7: Import only the approved local-runtime files and guide**

```powershell
git restore --source=01d0443c0713127aab6986f86fe8c6f6373650ef -- scripts/run_local_api.py app/KNOWLEDGE_AI_README.md
```

Do not restore `app/main.py`, `app/README.md`, `.env.example`, `requirements.txt`, or `app/storage/service.py` from the source branch.

- [ ] **Step 8: Run shared integration tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_knowledge_context_service.py tests/test_knowledge_router.py tests/test_integration_surface.py tests/test_storage.py
```

Expected: all selected tests PASS and OpenAPI still contains Valuation, Review, AI Assistant, History, and Knowledge routes.

- [ ] **Step 9: Confirm dependencies need no source overwrite**

```powershell
Select-String -LiteralPath requirements.txt -Pattern '^boto3>=1.35,<2.0$|^pypdf>=5.0,<7.0$|^reportlab>=4.2,<5.0$|^openpyxl>=3.1,<4.0$|^python-docx>=1.1,<2.0$'
```

Expected: all five target requirements are present. Leave `requirements.txt` unchanged.

- [ ] **Step 10: Commit the hand-merged runtime integration**

```powershell
git add .env.example app/KNOWLEDGE_AI_README.md app/api/router.py app/storage/service.py scripts/run_local_api.py tests/test_integration_surface.py tests/test_knowledge_router.py tests/test_storage.py
git commit -m "feat: expose history and knowledge integration routes"
```

---

### Task 4: Validate migrations, regressions, and development demos

**Files:**

- Verify only: `migrations/versions/**`
- Verify only: full application and test tree
- Do not create or modify production files unless a failing test identifies a scoped integration defect.

**Interfaces:**

- Consumes: the completed History and Knowledge integration.
- Produces: current command evidence for migration integrity, focused behavior, full regression status, and manually exercised demo boundaries.

- [ ] **Step 1: Prove source migrations were not imported**

```powershell
git diff --name-only fa2304f..HEAD -- migrations
```

Expected: no output.

- [ ] **Step 2: Validate the target Alembic head from the current source tree**

```powershell
docker compose --env-file .env.example run --rm --no-deps -v "$((Get-Location).Path):/app" migrate alembic heads
```

Expected: exactly `20260904_0014 (head)` and no duplicate revision error.

- [ ] **Step 3: Run the complete focused subsystem suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q app/history/tests tests/test_codex_provider.py tests/test_knowledge_context_service.py tests/test_knowledge_model_compatibility.py tests/test_knowledge_policy.py tests/test_knowledge_router.py tests/test_knowledge_safety.py tests/test_runtime_extraction.py tests/test_integration_surface.py tests/test_rule_pack_sources.py tests/test_storage.py
```

Expected: all selected tests PASS.

- [ ] **Step 4: Run isolated PostgreSQL/MinIO integration regressions**

```powershell
pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_valuation_review_handoff.py tests/integration/test_migration_0014_review_case_unique.py tests/test_integration_storage.py"
```

Expected: exit code 0; the script removes its temporary Compose project and volumes.

- [ ] **Step 5: Run the full automated suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: exit code 0. If it fails, record the exact failing selectors and compare them against `fa2304f` before changing code; do not label a pre-existing failure as an integration regression.

- [ ] **Step 6: Seed and inspect the History development boundary**

```powershell
docker compose --env-file .env.example up -d db minio minio-init
docker compose --env-file .env.example run --rm migrate
docker compose --env-file .env.example run --rm -v "$((Get-Location).Path):/app" api python -m app.history.demo seed
docker compose --env-file .env.example run --rm -v "$((Get-Location).Path):/app" api python -m app.history.demo status
```

Expected: the two documented development users and three deterministic History cases report ready; the deliberately missing object remains reported as missing.

- [ ] **Step 7: Start the local API in safe Knowledge mode**

In a dedicated PowerShell terminal:

```powershell
$env:KNOWLEDGE_ANSWER_PROVIDER='evidence_only'
.\.venv\Scripts\python.exe scripts/run_local_api.py
```

Expected: startup completes and Swagger is available at `http://127.0.0.1:8002/docs` without replacing the target's custom Swagger configuration.

- [ ] **Step 8: Perform the two manual smoke checks**

In a browser:

1. Open `http://127.0.0.1:8002/api/v1/history/test-ui`, log in as `history_appraiser`, and confirm search/detail display only Valuation data.
2. Log in as `history_reviewer` and confirm Review data, the downloadable `HIST-BOTH-001` report, and the explicit missing-object response for `HIST-REV-001`.
3. Open `http://127.0.0.1:8002/docs`, authorize with a seeded user, call `GET /api/v1/knowledge/provider-status`, then call `POST /api/v1/knowledge/search` with `{"question":"比較法的因素修正率依據是什麼？","limit":5}`.

Expected: History enforces role visibility; Knowledge requires authentication and returns only available source candidates or an explicit no-source/unreadable result. Do not claim `/ask` model execution was verified while using `evidence_only`.

- [ ] **Step 9: Review the final diff and worktree protection**

```powershell
git status --short
git diff --check
git diff --stat fa2304f..HEAD
```

Expected: `.serena/` and `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md` remain untracked; no migration is changed; no unexpected Valuation or Review file is changed; `git diff --check` has no output.

- [ ] **Step 10: Stop on any unresolved regression**

If any focused, integration, full-suite, or manual check fails, do not create a broad cleanup commit. Record the exact command and failure, diagnose it as a separate scoped change, and rerun the failed selector plus Steps 3, 4, and 5 before claiming completion.
