# Guided Three-Document Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the free-form source upload area with a persisted, sequential three-document intake that supports whole-document confirmation, individual handling of `NEEDS_CONFIRMATION` fields, and explicit skipping.

**Architecture:** Keep the existing upload, extraction, candidate confirmation, F01/F03, calculation, and report services. Add three explicit document categories and a small JSONB progress value on `valuation.cases`; the existing case workspace endpoint updates one guided step at a time. A focused frontend catalog resolves the fixed order and a new stepper component drives the existing upload, preview, extraction, and candidate-review actions.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2 async, Alembic, PostgreSQL JSONB, Vue 3 Composition API, TypeScript, Vitest, pytest.

## Global Constraints

- Input order is exactly: 宗地區段地價勘查表, 比準地價勘查表, 比較法查估表.
- F01「買賣實例調查估價表」and F03「比準地地價估計表」must not appear as Input requirements.
- Do not delete or weaken existing F01/F03 models, APIs, calculations, migrations, or report output.
- One file is uploaded and reviewed at a time; a completed or skipped step unlocks the next step.
- Only fields already marked `NEEDS_CONFIRMATION`, missing evidence, or conflicting by the backend require individual decisions. Do not create a second confidence algorithm in Vue.
- Skipping is persisted, does not invent values, and leaves a visible missing-data warning.
- Preserve existing API contracts and RBAC permissions; reuse `PATCH /valuation/cases/{case_id}/workspace`.
- Preserve unrelated dirty-worktree changes; stage only files named by the current task.
- `rtk` is unavailable on the current Windows host. The verification commands below therefore use direct commands after the observed `CommandNotFoundException`.

---

## File Structure

- Create `migrations/versions/20260913_0028_guided_input_progress.py`: add and remove the JSONB progress column.
- Modify `app/valuation/models.py`: map `CaseRecord.guided_input_progress`.
- Modify `app/valuation/documents/schemas.py`: add the three explicit upload categories.
- Modify `app/valuation/schemas.py`: define guided input codes/status/update and expose persisted progress.
- Modify `app/valuation/repository.py`: load the active document used to confirm a step and count unresolved fields.
- Modify `app/valuation/service.py`: validate sequential transitions and persist `CONFIRMED`/`SKIPPED`.
- Modify `frontend/src/modules/valuation/valuation.types.ts`: mirror new categories and progress DTOs.
- Modify `frontend/src/modules/valuation/valuation.api.ts`: send guided step updates through the existing workspace API.
- Modify `frontend/src/modules/valuation/valuation.mappers.ts`: preserve the progress field in the view model.
- Create `frontend/src/modules/valuation/guidedInputs.ts`: own the fixed catalog and pure status/current-step resolution.
- Create `frontend/src/modules/valuation/components/GuidedInputStepper.vue`: render the three steps and current document guidance.
- Modify `frontend/src/modules/valuation/components/ValuationDocumentWorkspace.vue`: replace the free category selector with the guided current-step controls.
- Modify `frontend/src/modules/valuation/components/ValuationDocumentStage.vue`: pass guided props/events through its wrapper boundary.
- Modify `frontend/src/modules/valuation/views/ValuationPrepareView.vue`: load progress, set the category, confirm/skip a step, and gate forward navigation.
- Modify `tests/test_valuation_schemas.py`, `tests/test_valuation_service.py`, `tests/test_valuation_routes.py`: backend contract and state tests.
- Create `frontend/tests/unit/guidedInputs.spec.ts`: pure catalog/status tests.
- Modify `frontend/tests/unit/workflowSupportComponents.spec.ts`: component behavior tests.
- Modify `frontend/tests/integration/valuationFlow.spec.ts`: complete sequential workflow and reload tests.

---

### Task 1: Persisted Guided Input Contract

