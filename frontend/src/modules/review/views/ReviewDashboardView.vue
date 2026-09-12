<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  PhCaretRight as CaretRight,
  PhFunnelSimple as FunnelSimple,
  PhMagnifyingGlass as MagnifyingGlass,
  PhPlus as Plus,
  PhX as X,
} from '@phosphor-icons/vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import { formatDateZhTw } from '../../../utils/formatters'
import { NEW_TAIPEI_DISTRICTS } from '../../valuation/newTaipei'
import { reviewApi, safeReviewErrorMessage } from '../review.api'
import {
  caseSourceLabel,
  mapWorkbenchCase,
  mapWorkbenchSummary,
  reviewStatusLabel,
  riskLevelLabel,
  statusGroupLabel,
  urgencyLabel,
} from '../review.mappers'
import type { ReviewQueueItemModel, ReviewSummaryModel } from '../review.types'

const route = useRoute()
const router = useRouter()
const summary = ref<ReviewSummaryModel | null>(null)
const cases = ref<ReviewQueueItemModel[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const filtersOpen = ref(false)
const searchTerm = ref('')
const createOpen = ref(false)
const creating = ref(false)
const createError = ref('')
const createDraft = reactive({
  caseNo: '',
  caseTitle: '',
  sourceOrganization: '',
  districtCode: '',
  valuationBaseDate: '',
  receivedAt: '',
  dueAt: '',
})
let loadSerial = 0
let activeController: AbortController | null = null

const allowedQueryKeys = new Set([
  'q',
  'status',
  'riskLevel',
  'statusGroup',
  'source',
  'district',
  'urgency',
  'sortBy',
  'sortDirection',
  'page',
  'pageSize',
])

const page = computed(() => positiveQuery('page', 1))
const pageSize = computed(() => positiveQuery('pageSize', 20))
const sortBy = computed(() => stringQuery('sortBy', 'updatedAt'))
const sortDirection = computed<'asc' | 'desc'>(() => (stringQuery('sortDirection', 'desc') === 'asc' ? 'asc' : 'desc'))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / Math.max(1, pageSize.value))))
const summaryTotal = computed(() => Object.values(summary.value?.statusCounts ?? {}).reduce((sum, count) => sum + count, 0))
const sortValue = computed(() => `${sortBy.value}:${sortDirection.value}`)

const quickFilters = computed(() => [
  { key: '', label: '全部', count: summaryTotal.value, testId: 'kpi-all' },
  { key: 'pending', label: '待處理', count: summary.value?.statusCounts.pending ?? 0, testId: 'kpi-pending' },
  { key: 'in_progress', label: '審查中', count: summary.value?.statusCounts.in_progress ?? 0, testId: 'kpi-in-progress' },
  { key: 'needs_input', label: '待補正', count: summary.value?.statusCounts.needs_input ?? 0, testId: 'kpi-needs-input' },
  { key: 'completed', label: '已完成', count: summary.value?.statusCounts.completed ?? 0, testId: 'kpi-completed' },
])

const activeFilters = computed(() => {
  const items: Array<{ key: string; label: string }> = []
  const q = stringQuery('q', '')
  const status = stringQuery('status', '')
  const statusGroup = stringQuery('statusGroup', '')
  const source = stringQuery('source', '')
  const riskLevel = stringQuery('riskLevel', '')
  const district = stringQuery('district', '')
  const urgency = stringQuery('urgency', '')

  if (q) items.push({ key: 'q', label: `搜尋：${q}` })
  if (status) items.push({ key: 'status', label: reviewStatusLabel(status) })
  if (statusGroup) items.push({ key: 'statusGroup', label: statusGroupLabel(statusGroup) })
  if (source) items.push({ key: 'source', label: caseSourceLabel(source) })
  if (riskLevel) items.push({ key: 'riskLevel', label: riskLevelLabel(riskLevel) })
  if (district) items.push({ key: 'district', label: `行政區：${district}` })
  if (urgency) items.push({ key: 'urgency', label: urgencyLabel(urgency) })
  return items
})

