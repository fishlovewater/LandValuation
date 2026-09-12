<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  PhArrowRight as ArrowRight,
  PhCalendarBlank as CalendarBlank,
  PhClockCountdown as ClockCountdown,
  PhFileText as FileText,
  PhMagnifyingGlass as MagnifyingGlass,
  PhPlus as Plus,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { useAuthStore } from '../../../stores/auth.store'
import { statusLabel } from '../../../utils/enumLabels'
import { formatDateZhTw } from '../../../utils/formatters'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import { LAND_USE_OPTIONS, VALUATION_CASE_TYPE, valuationCaseTypeLabel } from '../valuation.labels'
import { mapCaseResponse } from '../valuation.mappers'
import { valuationStageRoute } from '../valuation.navigation'
import { NEW_TAIPEI_CITY_CODE, NEW_TAIPEI_DISTRICTS } from '../newTaipei'
import { resetValuationFlow } from '../valuation.types'
import type { ValuationCaseModel } from '../valuation.types'

const router = useRouter()
const auth = useAuthStore()
const cases = ref<ValuationCaseModel[]>([])
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const notice = ref('')
const createOpen = ref(false)
const searchQuery = ref('')
const statusFilter = ref('')
const canCreate = computed(() => auth.permissions.includes('case.create') && auth.permissions.includes('valuation.update'))
const createDraft = reactive({
  caseNo: '',
  title: '',
  requestingAgency: '',
  valuationBaseDate: '',
  valuationDueDate: '',
  districtCode: '',
  landUseType: '',
})
const activeWorkCount = computed(() => cases.value.filter((item) =>
  !['IN_REVIEW', 'REVIEWING', 'COMPLETED', 'REVIEW_COMPLETED', 'ARCHIVED'].includes(item.status),
).length)
const revisionCount = computed(() => cases.value.filter((item) =>
  ['CORRECTION', 'REVISION_REQUIRED'].includes(item.status),
).length)
const dueSoonCount = computed(() => {
  const today = new Date()
  const cutoff = new Date(today)
  cutoff.setDate(today.getDate() + 7)
  return cases.value.filter((item) => {
    if (!item.valuationDueDate || ['COMPLETED', 'REVIEW_COMPLETED', 'ARCHIVED'].includes(item.status)) return false
    const due = new Date(`${item.valuationDueDate}T23:59:59`)
    return due >= today && due <= cutoff
  }).length
})
const availableStatuses = computed(() => Array.from(new Set(cases.value.map((item) => item.status))))
const filteredCases = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase('zh-Hant')
  return [...cases.value]
    .filter((item) => !statusFilter.value || item.status === statusFilter.value)
    .filter((item) => !query || `${item.caseNo} ${item.name}`.toLocaleLowerCase('zh-Hant').includes(query))
    .sort((left, right) => {
      const leftDue = left.valuationDueDate ?? '9999-12-31'
      const rightDue = right.valuationDueDate ?? '9999-12-31'
      return leftDue.localeCompare(rightDue) || right.updatedAt.localeCompare(left.updatedAt)
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
    caseNo: '', title: '', requestingAgency: '', valuationBaseDate: '',
    valuationDueDate: '', districtCode: '', landUseType: '',
  })
}

function caseDisplayStatus(row: ValuationCaseModel): string {
  if (!row.basicInfoConfirmedAt) return '待確認案件資料'
  return statusLabel(row.status)
}

function caseStatusTone(row: ValuationCaseModel): 'neutral' | 'active' | 'warning' | 'success' {
  if (!row.basicInfoConfirmedAt) return 'neutral'
  if (['CORRECTION', 'REVISION_REQUIRED'].includes(row.status)) return 'warning'
  if (['COMPLETED', 'REVIEW_COMPLETED'].includes(row.status)) return 'success'
  return 'active'
}

