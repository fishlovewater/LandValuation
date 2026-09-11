<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CaseTable from '../../../components/common/CaseTable.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { reviewApi, safeReviewErrorMessage } from '../review.api'
import { mapWorkbenchCase, mapWorkbenchSummary, riskLevelLabel, statusGroupLabel } from '../review.mappers'
import type { ReviewQueueItemModel, ReviewSummaryModel } from '../review.types'

const route = useRoute()
const router = useRouter()
const summary = ref<ReviewSummaryModel | null>(null)
const cases = ref<ReviewQueueItemModel[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
let loadSerial = 0
let activeController: AbortController | null = null

const page = computed(() => positiveQuery('page', 1))
const pageSize = computed(() => positiveQuery('pageSize', 20))
const sortBy = computed(() => stringQuery('sortBy', ''))
const sortDirection = computed<'asc' | 'desc'>(() => (stringQuery('sortDirection', 'desc') === 'asc' ? 'asc' : 'desc'))
const filters = computed(() => ({
  status: stringQuery('status', ''),
  riskLevel: stringQuery('riskLevel', ''),
}))

const queueRows = computed(() => {
  const rows = [...cases.value]
  const key = sortBy.value
  if (!key) return rows
  const direction = sortDirection.value === 'asc' ? 1 : -1
  return rows.sort((left, right) => {
    const leftValue = key === 'caseNo' ? left.caseNo : key === 'name' ? left.name : key === 'status' ? left.reviewStatusLabel : left.updatedAt
    const rightValue = key === 'caseNo' ? right.caseNo : key === 'name' ? right.name : key === 'status' ? right.reviewStatusLabel : right.updatedAt
    return leftValue.localeCompare(rightValue, 'zh-Hant') * direction
  })
})

const statusKpis = computed(() =>
  Object.entries(summary.value?.statusCounts ?? {})
    .map(([code, count]) => ({ code, label: statusGroupLabel(code), count }))
    .sort((left, right) => left.label.localeCompare(right.label, 'zh-Hant')),
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
  const allowed = new Set(['q', 'status', 'riskLevel', 'statusGroup', 'sortBy', 'sortDirection', 'page', 'pageSize'])
  return Object.fromEntries(Object.entries(query).filter(([key, value]) => allowed.has(key) && value))
}

function currentQueueQuery(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(route.query)
      .map(([key, value]) => [key, Array.isArray(value) ? value[0] ?? '' : value ?? ''])
      .filter(([key]) => key !== 'finding'),
  )
}

function updateQuery(query: Record<string, string>): void {
  const merged = currentQueueQuery()
  for (const [key, value] of Object.entries(query)) {
    if (value) merged[key] = value
    else delete merged[key]
  }
  void router.replace({ query: normalizedQueueQuery(merged) }).then(loadData)
}

function applyKpi(kind: 'status' | 'risk' | 'finding', statusCode = 'in_progress'): void {
  const next = normalizedQueueQuery({
    ...Object.fromEntries(Object.entries(route.query).map(([key, value]) => [key, Array.isArray(value) ? value[0] ?? '' : value ?? ''])),
  })
  delete next.status
  delete next.riskLevel
  delete next.statusGroup
  if (kind === 'status') next.statusGroup = statusCode
  if (kind === 'risk') next.riskLevel = 'HIGH'
  if (kind === 'finding') next.statusGroup = 'needs_input'
  updateQuery(next)
}

function openCase(row: { reviewId?: string }): void {
  if (!row.reviewId) return
  const queueQuery = normalizedQueueQuery({
    ...Object.fromEntries(Object.entries(route.query).map(([key, value]) => [key, Array.isArray(value) ? value[0] ?? '' : value ?? ''])),
  })
  void router.push({ name: 'review-workbench', params: { reviewId: row.reviewId }, query: queueQuery })
}

onMounted(loadData)

onBeforeUnmount(() => {
  activeController?.abort()
})
</script>