const hasActiveQueueView = computed(() =>
  activeFilters.value.length > 0
    || Boolean(stringQuery('sortBy', ''))
    || Boolean(stringQuery('sortDirection', ''))
    || page.value > 1,
)

function stringQuery(name: string, fallback: string): string {
  const value = route.query[name]
  return typeof value === 'string' ? value : fallback
}

function positiveQuery(name: string, fallback: number): number {
  const parsed = Number.parseInt(stringQuery(name, ''), 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function queueParams() {
  return {
    q: stringQuery('q', '') || undefined,
    status: stringQuery('status', '') || undefined,
    riskLevel: stringQuery('riskLevel', '') || undefined,
    statusGroup: stringQuery('statusGroup', '') || undefined,
    source: stringQuery('source', '') || undefined,
    district: stringQuery('district', '') || undefined,
    urgency: stringQuery('urgency', '') || undefined,
    sortBy: sortBy.value,
    sortDirection: sortDirection.value,
    limit: pageSize.value,
    offset: (page.value - 1) * pageSize.value,
  }
}

async function loadData(): Promise<void> {
  const serial = ++loadSerial
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  error.value = ''
  try {
    const [summaryDto, queueDto] = await Promise.all([
      reviewApi.getSummary(controller.signal),
      reviewApi.listCases(queueParams(), controller.signal),
    ])
    if (serial !== loadSerial) return
    summary.value = mapWorkbenchSummary(summaryDto)
    cases.value = queueDto.items.map(mapWorkbenchCase)
    total.value = queueDto.total
  } catch (caught: unknown) {
    if (serial === loadSerial && !controller.signal.aborted) error.value = safeReviewErrorMessage(caught)
  } finally {
    if (serial === loadSerial) loading.value = false
  }
}

function normalizedQueueQuery(query: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(query).filter(([key, value]) => allowedQueryKeys.has(key) && value))
}

function currentQueueQuery(): Record<string, string> {
  return normalizedQueueQuery(Object.fromEntries(
    Object.entries(route.query).map(([key, value]) => [key, Array.isArray(value) ? value[0] ?? '' : value ?? '']),
  ))
}

function updateQuery(query: Record<string, string>, resetPage = true): void {
  const merged = currentQueueQuery()
  for (const [key, value] of Object.entries(query)) {
    if (value) merged[key] = value
    else delete merged[key]
  }
  if (resetPage) delete merged.page
  void router.replace({ query: normalizedQueueQuery(merged) }).then(loadData)
}

function submitSearch(): void {
  updateQuery({ q: searchTerm.value.trim() })
}

function applyQuickFilter(statusGroup: string): void {
  updateQuery({ statusGroup, status: '' })
}

function applyAdvancedFilter(name: string, value: string): void {
  updateQuery({ [name]: value })
}

function changeSort(value: string): void {
  const [nextSortBy, nextDirection] = value.split(':')
  updateQuery({ sortBy: nextSortBy ?? 'updatedAt', sortDirection: nextDirection === 'asc' ? 'asc' : 'desc' })
}

function removeFilter(name: string): void {
  if (name === 'q') searchTerm.value = ''
  updateQuery({ [name]: '' })
}

function resetQueueView(): void {
  searchTerm.value = ''
  const pageSizeValue = stringQuery('pageSize', '')
  void router.replace({
    query: pageSizeValue && pageSizeValue !== '20' ? { pageSize: pageSizeValue } : {},
  }).then(loadData)
}

function goToPage(nextPage: number): void {
  if (nextPage < 1 || nextPage > pageCount.value || nextPage === page.value) return
  updateQuery({ page: String(nextPage) }, false)
}

function openCase(row: ReviewQueueItemModel): void {
  if (!row.reviewId) return
  void router.push({
    name: 'review-workbench',
    params: { reviewId: row.reviewId },
    query: currentQueueQuery(),
  })
}

function localDateTimeValue(date = new Date()): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function resetCreateDraft(): void {
  Object.assign(createDraft, {
    caseNo: '',
    caseTitle: '',
    sourceOrganization: '',
    districtCode: '',
    valuationBaseDate: '',
    receivedAt: localDateTimeValue(),
    dueAt: '',
  })
  createError.value = ''
}

function openCreateCase(): void {
  resetCreateDraft()
  createOpen.value = true
}

function closeCreateCase(): void {
  if (creating.value) return
  createOpen.value = false
  createError.value = ''
}

function optionalIso(value: string): string | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

async function createExternalCase(): Promise<void> {
  if (creating.value) return
  createError.value = ''
  if (!createDraft.caseTitle.trim() || !createDraft.districtCode || !createDraft.valuationBaseDate) {
    createError.value = '請填寫案件名稱、行政區與估價基準日。'
    return
  }
  if (createDraft.receivedAt && createDraft.dueAt) {
    const received = new Date(createDraft.receivedAt).getTime()
    const due = new Date(createDraft.dueAt).getTime()
    if (Number.isFinite(received) && Number.isFinite(due) && due < received) {
      createError.value = '審查期限不得早於收件時間。'
      return
    }
  }

  creating.value = true
  try {
    const created = await reviewApi.createExternalCase({
      case_no: createDraft.caseNo.trim() || null,
      case_title: createDraft.caseTitle.trim(),
      source_organization: createDraft.sourceOrganization.trim() || null,
      district_code: createDraft.districtCode,
      valuation_base_date: createDraft.valuationBaseDate,
      received_at: optionalIso(createDraft.receivedAt),
      due_at: optionalIso(createDraft.dueAt),
    })
    createOpen.value = false
    resetCreateDraft()
    await router.push({
      name: 'review-workbench',
      params: { reviewId: created.review_id },
      query: currentQueueQuery(),
    })
  } catch (caught: unknown) {
    createError.value = safeReviewErrorMessage(caught)
  } finally {
    creating.value = false
  }
}

function totalFindingCount(row: ReviewQueueItemModel): number {
  return row.highCount + row.mediumCount + row.lowCount
}

function riskTone(row: ReviewQueueItemModel): string {
  const risk = row.riskLevelCode?.toUpperCase()
  if (risk === 'CRITICAL' || risk === 'HIGH') return 'is-high'
  if (risk === 'MEDIUM') return 'is-medium'
  if (risk === 'LOW') return 'is-low'
  return 'is-neutral'
}

watch(
  () => route.query.q,
  (value) => {
    searchTerm.value = typeof value === 'string' ? value : ''
  },
  { immediate: true },
)

onMounted(loadData)

onBeforeUnmount(() => {
  activeController?.abort()
})
</script>

<template>
  <section class="review-dashboard" data-testid="review-dashboard">
    <PageHeader
      eyebrow="案件審查"
      title="審查案件"
      description="集中查看平台送審與外部案件，依目前階段、風險與期限接續審查工作。"
    >
      <template #actions>
        <button
          class="review-dashboard__create"
          type="button"
          data-testid="create-review-case"
          @click="openCreateCase"
        >
          <Plus :size="17" weight="bold" aria-hidden="true" />
          建立審查案件
        </button>
      </template>
    </PageHeader>

    <div v-if="loading && !summary" class="review-dashboard__loading">
      <LoadingSkeleton :rows="5" label="審查案件載入中" />
    </div>
    <ErrorState v-else-if="error && !summary" :message="error" @retry="loadData" />
    <template v-else>
      <section class="review-dashboard__controls" aria-label="案件搜尋與篩選">
        <div class="review-dashboard__control-row">
          <form class="review-dashboard__search" role="search" @submit.prevent="submitSearch">
            <MagnifyingGlass :size="18" aria-hidden="true" />
            <input
              v-model="searchTerm"
              type="search"
              data-testid="review-case-search"
              placeholder="搜尋案件編號或案件名稱"
              autocomplete="off"
            >
            <button type="submit">搜尋</button>
          </form>

          <button
            class="review-dashboard__filter-toggle"
            :class="{ 'is-active': filtersOpen || activeFilters.length > 0 }"
            type="button"
            data-testid="review-filter-toggle"
            :aria-expanded="filtersOpen ? 'true' : 'false'"
            aria-controls="review-advanced-filters"
            @click="filtersOpen = !filtersOpen"
          >
            <FunnelSimple :size="18" weight="bold" aria-hidden="true" />
            篩選
            <span v-if="activeFilters.length">{{ activeFilters.length }}</span>
          </button>

          <label class="review-dashboard__sort">
            <span>排序</span>
            <select data-testid="review-sort" :value="sortValue" @change="changeSort(($event.target as HTMLSelectElement).value)">
              <option value="updatedAt:desc">最近收件</option>
              <option value="dueAt:asc">最早到期</option>
              <option value="risk:desc">風險最高</option>
              <option value="caseNo:asc">案件編號</option>
              <option value="name:asc">案件名稱</option>
            </select>
          </label>
        </div>

        <div class="review-dashboard__quick-filters" aria-label="快速案件篩選">
          <button
            v-for="item in quickFilters"
            :key="item.key || 'all'"
            :data-testid="item.testId"
            :class="{ 'is-active': stringQuery('statusGroup', '') === item.key && !stringQuery('status', '') }"
            type="button"
            @click="applyQuickFilter(item.key)"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.count }}</strong>
          </button>
        </div>

        <div
          v-show="filtersOpen"
          id="review-advanced-filters"
          class="review-dashboard__advanced-filters"
          data-testid="review-advanced-filters"
        >
          <label>
            <span>案件狀態</span>
            <select name="status" :value="stringQuery('status', '')" @change="applyAdvancedFilter('status', ($event.target as HTMLSelectElement).value)">
              <option value="">全部狀態</option>
              <option value="RECEIVED">已收件</option>
              <option value="PREPROCESSING">前處理中</option>
              <option value="PENDING_MATERIALS">待補資料</option>
              <option value="READY_FOR_REVIEW">待審查</option>
              <option value="ANALYZING">分析中</option>
              <option value="REVIEW_REQUIRED">需人工判定</option>
              <option value="RETURNED_FOR_REVISION">退回補正</option>
              <option value="SUPPLEMENT_REQUIRED">待補件</option>
              <option value="EXPERT_REVIEW">專業覆核</option>
              <option value="REVIEW_COMPLETED">審查完成</option>
            </select>
          </label>

          <label>
            <span>案件來源</span>
            <select name="source" :value="stringQuery('source', '')" @change="applyAdvancedFilter('source', ($event.target as HTMLSelectElement).value)">
              <option value="">全部來源</option>
              <option value="PLATFORM">平台送審</option>
              <option value="EXTERNAL">外部案件</option>
            </select>
          </label>

          <label>
            <span>風險程度</span>
            <select name="riskLevel" :value="stringQuery('riskLevel', '')" @change="applyAdvancedFilter('riskLevel', ($event.target as HTMLSelectElement).value)">
              <option value="">全部風險</option>
              <option value="LOW">低風險</option>
              <option value="MEDIUM">中風險</option>
              <option value="HIGH">高風險</option>
              <option value="CRITICAL">極高風險</option>
            </select>
          </label>

          <label>
            <span>行政區</span>
            <input
              name="district"
              type="text"
              :value="stringQuery('district', '')"
              placeholder="例如：新店區"
              @change="applyAdvancedFilter('district', ($event.target as HTMLInputElement).value.trim())"
            >
          </label>

          <label>
            <span>期限狀態</span>
            <select name="urgency" :value="stringQuery('urgency', '')" @change="applyAdvancedFilter('urgency', ($event.target as HTMLSelectElement).value)">
              <option value="">全部期限</option>
              <option value="OVERDUE">已逾期</option>
              <option value="URGENT">緊急</option>
              <option value="DUE_SOON">即將到期</option>
              <option value="NORMAL">一般</option>
              <option value="NOT_SET">未設定期限</option>
            </select>
          </label>
        </div>

        <div v-if="activeFilters.length" class="review-dashboard__active-filters" aria-label="目前篩選條件">
          <span>目前篩選</span>
          <button v-for="item in activeFilters" :key="item.key" type="button" @click="removeFilter(item.key)">
            {{ item.label }}
            <X :size="13" weight="bold" aria-hidden="true" />
          </button>
          <button class="review-dashboard__clear" type="button" data-testid="reset-review-queue" @click="resetQueueView">
            清除全部
          </button>
        </div>
        <button
          v-else
          class="review-dashboard__reset-sr"
          type="button"
          data-testid="reset-review-queue"
          :disabled="!hasActiveQueueView"
          @click="resetQueueView"
        >
          清除全部篩選
        </button>
      </section>

      <p v-if="error" class="review-dashboard__inline-error" role="alert">{{ error }}</p>

      <section class="review-dashboard__queue" aria-labelledby="review-queue-title">
        <div class="review-dashboard__queue-heading">
          <div>
            <h2 id="review-queue-title">案件列表</h2>
            <span>共 {{ total }} 件</span>
          </div>
          <button type="button" data-testid="refresh-review-queue" @click="loadData">
            {{ loading ? '更新中…' : '重新整理' }}
          </button>
        </div>

        <LoadingSkeleton v-if="loading" :rows="Math.min(pageSize, 8)" label="案件載入中" />
        <div v-else-if="!cases.length" class="review-dashboard__empty">
          <strong>目前沒有符合條件的審查案件</strong>
          <p>調整搜尋或篩選條件，或清除目前的篩選後再查看。</p>
        </div>
        <div v-else class="review-dashboard__list" role="list">
          <article
            v-for="row in cases"
            :key="row.reviewId"
            class="review-dashboard__case"
            role="listitem"
            :data-testid="`review-case-row-${row.reviewId}`"
            tabindex="0"
            @click="openCase(row)"
            @keydown.enter="openCase(row)"
            @keydown.space.prevent="openCase(row)"
          >
            <div class="review-dashboard__case-main">
              <div class="review-dashboard__case-title">
                <strong>{{ row.caseNo }}</strong>
                <span>{{ row.name }}</span>
              </div>
              <div class="review-dashboard__badges">
                <span class="review-dashboard__source" :data-source="row.caseSourceCode">{{ row.caseSourceLabel }}</span>
                <span class="review-dashboard__status">{{ row.reviewStatusLabel }}</span>
                <span class="review-dashboard__risk" :class="riskTone(row)">{{ row.riskLevelLabel }}</span>
              </div>
              <div class="review-dashboard__case-meta">
                <span>{{ row.district || '行政區未設定' }}</span>
                <span>疑點 {{ totalFindingCount(row) }}</span>
                <span v-if="row.missingItemCount">缺件 {{ row.missingItemCount }}</span>
                <span v-if="row.assignedReviewerName">承辦：{{ row.assignedReviewerName }}</span>
              </div>
            </div>

            <div class="review-dashboard__case-side">
              <div class="review-dashboard__deadline">
                <strong>{{ row.urgencyLabel }}</strong>
                <span>{{ row.dueAt ? `期限 ${formatDateZhTw(row.dueAt)}` : '未設定期限' }}</span>
              </div>
              <small>收件 {{ formatDateZhTw(row.receivedAt) }}</small>
            </div>
            <CaretRight class="review-dashboard__case-caret" :size="20" weight="bold" aria-hidden="true" />
          </article>
        </div>

        <nav v-if="pageCount > 1" class="review-dashboard__pagination" aria-label="案件列表分頁">
          <button type="button" :disabled="page <= 1" @click="goToPage(page - 1)">上一頁</button>
          <span>第 {{ page }} / {{ pageCount }} 頁</span>
          <button type="button" :disabled="page >= pageCount" @click="goToPage(page + 1)">下一頁</button>
        </nav>
      </section>
    </template>

    <GlassModal
      :open="createOpen"
      id="review-create-external-case"
      class="review-external-create-modal"
      title="建立外部審查案件"
      initial-focus="#external-review-case-title"
      @close="closeCreateCase"
    >
      <form class="review-external-create" data-testid="external-review-case-form" @submit.prevent="createExternalCase">
        <div class="review-external-create__notice">
          <strong>僅用於未使用本平台送審的外部廠商案件</strong>
          <p>平台送審案件會自動進入審查清單，不需要在這裡重複建立。建立後會直接進入文件匯入與欄位確認流程。</p>
        </div>

        <div class="review-external-create__grid">
          <label class="review-external-create__wide">
            <span>案件名稱 *</span>
            <input
              id="external-review-case-title"
              v-model.trim="createDraft.caseTitle"
              data-testid="external-case-title"
              maxlength="200"
              required
              placeholder="例如：○○段土地徵收補償市價查估"
            >
          </label>
          <label>
            <span>案件編號</span>
            <input v-model.trim="createDraft.caseNo" data-testid="external-case-no" maxlength="50" placeholder="留空由系統產生" >
            <small>外部廠商有自己的案件編號時再填寫。</small>
          </label>
          <label>
            <span>外部查估單位</span>
            <input v-model.trim="createDraft.sourceOrganization" data-testid="external-case-organization" maxlength="200" placeholder="公司或機構名稱" >
          </label>
          <label>
            <span>行政區 *</span>
            <select v-model="createDraft.districtCode" data-testid="external-case-district" required>
              <option value="" disabled>請選擇新北市行政區</option>
              <option v-for="district in NEW_TAIPEI_DISTRICTS" :key="district.code" :value="district.code">{{ district.name }}</option>
            </select>
            <small>案件範圍固定為新北市，因此不另外要求選擇縣市。</small>
          </label>
          <label>
            <span>估價基準日 *</span>
            <input v-model="createDraft.valuationBaseDate" data-testid="external-case-base-date" type="date" required >
          </label>
          <label>
            <span>收件時間</span>
            <input v-model="createDraft.receivedAt" data-testid="external-case-received-at" type="datetime-local" >
          </label>
          <label>
            <span>審查期限</span>
            <input v-model="createDraft.dueAt" data-testid="external-case-due-at" type="datetime-local" >
          </label>
        </div>

        <p v-if="createError" class="review-external-create__error" role="alert">{{ createError }}</p>
        <div class="review-external-create__actions">
          <button type="button" :disabled="creating" @click="closeCreateCase">取消</button>
          <button type="submit" data-testid="submit-external-review-case" :disabled="creating">
            {{ creating ? '建立中…' : '建立並進入文件匯入' }}
          </button>
        </div>
      </form>
    </GlassModal>
  </section>
