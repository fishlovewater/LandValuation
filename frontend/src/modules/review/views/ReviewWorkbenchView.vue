<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ConfirmDialog from '../../../components/common/ConfirmDialog.vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import GlassCard from '../../../components/glass/GlassCard.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { useAuthStore } from '../../../stores/auth.store'
import EvidenceViewer from '../components/EvidenceViewer.vue'
import FindingPanel from '../components/FindingPanel.vue'
import ReviewActionBar from '../components/ReviewActionBar.vue'
import { reviewApi, safeReviewErrorMessage } from '../review.api'
import {
  latestGeneratedReport,
  latestRunId as latestRunIdForDetail,
  mapWorkbenchDetail,
  selectEvidenceDocument,
} from '../review.mappers'
import type {
  FindingTriageDecision,
  GeneratedReportDto,
  ReviewDetailModel,
  ReviewFindingModel,
} from '../review.types'

type DrawerName = 'left' | 'right' | null
type ConfirmationName = 'finalize' | 'return' | null

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const detail = ref<ReviewDetailModel | null>(null)
const loading = ref(false)
const mutating = ref(false)
const error = ref('')
const actionError = ref('')
const selectedFindingId = ref('')
const generatedReport = ref<GeneratedReportDto | null>(null)
const drawer = ref<DrawerName>(null)
const confirmation = ref<ConfirmationName>(null)
let loadSerial = 0
const drawerTrigger = ref<HTMLElement | null>(null)