**Files:**
- Create: `migrations/versions/20260913_0028_guided_input_progress.py`
- Modify: `app/valuation/models.py:51-82`
- Modify: `app/valuation/documents/schemas.py:8-18`
- Modify: `app/valuation/schemas.py:93-100,214-241`
- Modify: `app/valuation/repository.py:20-75`
- Modify: `app/valuation/service.py:132-154`
- Test: `tests/test_valuation_schemas.py`
- Test: `tests/test_valuation_service.py`
- Test: `tests/test_valuation_routes.py`

**Interfaces:**
- Consumes: existing `PATCH /api/v1/valuation/cases/{case_id}/workspace`, `CaseRecord`, `DocumentRecord`, and `ExtractedFieldRecord.field_status`.
- Produces: `GuidedInputCode`, `GuidedInputStatus`, `GuidedInputStepUpdate`, `CaseResponse.guided_input_progress`, and three `DocumentCategory` values.

- [ ] **Step 1: Write failing schema and service tests**

Add schema assertions in `tests/test_valuation_schemas.py`:

```python
from uuid import uuid4

from app.valuation.documents.schemas import DocumentCategory
from app.valuation.schemas import (
    CaseWorkspaceUpdate,
    GuidedInputCode,
    GuidedInputStatus,
    GuidedInputStepUpdate,
)


def test_guided_input_contract_has_exact_three_source_types() -> None:
    assert [item.value for item in GuidedInputCode] == [
        "parcel-section-survey",
        "benchmark-price-survey",
        "comparison-method-survey",
    ]
    assert DocumentCategory.PARCEL_SECTION_SURVEY.value == "parcel-section-survey"
    assert DocumentCategory.BENCHMARK_PRICE_SURVEY.value == "benchmark-price-survey"
    assert DocumentCategory.COMPARISON_METHOD_SURVEY.value == "comparison-method-survey"


def test_confirmed_guided_input_requires_document() -> None:
    with pytest.raises(ValidationError, match="確認文件時必須提供 document_id"):
        GuidedInputStepUpdate(
            input_code=GuidedInputCode.PARCEL_SECTION_SURVEY,
            status=GuidedInputStatus.CONFIRMED,
        )


def test_skipped_guided_input_rejects_document() -> None:
    with pytest.raises(ValidationError, match="跳過文件時不可提供 document_id"):
        GuidedInputStepUpdate(
            input_code=GuidedInputCode.PARCEL_SECTION_SURVEY,
            status=GuidedInputStatus.SKIPPED,
            document_id=uuid4(),
        )
```

Extend the existing fake repository in `tests/test_valuation_service.py` with `case_document` and `pending_field_count`, then add:

```python
@pytest.mark.asyncio
async def test_guided_inputs_must_be_handled_in_order() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    record.basic_info_confirmed_at = datetime.now(UTC)
    record.guided_input_progress = {}
    repository = FakeRepository(record)

    with pytest.raises(AppError) as raised:
        await ValuationService(None, repository=repository).update_case_workspace(
            record.case_id,
            CaseWorkspaceUpdate(guided_input_step=GuidedInputStepUpdate(
                input_code=GuidedInputCode.BENCHMARK_PRICE_SURVEY,
                status=GuidedInputStatus.SKIPPED,
            )),
            user,
        )

    assert raised.value.code == "GUIDED_INPUT_OUT_OF_ORDER"


@pytest.mark.asyncio
async def test_guided_input_skip_is_persisted_without_document() -> None:
    user = user_with_role()
    record = case_record(user.user_id, CaseStatus.PROCESSING.value)
    record.basic_info_confirmed_at = datetime.now(UTC)
    record.guided_input_progress = {}
    repository = FakeRepository(record)

    updated = await ValuationService(None, repository=repository).update_case_workspace(
        record.case_id,
        CaseWorkspaceUpdate(guided_input_step=GuidedInputStepUpdate(
            input_code=GuidedInputCode.PARCEL_SECTION_SURVEY,
            status=GuidedInputStatus.SKIPPED,
        )),
        user,
    )

    assert updated.guided_input_progress == {
        "parcel-section-survey": {"status": "SKIPPED", "document_id": None}
    }
```

