<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import CaseTable from '../../../components/common/CaseTable.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { useAuthStore } from '../../../stores/auth.store'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import { mapCaseResponse } from '../valuation.mappers'
import { resetValuationFlow } from '../valuation.types'
import type { FormRequirementResponseDto, ValuationCaseModel } from '../valuation.types'
import ValuationStepNavigator from '../components/ValuationStepNavigator.vue'

const router = useRouter()
const auth = useAuthStore()
const cases = ref<ValuationCaseModel[]>([])
const formTypes = ref<FormRequirementResponseDto[]>([])
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const notice = ref('')
const createOpen = ref(false)
const sortBy = ref('valuationDueDate')
const sortDirection = ref<'asc' | 'desc'>('asc')
const canCreate = computed(() => auth.permissions.includes('case.create') && auth.permissions.includes('valuation.update'))
const createDraft = reactive({
  caseNo: '',
  title: '',
  caseType: '',
  requestingAgency: '',
  valuationBaseDate: '',
  valuationDueDate: '',
  cityCode: '',
  districtCode: '',
  landUseType: '',
})
const landUseOptions = [
  { value: 'RESIDENTIAL', label: '住宅用地' },
  { value: 'COMMERCIAL', label: '商業用地' },
  { value: 'INDUSTRIAL', label: '工業用地' },
  { value: 'AGRICULTURAL', label: '農業用地' },
  { value: 'OTHER', label: '其他用途' },
] as const
const selectedRequirement = computed(() => formTypes.value.find((item) => item.form_type === 'F03') ?? null)
const sortedCases = computed(() => {
  const direction = sortDirection.value === 'asc' ? 1 : -1
  const key = sortBy.value
  return [...cases.value].sort((left, right) => {
    const leftValue = key === 'caseNo'
      ? left.caseNo
      : key === 'name'
        ? left.name
        : key === 'status'
          ? left.status
          : key === 'dueAt' || key === 'valuationDueDate'
            ? left.valuationDueDate ?? '9999-12-31'
            : left.updatedAt
    const rightValue = key === 'caseNo'
      ? right.caseNo
      : key === 'name'
        ? right.name
        : key === 'status'
          ? right.status
          : key === 'dueAt' || key === 'valuationDueDate'
            ? right.valuationDueDate ?? '9999-12-31'
            : right.updatedAt
    return leftValue.localeCompare(rightValue, 'zh-Hant') * direction
  })
})

function requirementFieldLabel(field: string): string {
  return ({
    valuation_base_date: '估價基準日',
    benchmark_land_id: '比準地',
  } as Record<string, string>)[field] ?? field
}

function requirementDocumentLabel(document: string): string {
  return ({
    'land-register': '土地登記資料',
    'cadastral-map': '地籍圖',
  } as Record<string, string>)[document] ?? document
}

async function loadCases(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const caseDtos = await valuationApi.listCases({ offset: 0, limit: 50 })
    cases.value = caseDtos.map(mapCaseResponse)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    loading.value = false
  }

  try {
    formTypes.value = await valuationApi.getFormTypes()
  } catch {
    formTypes.value = []
  }
}

function resetCreateDraft(): void {
  Object.assign(createDraft, {
    caseNo: '', title: '', caseType: '', requestingAgency: '', valuationBaseDate: '',
    valuationDueDate: '', cityCode: '', districtCode: '', landUseType: '',
  })
}

function updateSort(value: { sortBy: string; sortDirection: 'asc' | 'desc' }): void {
  sortBy.value = value.sortBy
  sortDirection.value = value.sortDirection
}

async function createCase(): Promise<void> {
  if (!canCreate.value || creating.value) return
  creating.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await valuationApi.createCase({
      case_no: createDraft.caseNo,
      case_title: createDraft.title,
      case_type: createDraft.caseType,
      requesting_agency: createDraft.requestingAgency || null,
      valuation_base_date: createDraft.valuationBaseDate,
      valuation_due_date: createDraft.valuationDueDate || null,
      city_code: createDraft.cityCode,
      district_code: createDraft.districtCode,
      land_use_type: createDraft.landUseType || null,
    })
    await valuationApi.createForm(created.case_id, {
      form_code: 'F03',
      prepared_date: createDraft.valuationBaseDate,
    })
    createOpen.value = false
    resetCreateDraft()
    notice.value = `案件 ${created.case_no} 已建立，可進入案件上傳來源文件與補齊估價資料。`
    await loadCases()
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    creating.value = false
  }
}