const reviewId = computed(() => {
  const param = route.params.reviewId
  return typeof param === 'string' ? param : ''
})
const canDecide = computed(() => authStore.permissions.includes('review.decide'))
const canExecute = computed(() => authStore.permissions.includes('review.execute'))
const selectedFinding = computed<ReviewFindingModel | null>(
  () => detail.value?.findings.find((finding) => finding.findingId === selectedFindingId.value) ?? null,
)
const selectedDocument = computed(() => {
  const documentId = selectedFinding.value?.documentId
  return detail.value ? selectEvidenceDocument(detail.value.documents, documentId) : null
})
const selectedDecision = computed(() => {
  const findingId = selectedFinding.value?.findingId
  return detail.value?.decisions.find((decision) => decision.findingId === findingId) ?? null
})
const latestRun = computed(() => {
  const currentDetail = detail.value
  if (!currentDetail) return null
  return currentDetail.runs.find((run) => run.validationRunId === currentDetail.latestValidationRunId)
    ?? currentDetail.runs.reduce<typeof currentDetail.runs[number] | null>(
      (latest, run) => (!latest || (run.runNo ?? 0) > (latest.runNo ?? 0) ? run : latest),
      null,
    )
})
const unresolvedCount = computed(() => detail.value?.unresolvedFindingCount ?? 0)
const latestReport = computed(
  () => generatedReport.value ?? detail.value?.reportDocument ?? (detail.value ? latestGeneratedReport(detail.value.generatedReports) : null),
)
const canTriage = computed(() => Boolean(
  canDecide.value
    && ['REVIEW_REQUIRED', 'EXPERT_REVIEW'].includes(detail.value?.reviewStatusCode ?? '')
    && selectedFinding.value?.statusCode === 'OPEN',
))
const triageReadonlyReason = computed(() => {
  if (!canDecide.value) return '目前帳號沒有審查決定權限，僅能閱讀。'
  if (!['REVIEW_REQUIRED', 'EXPERT_REVIEW'].includes(detail.value?.reviewStatusCode ?? '')) {
    return '案件目前尚未進入可判定疑點的審查狀態。'
  }
  if (selectedFinding.value?.statusCode !== 'OPEN') return '目前案件狀態或疑點狀態不允許再次判定。'
  return '目前無法判定此疑點。'
})
const completionBlockers = computed(() => {
  if (!detail.value) return ['尚未載入案件資料。']
  const blockers: string[] = []
  if (latestRun.value?.runStatusCode !== 'COMPLETED') blockers.push('最新一次智慧審查尚未完成。')
  const openMissingCount = detail.value.missingItems.filter((item) => item.status === 'OPEN').length
  if (openMissingCount) blockers.push(`仍有 ${openMissingCount} 項缺件。`)
  const confirmedCount = detail.value.findings.filter((finding) => finding.statusCode === 'CONFIRMED_ISSUE').length
  const openFindingCount = detail.value.findings.filter((finding) => ['OPEN', 'REQUIRES_SUPPLEMENT'].includes(finding.statusCode)).length
  const expertCount = detail.value.findings.filter((finding) => finding.statusCode === 'EXPERT_REVIEW').length
  if (openFindingCount) blockers.push(`仍有 ${openFindingCount} 項疑點未判定。`)
  if (confirmedCount) blockers.push(`仍有 ${confirmedCount} 項疑點待修正。`)
  if (expertCount) blockers.push(`仍有 ${expertCount} 項專業覆核。`)
  const activeRequests = detail.value.correctionRequests.filter((request) => request.status !== 'RECHECKED').length
  const unevaluatedItems = detail.value.correctionRequests
    .flatMap((request) => request.items)
    .filter((item) => item.recheck_outcome === 'NOT_EVALUATED').length
  if (activeRequests || unevaluatedItems) blockers.push('仍有修正通知尚未完成新版重檢。')
  return blockers
})
const canFinalize = computed(() => Boolean(canDecide.value && completionBlockers.value.length === 0 && detail.value?.reviewStatusCode !== 'REVIEW_COMPLETED'))
const finalizeActionReason = computed(() => completionBlockers.value[0] ?? '完成審查前會顯示未處理疑點數量。')
const startableReviewStatuses = new Set(['RECEIVED', 'PREPROCESSING', 'PENDING_MATERIALS', 'READY_FOR_REVIEW'])
const showStartReview = computed(() => Boolean(
  detail.value
    && !detail.value.latestValidationRunId
    && startableReviewStatuses.has(detail.value.reviewStatusCode),
))
const canStartReview = computed(() => Boolean(showStartReview.value && canExecute.value && !mutating.value))
const canGenerateReport = computed(() => Boolean(
  canExecute.value
    && detail.value?.reviewStatusCode === 'REVIEW_COMPLETED'
    && latestRun.value?.runStatusCode === 'COMPLETED'
    && latestRunIdForDetail(detail.value) === latestRun.value?.validationRunId,
))
const reportActionReason = computed(() => canGenerateReport.value ? '' : '案件完成且最新檢核完成後，才可產生審查報告。')

function stringQuery(name: string, fallback = ''): string {
  const value = route.query[name]
  return typeof value === 'string' ? value : fallback
}

function queueParams() {
  const page = Math.max(1, Number.parseInt(stringQuery('page', '1'), 10) || 1)
  const pageSize = Math.max(1, Number.parseInt(stringQuery('pageSize', '20'), 10) || 20)
  return {
    q: stringQuery('q') || undefined,
    status: stringQuery('status') || undefined,
    riskLevel: stringQuery('riskLevel') || undefined,
    statusGroup: stringQuery('statusGroup') || undefined,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  }
}

function queueQuery(): Record<string, string> {
  const names = ['q', 'status', 'riskLevel', 'statusGroup', 'sortBy', 'sortDirection', 'page', 'pageSize']
  return Object.fromEntries(
    names
      .map((name) => [name, stringQuery(name)] as const)
      .filter(([, value]) => value),
  )
}

async function loadDetail(): Promise<void> {
  if (!reviewId.value) return
  const serial = ++loadSerial
  loading.value = true
  error.value = ''
  try {
    const dto = await reviewApi.getCase(reviewId.value)
    if (serial !== loadSerial) return
    detail.value = mapWorkbenchDetail(dto)
    if (!detail.value.findings.some((finding) => finding.findingId === selectedFindingId.value)) {
      selectedFindingId.value = detail.value.findings[0]?.findingId ?? ''
    }
  } catch (caught: unknown) {
    if (serial === loadSerial) error.value = safeReviewErrorMessage(caught)
  } finally {
    if (serial === loadSerial) loading.value = false
  }
}