</template>

<style scoped>
.review-dashboard {
  padding: 0 28px 34px;
}

.review-dashboard__create {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border: 1px solid var(--app-accent);
  border-radius: 8px;
  color: #fff;
  background: var(--app-accent);
  font-size: 12px;
  font-weight: 900;
}

.review-dashboard__create:disabled {
  cursor: not-allowed;
  opacity: .58;
}

.review-dashboard__create:not(:disabled) { cursor: pointer; }
.review-dashboard__create:not(:disabled):hover { background: var(--app-accent-deep); }

.review-external-create { display: grid; gap: 16px; }
.review-external-create__notice { padding: 13px 14px; border: 1px solid #ead8b1; border-radius: 10px; color: #72531f; background: #fff8e8; }
.review-external-create__notice strong { font-size: 12px; }
.review-external-create__notice p { margin: 5px 0 0; color: #796744; font-size: 11px; line-height: 1.6; }
.review-external-create__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.review-external-create__grid label { display: grid; min-width: 0; gap: 5px; }
.review-external-create__wide { grid-column: 1 / -1; }
.review-external-create__grid label > span { color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.review-external-create__grid input,
.review-external-create__grid select { min-height: 42px; width: 100%; padding: 8px 10px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; font: inherit; font-size: 12px; }
.review-external-create__grid input:focus,
.review-external-create__grid select:focus { border-color: var(--app-accent); outline: 3px solid color-mix(in srgb, var(--app-accent) 12%, transparent); }
.review-external-create__grid small { color: var(--app-muted); font-size: 9px; line-height: 1.5; }
.review-external-create__error { margin: 0; color: #ac3c37; font-size: 11px; font-weight: 700; }
.review-external-create__actions { display: flex; justify-content: flex-end; gap: 8px; padding-top: 4px; }
.review-external-create__actions button { min-height: 40px; padding: 8px 13px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 11px; font-weight: 900; }
.review-external-create__actions button[type="submit"] { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.review-external-create__actions button:disabled { cursor: not-allowed; opacity: .55; }

.review-dashboard__loading {
  display: grid;
  gap: 14px;
}

.review-dashboard__controls {
  display: grid;
  gap: 12px;
  padding: 16px 0 18px;
  border-bottom: 1px solid var(--app-line);
}

.review-dashboard__control-row {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) auto auto;
  align-items: end;
  gap: 10px;
}

.review-dashboard__search {
  display: flex;
  min-height: 44px;
  align-items: center;
  gap: 8px;
  padding-left: 12px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  color: var(--app-muted);
  background: #fff;
}

.review-dashboard__search:focus-within {
  border-color: var(--app-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--app-accent) 12%, transparent);
}

.review-dashboard__search input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  color: var(--app-ink);
  background: transparent;
  font: inherit;
  font-size: 13px;
}

.review-dashboard__search button,
.review-dashboard__filter-toggle,
.review-dashboard__queue-heading button,
.review-dashboard__pagination button {
  min-height: 42px;
  padding: 8px 13px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}

.review-dashboard__search button {
  min-height: 36px;
  margin-right: 4px;
  padding-inline: 12px;
  border-color: transparent;
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.review-dashboard__filter-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
}

.review-dashboard__filter-toggle.is-active {
  border-color: color-mix(in srgb, var(--app-accent) 42%, var(--app-line));
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.review-dashboard__filter-toggle > span {
  display: grid;
  min-width: 19px;
  height: 19px;
  place-items: center;
  border-radius: 999px;
  color: #fff;
  background: var(--app-accent);
  font-size: 10px;
}

.review-dashboard__sort {
  display: grid;
  gap: 5px;
}

.review-dashboard__sort > span,
.review-dashboard__advanced-filters label > span {
  color: var(--app-muted);
  font-size: 10px;
  font-weight: 800;
}

.review-dashboard__sort select,
.review-dashboard__advanced-filters select,
.review-dashboard__advanced-filters input {
  min-height: 42px;
  padding: 8px 11px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  font: inherit;
  font-size: 12px;
}

.review-dashboard__quick-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.review-dashboard__quick-filters button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  color: var(--app-ink-soft);
  background: #f5f7fa;
  cursor: pointer;
  font-size: 11px;
  font-weight: 800;
}

.review-dashboard__quick-filters button strong {
  color: var(--app-muted);
  font-size: 10px;
}

.review-dashboard__quick-filters button.is-active {
  border-color: color-mix(in srgb, var(--app-accent) 28%, transparent);
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.review-dashboard__quick-filters button.is-active strong {
  color: var(--app-accent-deep);
}

.review-dashboard__advanced-filters {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
  background: #f8fafc;
}

.review-dashboard__advanced-filters label {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.review-dashboard__active-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.review-dashboard__active-filters > span {
  margin-right: 2px;
  color: var(--app-muted);
  font-size: 10px;
  font-weight: 800;
}

.review-dashboard__active-filters button {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  gap: 5px;
  padding: 5px 9px;
  border: 1px solid var(--app-line);
  border-radius: 999px;
  color: var(--app-ink-soft);
  background: #fff;
  cursor: pointer;
  font-size: 10px;
  font-weight: 800;
}

.review-dashboard__active-filters .review-dashboard__clear {
  border-color: transparent;
  color: var(--app-accent-deep);
  background: transparent;
}

.review-dashboard__reset-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  padding: 0;
  border: 0;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.review-dashboard__inline-error {
  margin: 14px 0 0;
  color: #ac3c37;
  font-size: 12px;
}

.review-dashboard__queue {
  padding-top: 18px;
}

.review-dashboard__queue-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 8px;
}

.review-dashboard__queue-heading > div {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.review-dashboard__queue-heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 20px;
  font-weight: 650;
}

.review-dashboard__queue-heading span {
  color: var(--app-muted);
  font-size: 11px;
}

.review-dashboard__queue-heading button:disabled,
.review-dashboard__pagination button:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.review-dashboard__list {
  border-top: 1px solid var(--app-line);
}

.review-dashboard__case {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(170px, auto) 28px;
  align-items: center;
  gap: 20px;
  min-height: 116px;
  padding: 17px 12px;
  border-bottom: 1px solid var(--app-line);
  background: #fff;
  cursor: pointer;
  transition: background 120ms ease, transform 120ms ease;
}

.review-dashboard__case:hover {
  background: #fbfcfe;
}

.review-dashboard__case:focus-visible {
  z-index: 1;
  outline: 3px solid color-mix(in srgb, var(--app-accent) 65%, white);
  outline-offset: -3px;
}

.review-dashboard__case-main {
  display: grid;
  min-width: 0;
  gap: 8px;
}

.review-dashboard__case-title {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 10px;
}

.review-dashboard__case-title strong {
  flex: 0 0 auto;
  color: var(--app-ink);
  font-size: 13px;
  font-weight: 900;
}

.review-dashboard__case-title span {
  overflow: hidden;
  color: var(--app-ink-soft);
  font-size: 14px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-dashboard__badges,
.review-dashboard__case-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.review-dashboard__badges > span {
  padding: 4px 7px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 900;
}

.review-dashboard__source {
  color: #315b7d;
  background: #edf5fb;
}

.review-dashboard__source[data-source="EXTERNAL"] {
  color: #74562d;
  background: #f8f1e6;
}

.review-dashboard__status {
  color: var(--app-ink-soft);
  background: #f1f3f6;
}

.review-dashboard__risk.is-high {
  color: #9f342e;
  background: #fdecea;
}

.review-dashboard__risk.is-medium {
  color: #86631d;
  background: #fff4d8;
}

.review-dashboard__risk.is-low {
  color: #3e6b50;
  background: #edf7f0;
}

.review-dashboard__risk.is-neutral {
  color: var(--app-muted);
  background: #f1f3f6;
}

.review-dashboard__case-meta {
  gap: 0;
  color: var(--app-muted);
  font-size: 10px;
}

.review-dashboard__case-meta span + span::before {
  content: '·';
  margin: 0 7px;
  color: #bdc4cc;
}

.review-dashboard__case-side {
  display: grid;
  gap: 7px;
  justify-items: end;
  text-align: right;
}

.review-dashboard__deadline {
  display: grid;
  gap: 2px;
}

.review-dashboard__deadline strong {
  color: var(--app-ink-soft);
  font-size: 11px;
}

.review-dashboard__deadline span,
.review-dashboard__case-side small {
  color: var(--app-muted);
  font-size: 9px;
}

.review-dashboard__case-caret {
  color: #b6bec8;
}

.review-dashboard__empty {
  display: grid;
  justify-items: center;
  gap: 6px;
  padding: 54px 18px;
  border-top: 1px solid var(--app-line);
  border-bottom: 1px solid var(--app-line);
  text-align: center;
}

.review-dashboard__empty strong {
  color: var(--app-ink);
  font-size: 14px;
}

.review-dashboard__empty p {
  margin: 0;
  color: var(--app-muted);
  font-size: 11px;
}

.review-dashboard__pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 14px;
}

.review-dashboard__pagination span {
  color: var(--app-muted);
  font-size: 11px;
}

@media (max-width: 1080px) {
  .review-dashboard__advanced-filters {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 780px) {
  .review-dashboard {
    padding-inline: 18px;
  }

  .review-dashboard__control-row {
    grid-template-columns: 1fr auto;
  }

  .review-dashboard__search {
    grid-column: 1 / -1;
  }

  .review-dashboard__advanced-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .review-dashboard__case {
    grid-template-columns: minmax(0, 1fr) 24px;
    gap: 12px;
  }

  .review-dashboard__case-side {
    grid-column: 1 / -1;
    grid-row: 2;
    justify-items: start;
    text-align: left;
  }

  .review-dashboard__case-caret {
    grid-column: 2;
    grid-row: 1;
  }
}

@media (max-width: 560px) {
  .review-dashboard {
    padding-inline: 14px;
  }

  .review-dashboard__advanced-filters {
    grid-template-columns: 1fr;
  }

  .review-dashboard__case-title {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .review-dashboard__case-title span {
    white-space: normal;
  }
}
</style>