<template>
  <section class="review-dashboard" data-testid="review-dashboard">
    <PageHeader
      eyebrow="案件審查"
      title="審查工作台"
      description="依案件風險、檢核結果與來源文件接續審查工作。"
    >
      <template #actions>
        <button class="review-dashboard__refresh" type="button" data-testid="refresh-review-queue" @click="loadData">
          重新整理
        </button>
      </template>
    </PageHeader>

    <div v-if="loading && !summary" class="review-dashboard__loading">
      <LoadingSkeleton :rows="3" label="審查摘要載入中" />
    </div>
    <ErrorState v-else-if="error && !summary" :message="error" @retry="loadData" />
    <template v-else>
      <section class="review-dashboard__kpis" aria-label="審查摘要">
        <button
          v-for="item in statusKpis"
          :key="item.code"
          v-liquid-glass
          data-lg
          class="review-dashboard__kpi lg"
          :data-testid="`kpi-${item.code.toLowerCase().replaceAll('_', '-')}`"
          :data-kpi-status="item.code"
          type="button"
          @click="applyKpi('status', item.code)"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.count }}</strong>
          <small>案件</small>
        </button>
        <button v-liquid-glass data-lg class="review-dashboard__kpi review-dashboard__kpi--risk lg" data-testid="kpi-high-risk" type="button" @click="applyKpi('risk')">
          <span>高風險案件</span>
          <strong>{{ summary?.highRiskCount ?? 0 }}</strong>
          <small>{{ riskLevelLabel('HIGH') }}</small>
        </button>
        <button v-liquid-glass data-lg class="review-dashboard__kpi lg" data-testid="kpi-open-findings" type="button" @click="applyKpi('finding')">
          <span>待處理疑點</span>
          <strong>{{ summary?.openFindingCount ?? 0 }}</strong>
          <small>需審查</small>
        </button>
        <div v-liquid-glass data-lg class="review-dashboard__metric lg">
          <span>待補資料</span>
          <strong>{{ summary?.missingItemCount ?? 0 }}</strong>
          <small>案件</small>
        </div>
      </section>

      <p v-if="error" class="review-dashboard__inline-error" role="alert">{{ error }}</p>

      <section v-liquid-glass data-lg class="review-dashboard__queue lg" aria-labelledby="review-queue-title">
        <div class="review-dashboard__queue-heading">
          <div>
            <p class="review-dashboard__eyebrow">待辦案件</p>
            <h2 id="review-queue-title">案件佇列</h2>
          </div>
          <span class="review-dashboard__queue-count">共 {{ total }} 件</span>
        </div>
        <CaseTable
          :cases="queueRows"
          :total="total"
          :page="page"
          :page-size="pageSize"
          :sort-by="sortBy"
          :sort-direction="sortDirection"
          :filters="filters"
          :filter-options="{
            status: [
              { value: 'READY_FOR_REVIEW', label: '待審查' },
              { value: 'REVIEW_REQUIRED', label: '需審查' },
              { value: 'RETURNED_FOR_REVISION', label: '退回補正' },
              { value: 'REVIEW_COMPLETED', label: '審查完成' },
            ],
            riskLevel: [
              { value: 'LOW', label: '低風險' },
              { value: 'MEDIUM', label: '中風險' },
              { value: 'HIGH', label: '高風險' },
              { value: 'CRITICAL', label: '極高風險' },
            ],
          }"
          row-test-id-prefix="review-case-row"
          :loading="loading"
          :error="error"
          empty-title="目前沒有符合條件的審查案件"
          empty-description="調整篩選條件，或等待新的送審案件進入佇列。"
          @query-change="updateQuery"
          @retry="loadData"
          @select="openCase"
        />
      </section>
    </template>
  </section>
</template>

<style scoped>
.review-dashboard { padding: 0 28px 34px; }
.review-dashboard__refresh { min-height: 42px; padding: 8px 15px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.review-dashboard__refresh:hover { border-color: var(--app-accent); color: var(--app-accent-deep); }
.review-dashboard__loading { display: grid; gap: 14px; }
.review-dashboard__kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.review-dashboard__kpi,
.review-dashboard__metric { display: grid; min-height: 118px; align-content: space-between; gap: 4px; padding: 16px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); color: var(--app-ink-soft); background: var(--app-paper-strong); text-align: left; }
.review-dashboard__kpi { cursor: pointer; }
.review-dashboard__kpi:hover { border-color: var(--app-accent); background: #fffaf6; }
.review-dashboard__kpi--risk { border-color: #e7c1bb; background: #fff7f4; }
.review-dashboard__kpi span,
.review-dashboard__metric span { font-size: 12px; font-weight: 800; }
.review-dashboard__kpi strong,
.review-dashboard__metric strong { color: var(--app-ink); font-family: var(--app-font-display); font-size: 34px; font-weight: 600; line-height: 1; }
.review-dashboard__kpi small,
.review-dashboard__metric small { color: var(--app-muted); font-size: 11px; }
.review-dashboard__inline-error { margin: 16px 0 0; color: #ac3c37; font-size: 13px; }
.review-dashboard__queue { margin-top: 28px; padding: 18px; border: 1px solid rgba(255,255,255,.72); border-radius: var(--app-radius-md); background: rgba(255,255,255,.68); box-shadow: var(--app-shadow-soft); }
.review-dashboard__queue-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.review-dashboard__eyebrow { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 10px; font-weight: 900; letter-spacing: .15em; }
.review-dashboard__queue-heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; }
.review-dashboard__queue-count { color: var(--app-muted); font-size: 12px; }

@media (max-width: 980px) {
  .review-dashboard { padding-inline: 18px; }
  .review-dashboard__kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 640px) {
  .review-dashboard { padding-inline: 14px; }
  .review-dashboard__kpis { grid-template-columns: 1fr 1fr; }
  .review-dashboard__queue-heading { align-items: flex-start; flex-direction: column; }
}
</style>