async function refreshAfterMutation(): Promise<void> {
  if (!reviewId.value) return
  const [summaryDto, queueDto, detailDto] = await Promise.all([
    reviewApi.getSummary(),
    reviewApi.listCases(queueParams()),
    reviewApi.getCase(reviewId.value),
  ])
  void summaryDto
  void queueDto
  detail.value = mapWorkbenchDetail(detailDto)
  if (!detail.value.findings.some((finding) => finding.findingId === selectedFindingId.value)) {
    selectedFindingId.value = detail.value.findings[0]?.findingId ?? ''
  }
}

async function saveFindingDecision(value: {
  findingId: string
  decision: FindingTriageDecision
  reason: string
}): Promise<void> {
  if (!reviewId.value || !canTriage.value || mutating.value) return
  mutating.value = true
  actionError.value = ''
  try {
    await reviewApi.triageFinding(value.findingId, {
      review_id: reviewId.value,
      decision: value.decision,
      reason: value.reason,
    })
    await refreshAfterMutation()
  } catch (caught: unknown) {
    actionError.value = safeReviewErrorMessage(caught)
  } finally {
    mutating.value = false
  }
}

function askFinalize(): void {
  if (!canFinalize.value || mutating.value) return
  confirmation.value = 'finalize'
}

async function startReview(): Promise<void> {
  if (!reviewId.value || !canStartReview.value) return
  mutating.value = true
  actionError.value = ''
  try {
    const preflight = await reviewApi.preflightCase(reviewId.value)
    if (preflight.outcome === 'BLOCKED') {
      await refreshAfterMutation()
      const missing = preflight.completeness.items
        .map((item) => item.item_name)
        .filter(Boolean)
      actionError.value = `開始審查暫停：${missing.join('、') || '仍有缺件或完整性問題'}。`
      return
    }
    const started = await reviewApi.startCase(reviewId.value)
    if (started.outcome !== 'COMPLETED' || started.run?.run_status !== 'COMPLETED') {
      throw new Error('review start did not return a completed run')
    }
    await refreshAfterMutation()
  } catch (caught: unknown) {
    actionError.value = safeReviewErrorMessage(caught)
  } finally {
    mutating.value = false
  }
}

function askReturn(): void {
  confirmation.value = 'return'
}

async function confirmAction(): Promise<void> {
  const requested = confirmation.value
  if (!requested || mutating.value) return
  confirmation.value = null
  if (requested === 'return') {
    actionError.value = '目前驗證的 Demo API 未提供案件退回端點；此操作未送出請求。'
    return
  }
  if (!reviewId.value || !canFinalize.value) return
  mutating.value = true
  actionError.value = ''
  try {
    await reviewApi.completeReview(reviewId.value, { reason: '依審查工作台確認結果完成審查。' })
    await refreshAfterMutation()
  } catch (caught: unknown) {
    actionError.value = safeReviewErrorMessage(caught)
  } finally {
    mutating.value = false
  }
}

async function generateReport(): Promise<void> {
  const runId = latestRunIdForDetail(detail.value)
  if (!runId || !canGenerateReport.value || mutating.value) return
  mutating.value = true
  actionError.value = ''
  try {
    generatedReport.value = await reviewApi.generateReportPdf(runId)
    await refreshAfterMutation()
  } catch (caught: unknown) {
    actionError.value = safeReviewErrorMessage(caught)
  } finally {
    mutating.value = false
  }
}

function selectFinding(findingId: string): void {
  selectedFindingId.value = findingId
  closeDrawer()
  void router.replace({ query: { ...route.query, finding: findingId } })
}