- [ ] **Step 2: Run the focused tests and verify the new symbols are missing**

Run:

```powershell
python -m pytest tests/test_valuation_schemas.py tests/test_valuation_service.py tests/test_valuation_routes.py -q
```

Expected: FAIL during collection because `GuidedInputCode` and the new category members do not exist.

- [ ] **Step 3: Add the migration and SQLAlchemy field**

Create `migrations/versions/20260913_0028_guided_input_progress.py`:

```python
"""Persist the three-step guided valuation input progress."""
from alembic import op

revision = "20260913_0028"
down_revision = "20260913_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE valuation.cases
            ADD COLUMN IF NOT EXISTS guided_input_progress jsonb NOT NULL DEFAULT '{}'::jsonb;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_valuation_cases_guided_input_progress_object'
            ) THEN
                ALTER TABLE valuation.cases
                    ADD CONSTRAINT ck_valuation_cases_guided_input_progress_object
                    CHECK (jsonb_typeof(guided_input_progress) = 'object');
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE valuation.cases
            DROP CONSTRAINT IF EXISTS ck_valuation_cases_guided_input_progress_object,
            DROP COLUMN IF EXISTS guided_input_progress;
    """)
```

Import `text` from SQLAlchemy and add to `CaseRecord`:

```python
guided_input_progress: Mapped[dict] = mapped_column(
    JSONB, default=dict, server_default=text("'{}'::jsonb")
)
```

- [ ] **Step 4: Add categories and request/response schemas**

Add to `DocumentCategory`:

```python
PARCEL_SECTION_SURVEY = "parcel-section-survey"
BENCHMARK_PRICE_SURVEY = "benchmark-price-survey"
COMPARISON_METHOD_SURVEY = "comparison-method-survey"
```

Add to `app/valuation/schemas.py`:

```python
class GuidedInputCode(StrEnum):
    PARCEL_SECTION_SURVEY = "parcel-section-survey"
    BENCHMARK_PRICE_SURVEY = "benchmark-price-survey"
    COMPARISON_METHOD_SURVEY = "comparison-method-survey"


class GuidedInputStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    SKIPPED = "SKIPPED"


class GuidedInputStepUpdate(RequestModel):
    input_code: GuidedInputCode
    status: GuidedInputStatus
    document_id: UUID | None = None

    @model_validator(mode="after")
    def validate_document(self):
        if self.status == GuidedInputStatus.CONFIRMED and self.document_id is None:
            raise ValueError("確認文件時必須提供 document_id")
        if self.status == GuidedInputStatus.SKIPPED and self.document_id is not None:
            raise ValueError("跳過文件時不可提供 document_id")
        return self
```

Add `guided_input_step: GuidedInputStepUpdate | None = None` to `CaseWorkspaceUpdate`, include it in the existing at-least-one-change validator, and add `guided_input_progress: dict[str, dict[str, str | None]] = Field(default_factory=dict)` to `CaseResponse`.

- [ ] **Step 5: Add repository checks and service transition logic**

Add to `ValuationRepository`:

```python
async def get_active_case_document(
    self, case_id: UUID, document_id: UUID
) -> DocumentRecord | None:
    return await self.session.scalar(select(DocumentRecord).where(
        DocumentRecord.case_id == case_id,
        DocumentRecord.document_id == document_id,
        DocumentRecord.is_active.is_(True),
    ))

async def count_pending_document_fields(self, document_id: UUID) -> int:
    return int(await self.session.scalar(
        select(func.count()).select_from(ExtractedFieldRecord).where(
            ExtractedFieldRecord.document_id == document_id,
            ExtractedFieldRecord.field_status == "NEEDS_CONFIRMATION",
        )
    ) or 0)
```

Import `ExtractedFieldRecord`. In `ValuationService`, define the fixed order and call this helper from `update_case_workspace`:

```python
GUIDED_INPUT_ORDER = tuple(GuidedInputCode)

async def _apply_guided_input_step(
    self, record: CaseRecord, step: GuidedInputStepUpdate
) -> None:
    progress = dict(record.guided_input_progress or {})
    position = GUIDED_INPUT_ORDER.index(step.input_code)
    missing_previous = [
        code.value for code in GUIDED_INPUT_ORDER[:position]
        if code.value not in progress
    ]
    if missing_previous:
        raise AppError("GUIDED_INPUT_OUT_OF_ORDER", "請先完成或跳過前一份文件。", 409)

    if step.status == GuidedInputStatus.CONFIRMED:
        document = await self.repository.get_active_case_document(
            record.case_id, step.document_id
        )
        if document is None or document.document_type != step.input_code.value:
            raise AppError("GUIDED_INPUT_DOCUMENT_MISMATCH", "文件不屬於目前上傳步驟。", 409)
        if await self.repository.count_pending_document_fields(step.document_id):
            raise AppError("GUIDED_INPUT_FIELDS_PENDING", "請先處理低信心或衝突欄位。", 409)

    progress[step.input_code.value] = {
        "status": step.status.value,
        "document_id": str(step.document_id) if step.document_id else None,
    }
    record.guided_input_progress = progress
```

- [ ] **Step 6: Add route contract coverage**

Extend `tests/test_valuation_routes.py` to assert the existing workspace route remains unique and accepts `guided_input_step`; do not introduce a second progress endpoint:

```python
def test_guided_input_reuses_case_workspace_route() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/v1/valuation/cases/{case_id}/workspace" in paths
    assert "/api/v1/valuation/cases/{case_id}/guided-inputs" not in paths
```

- [ ] **Step 7: Run backend tests**

Run:

```powershell
python -m pytest tests/test_valuation_schemas.py tests/test_valuation_service.py tests/test_valuation_routes.py tests/test_document_workflow.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 8: Commit the backend contract**

```powershell
git add migrations/versions/20260913_0028_guided_input_progress.py app/valuation/models.py app/valuation/documents/schemas.py app/valuation/schemas.py app/valuation/repository.py app/valuation/service.py tests/test_valuation_schemas.py tests/test_valuation_service.py tests/test_valuation_routes.py
git commit -m "feat(valuation): persist guided input progress"
```

---

### Task 2: Frontend Guided Input Domain

**Files:**
- Create: `frontend/src/modules/valuation/guidedInputs.ts`
- Modify: `frontend/src/modules/valuation/valuation.types.ts:191-220`
- Modify: `frontend/src/modules/valuation/valuation.api.ts:250-310`
- Modify: `frontend/src/modules/valuation/valuation.mappers.ts`
- Create: `frontend/tests/unit/guidedInputs.spec.ts`
- Modify: `frontend/tests/unit/valuationApi.spec.ts`
- Modify: `frontend/tests/unit/valuationMappers.spec.ts`

**Interfaces:**
- Consumes: backend category strings and `CaseResponse.guided_input_progress` from Task 1.
- Produces: `GUIDED_INPUT_STEPS`, `GuidedInputStep`, `resolveGuidedInputState()`, and typed workspace API payloads for Task 3.

- [ ] **Step 1: Write failing catalog and resolver tests**

Create `frontend/tests/unit/guidedInputs.spec.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { GUIDED_INPUT_STEPS, resolveGuidedInputState } from '../../src/modules/valuation/guidedInputs'