async function openCase(caseId: string): Promise<void> {
  resetValuationFlow()
  await router.push({ name: 'valuation-prepare', params: { caseId } })
}

onMounted(() => {
  void loadCases()
})
</script>

<template>
  <div class="valuation-view">
    <ValuationStepNavigator :current-step="1" />
    <PageHeader
      eyebrow="估價作業"
      title="估價作業"
      description="建立或接續估價案件，依表單需求完成文件、欄位、計算、檢核與正式送審。"
    >
      <template #actions>
        <button v-if="canCreate" class="solid-button solid-button--primary" type="button" data-testid="create-case" @click="createOpen = true">
          ＋ 新增案件
        </button>
      </template>
    </PageHeader>

    <p v-if="notice" class="dashboard-notice" role="status">{{ notice }}</p>
    <p v-if="error && cases.length" class="dashboard-error" role="alert">{{ error }}</p>

    <section v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="valuation-case-list-title">
      <div class="valuation-surface__heading">
        <div>
          <p class="valuation-eyebrow">案件與文件</p>
          <h2 id="valuation-case-list-title">最近可處理案件</h2>
        </div>
        <span class="source-marker" data-source-kind="automatic">目前可處理案件</span>
      </div>

      <CaseTable
        :cases="sortedCases"
        :loading="loading"
        :error="error"
        :sort-by="sortBy === 'valuationDueDate' ? 'dueAt' : sortBy"
        :sort-direction="sortDirection"
        :show-deadline="true"
        empty-title="目前沒有可處理案件"
        empty-description="請確認目前帳號具備案件讀取權限，或稍後重新整理。"
        @sort-change="updateSort"
        @retry="loadCases"
      >
        <template #actions="{ row }">
          <button
            class="case-action-button"
            type="button"
            :data-testid="`case-open-${row.caseId}`"
            @click="openCase(row.caseId)"
          >
            繼續估價
          </button>
        </template>
      </CaseTable>
    </section>

    <GlassModal
      :open="createOpen"
      id="valuation-create-case"
      class="valuation-create-modal"
      title="新增估價案件"
      initial-focus="#valuation-case-no"
      @close="createOpen = false"
    >
      <form class="create-case-form" data-testid="create-case-form" @submit.prevent="createCase">
        <div class="create-case-grid">
          <label><span>案件編號 *</span><input id="valuation-case-no" v-model.trim="createDraft.caseNo" required maxlength="50" /></label>
          <label><span>案件名稱 *</span><input v-model.trim="createDraft.title" required maxlength="200" /></label>
          <label><span>案件類型 *</span><input v-model.trim="createDraft.caseType" required maxlength="50" placeholder="例如：徵收補償市價查估" /></label>
          <label><span>估價基準日 *</span><input v-model="createDraft.valuationBaseDate" type="date" required /></label>
          <label><span>估價作業期限</span><input v-model="createDraft.valuationDueDate" type="date" /></label>
          <label><span>申請機關</span><input v-model.trim="createDraft.requestingAgency" maxlength="200" /></label>
          <label><span>縣市代碼 *</span><input v-model.trim="createDraft.cityCode" required maxlength="20" /></label>
          <label><span>行政區代碼 *</span><input v-model.trim="createDraft.districtCode" required maxlength="20" /></label>
          <label class="create-case-grid__wide">
            <span>土地用途 *</span>
            <select v-model="createDraft.landUseType" required data-testid="case-land-use-type">
              <option disabled value="">請選擇土地用途</option>
              <option v-for="option in landUseOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <small>請從清單選擇；系統會儲存對應的正式規則代碼。</small>
          </label>
          <div class="create-case-fixed-form create-case-grid__wide" data-testid="create-case-starting-form">
            <span>起始查估表</span>
            <strong>F03｜比準地地價估計表</strong>
            <small>新增案件會先建立目前估價工作台的 F03 草稿；其他查估書表會依後續比較、區域因素與正式報告流程建立或確認，不需要在這裡先選一張表。</small>
          </div>
        </div>

        <section v-if="selectedRequirement" class="requirement-preview" aria-label="所需資料清單">
          <div>
            <strong>{{ selectedRequirement.form_name }} 所需資料</strong>
            <span>這裡只列出 F03 起始草稿的必要條件，不代表整個徵收市價查估作業只有這一張表。</span>
          </div>
          <ul>
            <li v-for="field in selectedRequirement.required_fields" :key="`field-${field}`">欄位：{{ requirementFieldLabel(field) }}</li>
            <li v-for="document in selectedRequirement.required_documents" :key="`doc-${document}`">文件：{{ requirementDocumentLabel(document) }}</li>
          </ul>
        </section>

        <div class="create-case-actions">
          <button class="solid-button" type="button" :disabled="creating" @click="createOpen = false">取消</button>
          <button class="solid-button solid-button--primary" type="submit" :disabled="creating">
            {{ creating ? '建立中…' : '建立案件與表單' }}
          </button>
        </div>
      </form>
    </GlassModal>
  </div>