function openResult(): void {
  if (!reviewId.value) return
  void router.push({ name: 'review-result', params: { reviewId: reviewId.value }, query: { runId: latestRun.value?.validationRunId ?? '' } })
}

function backToQueue(): void {
  void router.push({ name: 'review-dashboard', query: queueQuery() })
}

function openDrawer(name: Exclude<DrawerName, null>, event?: Event): void {
  if (drawer.value === name) {
    closeDrawer()
    return
  }
  drawerTrigger.value = event?.currentTarget instanceof HTMLElement
    ? event.currentTarget
    : document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
  document.addEventListener('keydown', handleDrawerKeydown, true)
  drawer.value = name
  void nextTick(() => {
    const panel = document.getElementById(name === 'left' ? 'review-context-drawer' : 'review-finding-drawer')
    const target = panel?.querySelector<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
    ;(target ?? panel)?.focus()
  })
}

function closeDrawer(): void {
  if (!drawer.value) return
  drawer.value = null
  document.removeEventListener('keydown', handleDrawerKeydown, true)
  const restore = drawerTrigger.value
  drawerTrigger.value = null
  void nextTick(() => {
    if (restore?.isConnected) restore.focus()
  })
}

function handleDrawerKeydown(event: KeyboardEvent): void {
  if (!drawer.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDrawer()
    return
  }
  if (event.key !== 'Tab') return
  const panel = document.getElementById(drawer.value === 'left' ? 'review-context-drawer' : 'review-finding-drawer')
  if (!panel) return
  const focusables = Array.from(panel.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
  if (!focusables.length) {
    event.preventDefault()
    panel.focus()
    return
  }
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => route.query.finding,
  (value) => {
    if (typeof value === 'string' && detail.value?.findings.some((finding) => finding.findingId === value)) {
      selectedFindingId.value = value
    }
  },
)

watch(reviewId, () => {
  selectedFindingId.value = ''
  generatedReport.value = null
  void loadDetail()
})

onMounted(() => {
  const finding = stringQuery('finding')
  if (finding) selectedFindingId.value = finding
  void loadDetail()
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleDrawerKeydown, true)
})
</script>