describe('guided valuation inputs', () => {
  it('contains only the three problem-provided documents in order', () => {
    expect(GUIDED_INPUT_STEPS.map(step => step.label)).toEqual([
      '宗地區段地價勘查表',
      '比準地價勘查表',
      '比較法查估表',
    ])
    expect(GUIDED_INPUT_STEPS.map(step => step.code)).not.toContain('F01')
    expect(GUIDED_INPUT_STEPS.map(step => step.code)).not.toContain('F03')
  })

  it('returns the first unhandled step and preserves a skipped warning', () => {
    const state = resolveGuidedInputState({
      'parcel-section-survey': { status: 'SKIPPED', document_id: null },
    })
    expect(state.current.code).toBe('benchmark-price-survey')
    expect(state.steps[0].status).toBe('SKIPPED')
    expect(state.hasSkippedInputs).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test and verify the module is missing**

Run:

```powershell
Set-Location frontend
npm test -- --run tests/unit/guidedInputs.spec.ts
```

Expected: FAIL because `guidedInputs.ts` does not exist.

- [ ] **Step 3: Add frontend types and the fixed catalog**

Define `GuidedInputCode` in `valuation.types.ts`, extend `DocumentCategory` and case DTO/model types with the three category strings and progress field:

```ts
export type GuidedInputCode =
  | 'parcel-section-survey'
  | 'benchmark-price-survey'
  | 'comparison-method-survey'
```

Create `guidedInputs.ts`:

```ts
import type { DocumentCategory, GuidedInputCode, GuidedInputProgress } from './valuation.types'

export interface GuidedInputStep {
  code: GuidedInputCode
  category: DocumentCategory
  label: string
  purpose: string
  basicInfo: string
}

export const GUIDED_INPUT_STEPS: readonly GuidedInputStep[] = [
  { code: 'parcel-section-survey', category: 'parcel-section-survey', label: '宗地區段地價勘查表', purpose: '提供宗地所在區段與地價勘查資料。', basicInfo: '核對案件區段、宗地位置及勘查基本資料。' },
  { code: 'benchmark-price-survey', category: 'benchmark-price-survey', label: '比準地價勘查表', purpose: '提供比準地位置與相關地價資料。', basicInfo: '核對比準地、地價區段及其基本資料。' },
  { code: 'comparison-method-survey', category: 'comparison-method-survey', label: '比較法查估表', purpose: '提供比較標的與價格調整資料。', basicInfo: '核對比較標的、交易資訊及調整資料。' },
] as const

export function resolveGuidedInputState(progress: GuidedInputProgress) {
  const steps = GUIDED_INPUT_STEPS.map(step => ({
    ...step,
    status: progress[step.code]?.status ?? 'PENDING',
  }))
  return {
    steps,
    current: steps.find(step => step.status === 'PENDING') ?? steps.at(-1)!,
    complete: steps.every(step => step.status !== 'PENDING'),
    hasSkippedInputs: steps.some(step => step.status === 'SKIPPED'),
  }
}
```

- [ ] **Step 4: Type the existing workspace API call**

Add these types to `valuation.types.ts`:

```ts
export type GuidedInputStatus = 'CONFIRMED' | 'SKIPPED'
export type GuidedInputProgress = Partial<Record<GuidedInputCode, {
  status: GuidedInputStatus
  document_id: string | null
}>>
```

Extend the existing `updateCaseWorkspace` payload rather than adding another request:

```ts
guided_input_step?: {
  input_code: GuidedInputCode
  status: GuidedInputStatus
  document_id?: string | null
}
```

Map `guided_input_progress` unchanged into the case view model.

- [ ] **Step 5: Run unit tests and type checking**

Run:

```powershell
Set-Location frontend
npm test -- --run tests/unit/guidedInputs.spec.ts tests/unit/valuationApi.spec.ts tests/unit/valuationMappers.spec.ts
npx vue-tsc -b
```

Expected: selected Vitest tests PASS and `vue-tsc` exits 0.

- [ ] **Step 6: Commit the frontend domain layer**

```powershell
git add frontend/src/modules/valuation/guidedInputs.ts frontend/src/modules/valuation/valuation.types.ts frontend/src/modules/valuation/valuation.api.ts frontend/src/modules/valuation/valuation.mappers.ts frontend/tests/unit/guidedInputs.spec.ts frontend/tests/unit/valuationApi.spec.ts frontend/tests/unit/valuationMappers.spec.ts
git commit -m "feat(valuation): define three guided input steps"
```

---

### Task 3: Sequential Upload, Whole-Document Confirmation, and Skip UI

**Files:**
- Create: `frontend/src/modules/valuation/components/GuidedInputStepper.vue`
- Modify: `frontend/src/modules/valuation/components/ValuationDocumentWorkspace.vue:1-430`
- Modify: `frontend/src/modules/valuation/components/ValuationDocumentStage.vue:1-132`
- Modify: `frontend/tests/unit/workflowSupportComponents.spec.ts`

**Interfaces:**
- Consumes: Task 2's catalog/resolver and existing upload, extraction, preview, candidate-review events.
- Produces: `confirm-guided-input` and `skip-guided-input` presentation events; no new extraction behavior and no F01/F03 deletion.

- [ ] **Step 1: Write failing component tests**

Add tests to `workflowSupportComponents.spec.ts` that mount the guided stepper and document workspace:

```ts
it('shows one current guided input with basic information and no category chooser', () => {
  const wrapper = mount(GuidedInputStepper, {
    props: {
      steps: resolveGuidedInputState({}).steps,
      currentCode: 'parcel-section-survey',
      canConfirm: false,
    },
  })
  expect(wrapper.text()).toContain('宗地區段地價勘查表')
  expect(wrapper.text()).toContain('核對案件區段、宗地位置及勘查基本資料')
  expect(wrapper.find('[data-testid="guided-input-parcel-section-survey"]').attributes('aria-current')).toBe('step')
})

it('emits skip for the current document and hides F01/F03 input labels', async () => {
  const wrapper = mount(GuidedInputStepper, {
    props: {
      steps: resolveGuidedInputState({}).steps,
      currentCode: 'parcel-section-survey',
      canConfirm: false,
    },
  })
  await wrapper.get('[data-testid="skip-guided-input"]').trigger('click')
  expect(wrapper.emitted('skip')).toEqual([['parcel-section-survey']])
  expect(wrapper.text()).not.toContain('買賣實例調查估價表')
  expect(wrapper.text()).not.toContain('比準地地價估計表')
})
```

- [ ] **Step 2: Run component tests and verify failure**

Run:

```powershell
Set-Location frontend
npm test -- --run tests/unit/workflowSupportComponents.spec.ts
```

Expected: FAIL because `GuidedInputStepper.vue` and its events are missing.

- [ ] **Step 3: Implement the focused stepper component**

Create `GuidedInputStepper.vue` with a semantic ordered list, status labels, current step guidance, and two actions:

```vue
<script setup lang="ts">
import type { GuidedInputCode } from '../valuation.types'

defineProps<{
  steps: Array<{ code: GuidedInputCode; label: string; purpose: string; basicInfo: string; status: string }>
  currentCode: GuidedInputCode
  canConfirm: boolean
}>()
defineEmits<{
  confirm: [code: GuidedInputCode]
  skip: [code: GuidedInputCode]
}>()
</script>

<template>
  <section class="guided-inputs" aria-labelledby="guided-input-title">
    <h3 id="guided-input-title">依序準備三份題目資料</h3>
    <ol>
      <li v-for="step in steps" :key="step.code" :data-testid="`guided-input-${step.code}`" :aria-current="step.code === currentCode ? 'step' : undefined">
        <strong>{{ step.label }}</strong><span>{{ step.status }}</span>
        <template v-if="step.code === currentCode"><p>{{ step.purpose }}</p><small>{{ step.basicInfo }}</small></template>
      </li>
    </ol>
    <div class="guided-inputs__actions">
      <button type="button" data-testid="skip-guided-input" @click="$emit('skip', currentCode)">暫時跳過</button>
      <button type="button" data-testid="confirm-guided-input" :disabled="!canConfirm" @click="$emit('confirm', currentCode)">本份文件確認完成</button>
    </div>
  </section>
</template>
```

Use existing design tokens and focus styles; do not add a UI dependency.

- [ ] **Step 4: Replace free-form category choice with current-step category**

In `ValuationDocumentWorkspace.vue`:

- Render `GuidedInputStepper` before the upload control.
- Remove the user-facing category `<select>` from the guided path.
- Display only the current step's file or an empty upload target.
- Keep preview, download, retry extraction, and existing evidence display.
- Set `accept` to the existing supported list and retain one-file selection (`files[0]`).
- Emit `updateUploadCategory(currentStep.category)` when current step changes.
- Disable whole-document confirmation while `documentPendingCount(currentDocumentId) > 0` or recognition is not complete.

The upload button copy becomes:

```vue
{{ uploading ? '上傳中…' : `上傳${currentStep.label}` }}
```

- [ ] **Step 5: Run component tests and build**

Run:

```powershell
Set-Location frontend
npm test -- --run tests/unit/workflowSupportComponents.spec.ts tests/unit/guidedInputs.spec.ts
npm run build
```

Expected: selected tests PASS and Vite production build exits 0.

- [ ] **Step 6: Commit the guided presentation layer**

```powershell
git add frontend/src/modules/valuation/components/GuidedInputStepper.vue frontend/src/modules/valuation/components/ValuationDocumentWorkspace.vue frontend/src/modules/valuation/components/ValuationDocumentStage.vue frontend/tests/unit/workflowSupportComponents.spec.ts
git commit -m "feat(valuation): present guided source document steps"
```

---

### Task 4: End-to-End Workflow and Regression Boundary

**Files:**
- Modify: `frontend/src/modules/valuation/views/ValuationPrepareView.vue:78-109,1664-1826,2450-2550`
- Modify: `frontend/tests/integration/valuationFlow.spec.ts`

**Interfaces:**
- Consumes: all Task 1-3 contracts.
- Produces: persistence wiring and browser-level proof that the three-step state persists and does not remove downstream F01/F03 capabilities.

- [ ] **Step 1: Add the failing integration scenario**

Add one scenario to `valuationFlow.spec.ts` using the file's existing authenticated router/mount helpers and Axios adapter. Keep a mutable `guidedProgress` object in the adapter; when it receives `PATCH /workspace`, merge `guided_input_step` into that object and return the case DTO with `guided_input_progress: guidedProgress`. The test body must execute these assertions and actions:

```ts
it('uploads one guided source at a time, skips one, and restores progress', async () => {
  expect(wrapper.get('[data-testid="guided-input-parcel-section-survey"]').attributes('aria-current')).toBe('step')
  expect(wrapper.get('[data-testid="valuation-upload-panel"]').text()).toContain('宗地區段地價勘查表')

  const input = wrapper.get<HTMLInputElement>('#valuation-source-file')
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [new File(['source'], '宗地區段地價勘查表.xlsx')],
  })
  await input.trigger('change')
  await wrapper.get('[data-testid="valuation-upload-panel"]').trigger('submit')
  await vi.waitFor(() => expect(wrapper.get('[data-testid="confirm-guided-input"]').attributes('disabled')).toBeUndefined())
  await wrapper.get('[data-testid="confirm-guided-input"]').trigger('click')

  await vi.waitFor(() => expect(wrapper.get('[data-testid="guided-input-benchmark-price-survey"]').attributes('aria-current')).toBe('step'))
  await wrapper.get('[data-testid="skip-guided-input"]').trigger('click')
  await vi.waitFor(() => expect(wrapper.get('[data-testid="guided-input-comparison-method-survey"]').attributes('aria-current')).toBe('step'))
  expect(wrapper.text()).toContain('缺少的資料不會自動補值')
  expect(wrapper.text()).not.toContain('買賣實例調查估價表')
  expect(wrapper.text()).not.toContain('比準地地價估計表')

  wrapper.unmount()
  const reopened = mount(AppLayout, { global: { plugins: [router] } })
  await flushPromises()
  expect(reopened.get('[data-testid="guided-input-parcel-section-survey"]').text()).toContain('CONFIRMED')
  expect(reopened.get('[data-testid="guided-input-benchmark-price-survey"]').text()).toContain('SKIPPED')
})
```

Use the existing Axios adapter pattern in the same test file; assert exact request bodies:

```ts
expect(workspaceBodies).toContainEqual({
  guided_input_step: {
    input_code: 'benchmark-price-survey',
    status: 'SKIPPED',
    document_id: null,
  },
})
```

- [ ] **Step 2: Run the integration test and verify it fails before persistence wiring**

Run:

```powershell
Set-Location frontend
npm test -- --run tests/integration/valuationFlow.spec.ts
```

Expected: FAIL because `ValuationPrepareView.vue` does not yet persist the stepper's confirm/skip events.

- [ ] **Step 3: Wire progress persistence in `ValuationPrepareView.vue`**

Add computed guided state from `flow.case.guidedInputProgress`. On current-step change, assign its category. Wire the stepper events to these handlers:

```ts
async function skipGuidedInput(code: GuidedInputCode): Promise<void> {
  if (!flow.case) return
  const updated = await valuationApi.updateCaseWorkspace(flow.case.caseId, {
    guided_input_step: { input_code: code, status: 'SKIPPED', document_id: null },
  })
  flow.case = mapCaseResponse(updated)
  notice.value = `${guidedInputLabel(code)}已跳過；缺少的資料不會自動補值。`
}

async function confirmGuidedInput(code: GuidedInputCode, documentId: string): Promise<void> {
  if (!flow.case) return
  const updated = await valuationApi.updateCaseWorkspace(flow.case.caseId, {
    guided_input_step: { input_code: code, status: 'CONFIRMED', document_id: documentId },
  })
  flow.case = mapCaseResponse(updated)
  notice.value = `${guidedInputLabel(code)}已確認。`
}
```

Keep `extractDocument()` unchanged: the approved design removed the proposed per-document form-analysis restriction. Do not remove F01/F03 analysis code. The final forward gate must be:

```ts
const guidedInputsHandled = computed(() => resolveGuidedInputState(
  flow.case?.guidedInputProgress ?? {},
).complete)
```

Skipped inputs count as handled for navigation but continue to render a visible missing-data warning.

- [ ] **Step 4: Run focused backend and frontend regression suites**

Run from repository root:

```powershell
python -m pytest tests/test_valuation_schemas.py tests/test_valuation_service.py tests/test_valuation_routes.py tests/test_document_workflow.py tests/test_auto_workflow.py -q
Set-Location frontend
npm test -- --run tests/unit/guidedInputs.spec.ts tests/unit/valuationApi.spec.ts tests/unit/valuationMappers.spec.ts tests/unit/workflowSupportComponents.spec.ts tests/integration/valuationFlow.spec.ts
npm run build
```

Expected: all selected pytest and Vitest tests PASS; the frontend build exits 0.

- [ ] **Step 5: Verify F01/F03 preservation explicitly**

Run from repository root:

```powershell
Select-String -Path app/valuation/official_forms.py -Pattern '買賣實例調查估價表|比準地地價估計表'
python -m pytest tests/test_valuation_schemas.py::test_f03_requirements_match_backend_guide -q
```

Expected: both labels are still present in `official_forms.py`, and the F03 requirement test PASSes. This proves removal was limited to Input guidance.

- [ ] **Step 6: Commit integration coverage**

```powershell
git add frontend/src/modules/valuation/views/ValuationPrepareView.vue frontend/tests/integration/valuationFlow.spec.ts
git commit -m "test(valuation): cover guided document intake"
```

- [ ] **Step 7: Inspect final scope before claiming completion**

Run:

```powershell
git status --short
git diff HEAD~4 --stat
```

Expected: only planned guided-input files appear in the task commits; pre-existing unrelated working-tree modifications remain unstaged and preserved.