function caseNextAction(row: ValuationCaseModel): string {
  if (!row.basicInfoConfirmedAt) return '確認案件資料'
  if (['CORRECTION', 'REVISION_REQUIRED'].includes(row.status)) return '處理補正'
  if (['IN_REVIEW', 'REVIEWING'].includes(row.status)) return '查看送審狀態'
  if (['COMPLETED', 'REVIEW_COMPLETED', 'ARCHIVED'].includes(row.status)) return '查看案件'
  if (row.lastWorkspaceStage === 'documents' || row.lastWorkspaceStage === 'ai-review') return '整理來源資料'
  if (row.lastWorkspaceStage === 'data') return '補齊估價資料'
  if (row.lastWorkspaceStage === 'calculation') return '完成計算與檢核'
  if (row.lastWorkspaceStage === 'report') return '完成查估書與送審'
  return '繼續估價'
}

function caseNextDetail(row: ValuationCaseModel): string {
  if (!row.basicInfoConfirmedAt) return '請先確認案件基本資料，再開始估價作業。'
  if (['CORRECTION', 'REVISION_REQUIRED'].includes(row.status)) return '審查端已有修正要求，建議優先處理。'
  if (['IN_REVIEW', 'REVIEWING'].includes(row.status)) return '本版已送審，目前等待審查結果。'
  if (['COMPLETED', 'REVIEW_COMPLETED'].includes(row.status)) return '案件流程已完成，可查看既有資料與輸出。'
  if (row.status === 'ARCHIVED') return '案件已封存，目前僅供查閱。'
  const labels: Record<string, string> = {
    documents: '整理來源文件並完成必要資料辨識。',
    'ai-review': '仍有辨識結果需要人工確認。',
    data: '確認宗地、比準地與正式估價資料。',
    calculation: '執行估價計算並處理檢核結果。',
    report: '確認查估書、正式文件並完成送審。',
  }
  return labels[row.lastWorkspaceStage] ?? '接續目前案件進度。'
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
      case_type: VALUATION_CASE_TYPE,
      requesting_agency: createDraft.requestingAgency || null,
      valuation_base_date: createDraft.valuationBaseDate,
      valuation_due_date: createDraft.valuationDueDate || null,
      city_code: NEW_TAIPEI_CITY_CODE,
      district_code: createDraft.districtCode,
      land_use_type: createDraft.landUseType || null,
    })
    createOpen.value = false
    resetCreateDraft()
    resetValuationFlow()
    await router.push(valuationStageRoute(created.case_id, 'case'))
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    creating.value = false
  }
}

async function openCase(caseId: string): Promise<void> {
  resetValuationFlow()
  const row = cases.value.find((item) => item.caseId === caseId)
  const stage = row?.basicInfoConfirmedAt ? row.lastWorkspaceStage : 'case'
  await router.push(valuationStageRoute(caseId, stage))
}

onMounted(() => {
  void loadCases()
})
</script>