</template>

<style scoped>
.valuation-view {
  display: grid;
  gap: 18px;
  padding: 24px 28px 34px;
}

.valuation-surface {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: color-mix(in srgb, var(--app-paper-strong) 82%, transparent);
  box-shadow: var(--app-shadow-soft);
}

.dashboard-notice,
.dashboard-error { margin: 0; padding: 12px 14px; border-radius: var(--app-radius-sm); font-size: 13px; }
.dashboard-notice { color: var(--app-green); background: rgba(59, 129, 102, .09); }
.dashboard-error { color: #a44334; background: rgba(255, 240, 237, .9); }

.create-case-form { display: grid; width: 100%; min-width: 0; gap: 18px; }
:deep(.valuation-create-modal.lg-modal__panel) { width: min(860px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow: auto; }
:deep(.valuation-create-modal .lg-modal__title) { color: var(--app-ink); }
.create-case-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; }
.create-case-grid label { display: grid; gap: 6px; color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.create-case-grid label small { color: var(--app-muted); font-size: 11px; font-weight: 500; line-height: 1.45; }
.create-case-grid__wide { grid-column: 1 / -1; }
.create-case-grid input,
.create-case-grid select { min-height: 44px; padding: 9px 11px; border: 1px solid var(--app-line); border-radius: 10px; color: var(--app-ink); background: rgba(255,255,255,.8); font: inherit; }
.create-case-grid input:focus,
.create-case-grid select:focus { outline: 3px solid rgba(200, 91, 67, .16); border-color: var(--app-accent); }
.create-case-fixed-form { display: grid; gap: 4px; padding: 12px 13px; border: 1px solid rgba(46,89,132,.18); border-radius: 10px; background: #f7fbff; }
.create-case-fixed-form > span { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.create-case-fixed-form strong { color: var(--app-ink); font-size: 13px; }
.create-case-fixed-form small { color: var(--app-ink-soft); font-size: 11px; font-weight: 500; line-height: 1.6; }
.requirement-preview { display: grid; gap: 10px; padding: 14px; border: 1px solid rgba(46, 89, 132, .18); border-radius: 14px; background: rgba(237, 244, 251, .66); }
.requirement-preview div { display: grid; gap: 3px; }
.requirement-preview strong { color: var(--app-ink); }
.requirement-preview span { color: var(--app-muted); font-size: 11px; }
.requirement-preview ul { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.requirement-preview li { padding: 6px 9px; border-radius: 999px; color: var(--app-ink-soft); background: rgba(255,255,255,.76); font-size: 11px; }
.create-case-actions { display: flex; justify-content: flex-end; gap: 8px; }

.valuation-surface__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.valuation-surface__heading {
  margin-bottom: 16px;
}

.valuation-surface h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.04em;
}

.valuation-eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.source-marker {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid rgba(59, 129, 102, 0.24);
  border-radius: var(--app-radius-pill);
  color: var(--app-green);
  background: rgba(59, 129, 102, 0.08);
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.case-action-button { min-height: 36px; padding: 7px 12px; border: 1px solid #2e5984; border-radius: 8px; color: #fff; background: #2e5984; cursor: pointer; font-size: 11px; font-weight: 900; white-space: nowrap; }
.case-action-button:hover { background: #244d73; }

.solid-button {
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}

.solid-button--primary {
  border-color: var(--app-accent);
  color: #fff;
  background: var(--app-accent);
}

.solid-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

@media (max-width: 640px) {
  .valuation-view {
    padding: 18px 16px 28px;
  }

  .valuation-surface {
    padding: 16px;
  }

  .valuation-surface__heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .solid-button {
    width: 100%;
  }
  .create-case-form { min-width: 0; }
  .create-case-grid { grid-template-columns: 1fr; }
  .create-case-grid__wide { grid-column: auto; }
  .create-case-actions { flex-direction: column-reverse; }
}
</style>
