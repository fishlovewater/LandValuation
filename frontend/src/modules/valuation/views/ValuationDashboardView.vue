<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import CaseTable from '../../../components/common/CaseTable.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { useAuthStore } from '../../../stores/auth.store'
import { statusLabel } from '../../../utils/enumLabels'
import { formatDateZhTw } from '../../../utils/formatters'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import { mapCaseResponse } from '../valuation.mappers'
import { resetValuationFlow } from '../valuation.types'
import type { ValuationCaseModel } from '../valuation.types'
import ValuationStepNavigator from '../components/ValuationStepNavigator.vue'

const router = useRouter()
const auth = useAuthStore()
const cases = ref<ValuationCaseModel[]>([])
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
const casesWithDeadlineCount = computed(() => cases.value.filter((item) => Boolean(item.valuationDueDate)).length)
const priorityCase = computed(() => {
  if (!cases.value.length) return null
  return [...cases.value].sort((left, right) => {
    const leftDue = left.valuationDueDate ?? '9999-12-31'
    const rightDue = right.valuationDueDate ?? '9999-12-31'
    if (leftDue !== rightDue) return leftDue.localeCompare(rightDue)
    return right.updatedAt.localeCompare(left.updatedAt)
  })[0] ?? null
})
const landUseOptions = [
  { value: 'RESIDENTIAL', label: '????' },
  { value: 'COMMERCIAL', label: '????' },
  { value: 'INDUSTRIAL', label: '????' },
  { value: 'AGRICULTURAL', label: '????' },
  { value: 'OTHER', label: '????' },
] as const
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
    const { case: created } = await valuationApi.bootstrapCase({
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

    <section class="dashboard-workflow" data-testid="valuation-dashboard-workflow" aria-labelledby="valuation-dashboard-workflow-title">
      <div class="dashboard-workflow__heading">
        <div>
          <p class="valuation-eyebrow">作業流程</p>
          <h2 id="valuation-dashboard-workflow-title">一個案件會依序完成這 5 個階段</h2>
        </div>
        <small>進入案件後，系統會保留目前進度，不需要一次把所有資料填完。</small>
      </div>
      <ol>
        <li><b>1</b><div><strong>建立案件</strong><span>建立案件基本資料，系統會準備後續估價工作環境。</span></div></li>
        <li><b>2</b><div><strong>文件與 AI 辨識</strong><span>上傳來源文件，辨識後由人員確認候選值。</span></div></li>
        <li><b>3</b><div><strong>資料確認</strong><span>確認宗地、比準地與查估必要欄位。</span></div></li>
        <li><b>4</b><div><strong>計算與檢核</strong><span>資料齊全後執行正式計算與規則檢核。</span></div></li>
        <li><b>5</b><div><strong>正式文件與送審</strong><span>確認完整查估書、產生完整送審 PDF，再送交審查。</span></div></li>
      </ol>
    </section>

    <p v-if="notice" class="dashboard-notice" role="status">{{ notice }}</p>
    <p v-if="error && cases.length" class="dashboard-error" role="alert">{{ error }}</p>

    <section
      v-if="cases.length"
      class="dashboard-overview"
      data-testid="valuation-dashboard-overview"
      aria-label="估價案件工作摘要"
    >
      <article>
        <span>目前案件</span>
        <strong>{{ cases.length }} 件</strong>
        <small>可從下方案件清單接續處理。</small>
      </article>
      <article>
        <span>已設定作業期限</span>
        <strong>{{ casesWithDeadlineCount }} 件</strong>
        <small>案件清單預設依作業期限由近到遠排列。</small>
      </article>
      <article v-if="priorityCase" class="dashboard-overview__priority">
        <div>
          <span>建議先處理</span>
          <strong>{{ priorityCase.caseNo }}｜{{ priorityCase.name }}</strong>
          <small>
            {{ statusLabel(priorityCase.status) }} ·
            {{ priorityCase.valuationDueDate ? `作業期限 ${formatDateZhTw(priorityCase.valuationDueDate)}` : '尚未設定作業期限' }}
          </small>
        </div>
        <button
          class="case-action-button"
          type="button"
          data-testid="priority-case-open"
          @click="openCase(priorityCase.caseId)"
        >
          繼續此案件
        </button>
      </article>
    </section>

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
            <span>???? *</span>
            <select v-model="createDraft.landUseType" required data-testid="case-land-use-type">
              <option disabled value="">???????</option>
              <option v-for="option in landUseOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <small>??????????????????????</small>
          </label>
        </div>

        <div class="create-case-actions">
          <button class="solid-button" type="button" :disabled="creating" @click="createOpen = false">取消</button>
          <button class="solid-button solid-button--primary" type="submit" :disabled="creating">
            {{ creating ? '建立中…' : '建立案件' }}
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

.dashboard-workflow { display: grid; gap: 13px; padding: 18px 20px; border: 1px solid #dce5ef; border-radius: var(--app-radius-md); background: #f8fbfe; }
.dashboard-workflow__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.dashboard-workflow__heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 20px; }
.dashboard-workflow__heading > small { max-width: 420px; color: var(--app-muted); font-size: 10px; line-height: 1.6; text-align: right; }
.dashboard-workflow ol { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin: 0; padding: 0; list-style: none; }
.dashboard-workflow li { display: grid; grid-template-columns: auto minmax(0, 1fr); align-content: start; gap: 8px; min-width: 0; padding: 11px; border: 1px solid #dfe6ee; border-radius: 10px; background: #fff; }
.dashboard-workflow li b { display: grid; width: 24px; height: 24px; place-items: center; border-radius: 999px; color: #fff; background: #2e5984; font-size: 10px; }
.dashboard-workflow li div { display: grid; gap: 3px; min-width: 0; }
.dashboard-workflow li strong { color: var(--app-ink); font-size: 11px; }
.dashboard-workflow li span { color: var(--app-muted); font-size: 9px; line-height: 1.5; }

.dashboard-overview {
  display: grid;
  grid-template-columns: minmax(150px, .7fr) minmax(180px, .8fr) minmax(320px, 1.5fr);
  gap: 10px;
}
.dashboard-overview article {
  display: grid;
  align-content: center;
  gap: 4px;
  min-width: 0;
  padding: 15px 16px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: #f9fbfd;
}
.dashboard-overview article > span,
.dashboard-overview article small { color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.dashboard-overview article > span { font-weight: 900; letter-spacing: .08em; }
.dashboard-overview article > strong { color: var(--app-ink); font-size: 18px; line-height: 1.35; }
.dashboard-overview__priority { grid-template-columns: minmax(0, 1fr) auto; align-items: center; border-color: rgba(46, 89, 132, .2) !important; background: #f5f9fd !important; }
.dashboard-overview__priority > div { display: grid; gap: 4px; min-width: 0; }
.dashboard-overview__priority strong { overflow-wrap: anywhere; color: var(--app-ink); font-size: 13px; }
.dashboard-overview__priority .case-action-button { align-self: center; }

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

  .dashboard-overview { grid-template-columns: 1fr; }
  .dashboard-overview__priority { grid-template-columns: 1fr; }
  .dashboard-overview__priority .case-action-button { width: 100%; margin-top: 6px; }
  .dashboard-workflow__heading { flex-direction: column; }
  .dashboard-workflow__heading > small { text-align: left; }
  .dashboard-workflow ol { grid-template-columns: 1fr; }

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