<template>
  <div class="valuation-dashboard">
    <header class="valuation-dashboard__header" data-testid="valuation-dashboard-header">
      <div class="valuation-dashboard__intro">
        <p class="valuation-eyebrow">估價作業</p>
        <h1>估價案件</h1>
        <p>從目前工作狀態找到下一個要處理的案件，不需要先判斷系統流程或功能位置。</p>
      </div>
      <button v-if="canCreate" class="solid-button solid-button--primary" type="button" data-testid="create-case" @click="createOpen = true">
        <Plus :size="17" weight="bold" aria-hidden="true" />
        建立案件
      </button>
    </header>

    <section v-if="cases.length" class="work-summary" data-testid="valuation-dashboard-summary" aria-label="我的工作摘要">
      <article>
        <span class="work-summary__icon"><FileText :size="22" weight="duotone" aria-hidden="true" /></span>
        <div><small>待處理</small><strong>{{ activeWorkCount }}</strong></div>
      </article>
      <article>
        <span class="work-summary__icon work-summary__icon--warning"><WarningCircle :size="22" weight="duotone" aria-hidden="true" /></span>
        <div><small>補正中</small><strong>{{ revisionCount }}</strong></div>
      </article>
      <article>
        <span class="work-summary__icon work-summary__icon--due"><ClockCountdown :size="22" weight="duotone" aria-hidden="true" /></span>
        <div><small>7 日內到期</small><strong>{{ dueSoonCount }}</strong></div>
      </article>
    </section>

    <p v-if="notice" class="dashboard-notice" role="status">{{ notice }}</p>
    <p v-if="error && cases.length" class="dashboard-error" role="alert">{{ error }}</p>

    <section class="valuation-case-list" data-testid="valuation-case-list" aria-labelledby="valuation-case-list-title">
      <div class="valuation-case-list__toolbar">
        <h2 id="valuation-case-list-title" class="sr-only">案件列表</h2>
        <label class="case-search">
          <MagnifyingGlass :size="17" aria-hidden="true" />
          <span class="sr-only">搜尋案件名稱或編號</span>
          <input v-model="searchQuery" type="search" placeholder="搜尋案件名稱 / 編號">
        </label>
        <label class="case-filter">
          <span>狀態</span>
          <select v-model="statusFilter">
            <option value="">全部</option>
            <option v-for="status in availableStatuses" :key="status" :value="status">{{ statusLabel(status) }}</option>
          </select>
        </label>
        <span class="valuation-case-list__count">共 {{ filteredCases.length }} 件</span>
      </div>

      <div v-if="loading" class="case-list-state">案件載入中…</div>
      <div v-else-if="error && !cases.length" class="case-list-state case-list-state--error">
        <span>{{ error }}</span><button type="button" @click="loadCases">重新整理</button>
      </div>
      <div v-else-if="!filteredCases.length" class="case-list-state">目前沒有符合條件的案件。</div>
      <div v-else class="case-cards">
        <article v-for="row in filteredCases" :key="row.caseId" class="case-card" :data-testid="`case-row-${row.caseId}`">
          <div class="case-card__main">
            <div class="case-card__title-row">
              <div>
                <h2>{{ row.name }}</h2>
                <span>{{ row.caseNo }}</span>
              </div>
              <span class="case-status" :data-tone="caseStatusTone(row)">{{ caseDisplayStatus(row) }}</span>
            </div>
            <p class="case-card__next"><FileText :size="15" weight="duotone" aria-hidden="true" />{{ caseNextDetail(row) }}</p>
          </div>
          <div class="case-card__deadline">
            <template v-if="row.valuationDueDate">
              <CalendarBlank :size="15" weight="duotone" aria-hidden="true" />
              <span>{{ formatDateZhTw(row.valuationDueDate) }} 到期</span>
            </template>
            <span v-else>未設定作業期限</span>
          </div>
          <button class="case-action-button" type="button" :data-testid="`case-open-${row.caseId}`" @click="openCase(row.caseId)">
            <span>{{ caseNextAction(row) }}</span><ArrowRight :size="16" weight="bold" aria-hidden="true" />
          </button>
        </article>
      </div>
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
          <label><span>估價基準日 *</span><input v-model="createDraft.valuationBaseDate" type="date" required /></label>
          <label>
            <span>行政區 *</span>
            <select v-model="createDraft.districtCode" required data-testid="create-case-district">
              <option value="" disabled>請選擇新北市行政區</option>
              <option v-for="district in NEW_TAIPEI_DISTRICTS" :key="district.code" :value="district.code">
                {{ district.name }}
              </option>
            </select>
            <small>本系統查估範圍固定為新北市；正式行政區代碼由系統自動帶入。</small>
          </label>
          <label>
            <span>土地用途 *</span>
            <select v-model="createDraft.landUseType" required data-testid="case-land-use-type">
              <option disabled value="">請選擇土地用途</option>
              <option v-for="option in LAND_USE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <small>請從清單選擇，系統會自動儲存對應的正式規則代碼。</small>
          </label>
          <details class="create-case-more create-case-grid__wide">
            <summary>其他案件資料</summary>
            <div class="create-case-more__grid">
              <label><span>估價作業期限</span><input v-model="createDraft.valuationDueDate" type="date" /></label>
              <label><span>申請機關</span><input v-model.trim="createDraft.requestingAgency" maxlength="200" /></label>
              <div class="create-case-fixed-field" data-testid="create-case-type-fixed">
                <span>案件類型</span>
                <strong>{{ valuationCaseTypeLabel(VALUATION_CASE_TYPE) }}</strong>
                <small>系統固定辦理土地徵收補償市價查估，不需另外選擇。</small>
              </div>
            </div>
          </details>
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
.valuation-dashboard {
  display: grid;
  gap: 16px;
  padding: 28px 30px 36px;
}