<template>
  <section class="review-workbench" data-testid="review-workbench">
    <PageHeader
      eyebrow="CASE REVIEW"
      :title="detail?.caseTitle ?? '案件審查'"
      :description="detail ? `${detail.caseNo} · ${detail.districtCode} · 評價基準日 ${detail.valuationBaseDate}` : '讀取審查案件與證據。'"
    >
      <template #actions>
        <button type="button" class="review-workbench__back" data-testid="review-back-to-queue" @click="backToQueue">
          返回案件佇列
        </button>
      </template>
    </PageHeader>

    <div v-if="!reviewId" class="review-workbench__empty">
      <EmptyState title="尚未選取審查案件" description="請先從審查工作台選取一筆案件。">
        <template #action><button type="button" @click="backToQueue">前往案件佇列</button></template>
      </EmptyState>
    </div>
    <template v-else>
      <LoadingSkeleton v-if="loading && !detail" :rows="7" label="審查案件載入中" />
      <ErrorState v-else-if="error && !detail" :message="error" @retry="loadDetail" />
      <template v-else-if="detail">
        <div v-if="showStartReview" v-liquid-glass data-lg class="review-workbench__start-panel lg" data-testid="review-start-panel">
          <div>
            <strong>尚未開始智慧審查</strong>
            <p>先執行完整性檢查與伺服器規則檢核，完成後才能處理疑點與完成審查。</p>
          </div>
          <button
            type="button"
            data-testid="start-review"
            :disabled="!canStartReview"
            @click="startReview"
          >
            {{ mutating ? '審查啟動中…' : '開始審查' }}
          </button>
        </div>
        <ReviewActionBar
          :can-decide="canDecide"
          :can-finalize="canFinalize"
          :can-execute="canExecute"
          :can-generate-report="canGenerateReport"
          :review-status-code="detail.reviewStatusCode"
          :unresolved-finding-count="unresolvedCount"
          :latest-run-id="latestRun?.validationRunId"
          :report-document="latestReport"
          :report-action-reason="reportActionReason"
          :finalize-action-reason="finalizeActionReason"
          :busy="mutating"
          @finalize-request="askFinalize"
          @return-request="askReturn"
          @generate-report="generateReport"
          @open-result="openResult"
        />
        <p v-if="error || actionError" class="review-workbench__error" role="alert">{{ error || actionError }}</p>

        <div class="review-workbench__mobile-tools" aria-label="輔助面板">
          <button type="button" data-testid="open-review-context" aria-controls="review-context-drawer" :aria-expanded="drawer === 'left'" @click="openDrawer('left', $event)">案件脈絡</button>
          <button type="button" data-testid="open-review-finding" aria-controls="review-finding-drawer" :aria-expanded="drawer === 'right'" @click="openDrawer('right', $event)">疑點內容</button>
        </div>

        <button
          v-if="drawer"
          type="button"
          class="review-workbench__drawer-backdrop"
          data-testid="review-drawer-backdrop"
          :aria-label="drawer === 'left' ? '關閉案件脈絡' : '關閉疑點內容'"
          @click="closeDrawer"
        />

        <div class="review-workbench__layout">
          <aside
            id="review-context-drawer"
            v-liquid-glass
            data-lg
            class="review-workbench__left lg"
            :class="{ 'review-workbench__left--open': drawer === 'left' }"
            :role="drawer === 'left' ? 'dialog' : undefined"
            :aria-modal="drawer === 'left' ? 'true' : undefined"
            aria-labelledby="review-context-title"
            aria-label="案件脈絡"
          >
            <div class="review-workbench__panel-heading">
              <div><p>CASE CONTEXT</p><h2 id="review-context-title">案件脈絡</h2></div>
              <button v-if="drawer === 'left'" type="button" aria-label="關閉案件脈絡" @click="closeDrawer">×</button>
            </div>
            <dl class="review-workbench__case-facts">
              <div><dt>案件編號</dt><dd>{{ detail.caseNo }}</dd></div>
              <div><dt>案件狀態</dt><dd>{{ detail.caseStatusLabel }}</dd></div>
              <div><dt>審查狀態</dt><dd>{{ detail.reviewStatusLabel }}</dd></div>
              <div><dt>風險</dt><dd>{{ detail.riskLevelLabel }}</dd></div>
            </dl>
            <section class="review-workbench__context-section">
              <h3>文件（{{ detail.documents.length }}）</h3>
              <ul v-if="detail.documents.length" class="review-workbench__plain-list">
                <li v-for="document in detail.documents" :key="document.documentId">
                  <span>{{ document.filename }}</span><small>第 {{ document.versionNo }} 版</small>
                </li>
              </ul>
              <p v-else class="review-workbench__muted">目前沒有可預覽文件。</p>
            </section>
            <section class="review-workbench__context-section">
              <h3>檢核執行（{{ detail.runs.length }}）</h3>
              <ul v-if="detail.runs.length" class="review-workbench__plain-list">
                <li v-for="run in detail.runs" :key="run.validationRunId">
                  <span>第 {{ run.runNo ?? '—' }} 次：{{ run.runStatusLabel }}</span>
                  <small>{{ run.failedCount }} 個阻擋項目</small>
                </li>
              </ul>
              <p v-else class="review-workbench__muted">目前沒有檢核執行紀錄。</p>
            </section>
            <section class="review-workbench__context-section">
              <h3>疑點（{{ detail.findings.length }}）</h3>
              <ul class="review-workbench__finding-list">
                <li v-for="finding in detail.findings" :key="finding.findingId">
                  <button
                    type="button"
                    :data-testid="`finding-select-${finding.findingId}`"
                    :class="{ 'is-selected': finding.findingId === selectedFindingId }"
                    @click="selectFinding(finding.findingId)"
                  >
                    <span>{{ finding.title }}</span>
                    <small>{{ finding.severityLabel }} · {{ finding.statusLabel }}</small>
                  </button>
                </li>
              </ul>
              <p v-if="!detail.findings.length" class="review-workbench__muted">目前沒有疑點。</p>
            </section>
            <section class="review-workbench__context-section review-workbench__context-summary">
              <h3>補正與決定</h3>
              <p>補正通知 {{ detail.correctionRequests.length }} 件 · 已保存決定 {{ detail.decisions.length }} 筆</p>
            </section>
          </aside>

          <main class="review-workbench__center" aria-label="主要證據">
            <EvidenceViewer
              :review-id="detail.reviewId"
              :document="selectedDocument"
              :page-number="selectedFinding?.pageNumber"
              :field-path="selectedFinding?.fieldPath"
            />
          </main>

          <aside
            id="review-finding-drawer"
            class="review-workbench__right"
            :class="{ 'review-workbench__right--open': drawer === 'right' }"
            :role="drawer === 'right' ? 'dialog' : undefined"
            :aria-modal="drawer === 'right' ? 'true' : undefined"
            aria-label="疑點內容"
          >
            <button v-if="drawer === 'right'" type="button" class="review-workbench__drawer-close" aria-label="關閉疑點內容" @click="closeDrawer">×</button>
            <GlassCard class="review-workbench__finding-frame" data-testid="right-finding-frame">
              <FindingPanel
                :finding="selectedFinding"
                :decision="selectedDecision"
                :can-decide="canDecide"
                :can-triage="canTriage"
                :readonly-reason="triageReadonlyReason"
                :saving="mutating"
                @save="saveFindingDecision"
              />
            </GlassCard>
          </aside>
        </div>
      </template>
    </template>

    <ConfirmDialog
      :open="confirmation === 'finalize'"
      title="完成審查確認"
      :message="`目前有 ${unresolvedCount} 個尚未處理的疑點。伺服器會再次檢查案件狀態，確定要送出完成審查嗎？`"
      confirm-label="完成審查"
      :busy="mutating"
      @cancel="confirmation = null"
      @close="confirmation = null"
      @confirm="confirmAction"
    />
  </section>
