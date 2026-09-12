<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhPlus as Plus } from '@phosphor-icons/vue'
import CaseTable from '../../../components/common/CaseTable.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { useAuthStore } from '../../../stores/auth.store'
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
const sortBy = ref('valuationDueDate')
const sortDirection = ref<'asc' | 'desc'>('asc')
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
const casesWithDeadlineCount = computed(() => cases.value.filter((item) => Boolean(item.valuationDueDate)).length)
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
    caseNo: '', title: '', requestingAgency: '', valuationBaseDate: '',
    valuationDueDate: '', districtCode: '', landUseType: '',
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
      <div>
        <p class="valuation-eyebrow">估價作業</p>
        <h1>估價案件</h1>
        <p>建立新案件或接續既有案件。進入案件後，會顯示案件基本資料與五階段作業進度。</p>
      </div>
      <button v-if="canCreate" class="solid-button solid-button--primary" type="button" data-testid="create-case" @click="createOpen = true">
        <Plus :size="17" weight="bold" aria-hidden="true" />
        建立案件
      </button>
    </header>

    <div v-if="cases.length" class="valuation-dashboard__summary" data-testid="valuation-dashboard-summary" aria-label="案件列表摘要">
      <span>目前 {{ cases.length }} 件案件</span>
      <span>{{ casesWithDeadlineCount }} 件已設定作業期限</span>
      <span>預設依作業期限由近到遠排列</span>
    </div>

    <p v-if="notice" class="dashboard-notice" role="status">{{ notice }}</p>
    <p v-if="error && cases.length" class="dashboard-error" role="alert">{{ error }}</p>

    <section class="valuation-case-list" data-testid="valuation-case-list" aria-labelledby="valuation-case-list-title">
      <div class="valuation-case-list__heading">
        <div>
          <h2 id="valuation-case-list-title">案件列表</h2>
          <p>選擇案件後會回到該案件目前的估價工作流程。</p>
        </div>
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
          <div class="create-case-fixed-field" data-testid="create-case-type-fixed">
            <span>案件類型</span>
            <strong>{{ valuationCaseTypeLabel(VALUATION_CASE_TYPE) }}</strong>
            <small>本系統目前固定辦理土地徵收補償市價查估，不需另外輸入案件類型。</small>
          </div>
          <label><span>估價基準日 *</span><input v-model="createDraft.valuationBaseDate" type="date" required /></label>
          <label><span>估價作業期限</span><input v-model="createDraft.valuationDueDate" type="date" /></label>
          <label><span>申請機關</span><input v-model.trim="createDraft.requestingAgency" maxlength="200" /></label>
          <label class="create-case-grid__wide">
            <span>行政區 *</span>
            <select v-model="createDraft.districtCode" required data-testid="create-case-district">
              <option value="" disabled>請選擇新北市行政區</option>
              <option v-for="district in NEW_TAIPEI_DISTRICTS" :key="district.code" :value="district.code">
                {{ district.name }}
              </option>
            </select>
            <small>本系統查估範圍固定為新北市；正式行政區代碼由系統自動帶入。</small>
          </label>
          <label class="create-case-grid__wide">
            <span>土地用途 *</span>
            <select v-model="createDraft.landUseType" required data-testid="case-land-use-type">
              <option disabled value="">請選擇土地用途</option>
              <option v-for="option in LAND_USE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <small>請從清單選擇，系統會自動儲存對應的正式規則代碼。</small>
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

.valuation-dashboard__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 7px 18px;
  padding: 3px 2px;
  color: #6c7d90;
  font-size: 10px;
  font-weight: 750;
}

.valuation-dashboard__summary span + span::before {
  content: '·';
  margin-right: 18px;
  color: #b0bbc6;
}

.valuation-case-list {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dce4ed;
  border-radius: 11px;
  background: #fff;
}

.valuation-case-list__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 18px;
  border-bottom: 1px solid #e4e9ef;
  background: #fafbfd;
}

.valuation-case-list__heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-size: 15px;
  font-weight: 850;
}

.valuation-case-list__heading p {
  margin: 4px 0 0;
  color: #75869a;
  font-size: 10px;
  line-height: 1.5;
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
.create-case-fixed-field { display: grid; gap: 5px; padding: 10px 11px; border: 1px solid #dce4ed; border-radius: 10px; background: #f7f9fc; }
.create-case-fixed-field > span { color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.create-case-fixed-field > strong { color: var(--app-ink); font-size: 13px; }
.create-case-fixed-field > small { color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.create-case-grid__wide { grid-column: 1 / -1; }
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

  .valuation-dashboard__summary {
    display: grid;
    gap: 4px;
  }

  .valuation-dashboard__summary span + span::before { content: none; }

  .solid-button {
    width: 100%;
  }
  .create-case-form { min-width: 0; }
  .create-case-grid { grid-template-columns: 1fr; }
  .create-case-grid__wide { grid-column: auto; }
  .create-case-actions { flex-direction: column-reverse; }
}
</style>