.valuation-dashboard__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e1e7ee;
}

.valuation-dashboard__header > div {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.valuation-dashboard__header h1 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 28px;
  font-weight: 650;
  letter-spacing: -.035em;
}

.valuation-dashboard__header p:last-child {
  max-width: 720px;
  margin: 0;
  color: #687b8f;
  font-size: 12px;
  line-height: 1.65;
}

.work-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.work-summary article { display:flex; align-items:center; gap:12px; min-height:92px; padding:16px 18px; border:1px solid #dce4ed; border-radius:12px; background:#fff; }
.work-summary__icon { display:grid; width:44px; height:44px; flex:0 0 44px; place-items:center; border-radius:12px; color:#2e5984; background:#edf4fb; }
.work-summary__icon--warning { color:#9a5c17; background:#fff2de; }
.work-summary__icon--due { color:#9a4638; background:#fff0ed; }
.work-summary article > div { display:grid; gap:3px; }
.work-summary small { color:#6d7e90; font-size:11px; font-weight:800; }
.work-summary strong { color:var(--app-ink); font-size:26px; line-height:1; }

.valuation-case-list {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dce4ed;
  border-radius: 11px;
  background: #fff;
}

.valuation-case-list__toolbar { display:grid; grid-template-columns:minmax(260px,1fr) 220px auto; align-items:end; gap:12px; padding:14px 16px; border-bottom:1px solid #e4e9ef; background:#fafbfd; }
.case-search { position:relative; display:flex; align-items:center; min-width:0; color:#6e8195; }
.case-search > svg { position:absolute; left:12px; pointer-events:none; }
.case-search input { width:100%; min-height:44px; padding:9px 12px 9px 38px; border:1px solid #d4dee8; border-radius:9px; color:var(--app-ink); background:#fff; font:inherit; }
.case-filter { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:8px; color:#687b8f; font-size:11px; font-weight:850; }
.case-filter select { min-height:44px; padding:8px 10px; border:1px solid #d4dee8; border-radius:9px; color:var(--app-ink); background:#fff; font:inherit; }
.valuation-case-list__count { align-self:center; color:#718094; font-size:11px; font-weight:800; white-space:nowrap; }
.case-list-state { display:flex; min-height:180px; align-items:center; justify-content:center; gap:10px; padding:28px; color:#718094; font-size:12px; text-align:center; }
.case-list-state--error { color:#9a4638; }
.case-list-state button { min-height:36px; padding:6px 10px; border:1px solid #d4dee8; border-radius:8px; color:#244d73; background:#fff; cursor:pointer; font-weight:800; }
.case-cards { display:grid; }
.case-card { display:grid; grid-template-columns:minmax(0,1fr) auto auto; align-items:center; gap:18px; padding:18px 20px; border-bottom:1px solid #e9edf2; background:#fff; }
.case-card:last-child { border-bottom:0; }
.case-card:hover { background:#fbfcfe; }
.case-card__main { display:grid; min-width:0; gap:9px; }
.case-card__title-row { display:flex; align-items:flex-start; flex-wrap:wrap; gap:9px 12px; }
.case-card__title-row > div { display:grid; min-width:0; gap:2px; }
.case-card__title-row h2 { margin:0; overflow:hidden; color:var(--app-ink); font-size:16px; font-weight:850; text-overflow:ellipsis; white-space:nowrap; }
.case-card__title-row > div > span { color:#76879a; font-size:10px; font-weight:750; }
.case-status { display:inline-flex; min-height:26px; align-items:center; padding:4px 8px; border-radius:999px; font-size:9px; font-weight:900; white-space:nowrap; }
.case-status[data-tone="neutral"] { color:#5c6f83; background:#eef2f6; }
.case-status[data-tone="active"] { color:#2e5984; background:#edf4fb; }
.case-status[data-tone="warning"] { color:#955119; background:#fff0df; }
.case-status[data-tone="success"] { color:#2f745b; background:#edf8f3; }
.case-card__next { display:flex; align-items:flex-start; gap:6px; margin:0; color:#66798d; font-size:11px; line-height:1.55; }
.case-card__next > svg { flex:0 0 auto; margin-top:1px; }
.case-card__deadline { display:flex; align-items:center; justify-content:flex-end; gap:5px; color:#687b8f; font-size:10px; font-weight:800; white-space:nowrap; }
.case-action-button { display:inline-flex; min-height:38px; align-items:center; justify-content:center; gap:6px; padding:7px 12px; border:1px solid #2e5984; border-radius:8px; color:#fff; background:#2e5984; cursor:pointer; font-size:10px; font-weight:900; white-space:nowrap; }
.case-action-button:hover { background:#244d73; }
.sr-only { position:absolute!important; width:1px!important; height:1px!important; padding:0!important; margin:-1px!important; overflow:hidden!important; clip:rect(0,0,0,0)!important; white-space:nowrap!important; border:0!important; }

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
.create-case-fixed-field { display: grid; gap: 5px; padding: 10px 11px; border: 1px solid #dce4ed; border-radius: 10px; background: #f7f9fc; }
.create-case-fixed-field > span { color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.create-case-fixed-field > strong { color: var(--app-ink); font-size: 13px; }
.create-case-fixed-field > small { color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.create-case-grid__wide { grid-column: 1 / -1; }
.create-case-more { padding:12px; border:1px solid #dce4ed; border-radius:10px; background:#f8fafc; }
.create-case-more summary { cursor:pointer; color:#40566e; font-size:12px; font-weight:850; }
.create-case-more__grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:12px; }
.create-case-more__grid .create-case-fixed-field { grid-column:1/-1; }
.create-case-grid input,
.create-case-grid select { min-height: 44px; padding: 9px 11px; border: 1px solid var(--app-line); border-radius: 10px; color: var(--app-ink); background: rgba(255,255,255,.8); font: inherit; }
.create-case-grid label small { color: var(--app-muted); font-size: 10px; font-weight: 500; line-height: 1.5; }
.create-case-grid input:focus,
.create-case-grid select:focus { outline: 3px solid rgba(200, 91, 67, .16); border-color: var(--app-accent); }
.create-case-actions { display: flex; justify-content: flex-end; gap: 8px; }

.valuation-eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

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
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-color: var(--app-accent);
  color: #fff;
  background: var(--app-accent);
}

.solid-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

@media (max-width: 640px) {
  .valuation-dashboard {
    padding: 18px 16px 28px;
  }

  .valuation-dashboard__header {
    align-items: stretch;
    flex-direction: column;
  }

  .work-summary { grid-template-columns:1fr; }
  .valuation-case-list__toolbar { grid-template-columns:1fr; }
  .case-filter { grid-template-columns:auto 1fr; }
  .valuation-case-list__count { justify-self:start; }
  .case-card { grid-template-columns:1fr; align-items:stretch; gap:10px; }
  .case-card__deadline { justify-content:flex-start; }
  .case-action-button { width:100%; }

  .solid-button {
    width: 100%;
  }
  .create-case-form { min-width: 0; }
  .create-case-grid { grid-template-columns: 1fr; }
  .create-case-grid__wide { grid-column: auto; }
  .create-case-more__grid { grid-template-columns:1fr; }
  .create-case-more__grid .create-case-fixed-field { grid-column:auto; }
  .create-case-actions { flex-direction: column-reverse; }
}
</style>