</template>

<style scoped>
.review-workbench { padding: 0 28px 34px; }
.review-workbench__start-panel { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-top: 16px; padding: 16px 18px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fff9f3; }
.review-workbench__start-panel strong { color: var(--app-ink); font-size: 14px; }
.review-workbench__start-panel p { margin: 5px 0 0; color: var(--app-muted); font-size: 12px; line-height: 1.6; }
.review-workbench__start-panel button { min-height: 44px; padding: 8px 16px; border: 1px solid var(--app-accent); border-radius: 8px; color: #fff8f2; background: var(--app-accent); cursor: pointer; font-weight: 800; white-space: nowrap; }
.review-workbench__start-panel button:disabled { cursor: not-allowed; opacity: .55; }
.review-workbench__back { min-height: 42px; padding: 8px 15px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.review-workbench__error { margin: 12px 0 0; color: #ac3c37; font-size: 13px; }
.review-workbench__layout { display: grid; grid-template-columns: minmax(190px, 230px) minmax(380px, 1fr) minmax(320px, 410px); align-items: start; gap: 16px; margin-top: 16px; }
.review-workbench__left { position: sticky; top: 20px; display: grid; max-height: calc(100vh - 40px); gap: 16px; overflow: auto; padding: 18px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #f7f8fb; }
.review-workbench__center { min-width: 0; }
.review-workbench__right { min-width: 0; }
.review-workbench__finding-frame { padding: 0; overflow: hidden; background: rgba(255, 255, 255, .82); }
.review-workbench__panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.review-workbench__panel-heading p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 9px; font-weight: 900; letter-spacing: .14em; }
.review-workbench__panel-heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 21px; }
.review-workbench__panel-heading button,
.review-workbench__drawer-close { display: grid; width: 42px; height: 42px; place-items: center; border: 0; border-radius: 8px; color: var(--app-ink-soft); background: transparent; cursor: pointer; font-size: 25px; }
.review-workbench__case-facts { display: grid; gap: 10px; margin: 0; }
.review-workbench__case-facts div { display: grid; gap: 3px; }
.review-workbench__case-facts dt { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.review-workbench__case-facts dd { margin: 0; color: var(--app-ink); font-size: 13px; font-weight: 800; overflow-wrap: anywhere; }
.review-workbench__context-section { display: grid; gap: 9px; padding-top: 14px; border-top: 1px solid var(--app-line); }
.review-workbench__context-section h3 { margin: 0; color: var(--app-ink); font-size: 13px; }
.review-workbench__plain-list,
.review-workbench__finding-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.review-workbench__plain-list li { display: grid; gap: 3px; color: var(--app-ink-soft); font-size: 11px; overflow-wrap: anywhere; }
.review-workbench__plain-list small { color: var(--app-muted); }
.review-workbench__finding-list button { display: grid; width: 100%; gap: 4px; padding: 10px; border: 1px solid transparent; border-radius: 8px; color: var(--app-ink-soft); background: transparent; cursor: pointer; text-align: left; }
.review-workbench__finding-list button:hover,
.review-workbench__finding-list button.is-selected { border-color: rgba(200, 91, 67, .2); color: var(--app-accent-deep); background: var(--app-accent-soft); }
.review-workbench__finding-list span { font-size: 12px; font-weight: 800; line-height: 1.4; }
.review-workbench__finding-list small { color: var(--app-muted); font-size: 10px; }
.review-workbench__context-summary p { margin: 0; color: var(--app-muted); font-size: 11px; line-height: 1.6; }
.review-workbench__muted { margin: 0; color: var(--app-muted); font-size: 11px; line-height: 1.6; }
.review-workbench__mobile-tools { display: none; }
.review-workbench__drawer-backdrop { position: fixed; z-index: 49; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(23, 34, 56, .24); cursor: default; }
.review-workbench__empty { max-width: 720px; margin: 28px auto; }

@media (max-width: 1180px) {
  .review-workbench { padding-inline: 18px; }
  .review-workbench__layout { grid-template-columns: minmax(175px, 210px) minmax(340px, 1fr); }
  .review-workbench__right { grid-column: 1 / -1; }
  .review-workbench__finding-frame { max-width: none; }
}

@media (max-width: 980px) {
  .review-workbench__mobile-tools { display: flex; gap: 8px; margin-top: 14px; }
  .review-workbench__mobile-tools button { min-height: 44px; padding: 8px 14px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
  .review-workbench__layout { display: block; margin-top: 12px; }
  .review-workbench__left,
  .review-workbench__right { display: none; }
  .review-workbench__left--open,
  .review-workbench__right--open { position: fixed; z-index: 50; inset: 16px auto 16px 16px; display: grid; width: min(330px, calc(100vw - 32px)); max-height: none; box-shadow: 0 18px 50px rgba(33, 48, 74, .22); }
  .review-workbench__right--open { inset: 16px 16px 16px auto; width: min(430px, calc(100vw - 32px)); overflow: auto; }
  .review-workbench__center { width: 100%; }
  .review-workbench__drawer-close { position: absolute; z-index: 1; top: 8px; right: 8px; }
}

@media (max-width: 640px) {
  .review-workbench { padding-inline: 14px; }
  .review-workbench__start-panel { align-items: stretch; flex-direction: column; }
  .review-workbench__start-panel button { width: 100%; }
  .review-workbench__left--open,
  .review-workbench__right--open { inset: 8px; width: auto; }
}
</style>
