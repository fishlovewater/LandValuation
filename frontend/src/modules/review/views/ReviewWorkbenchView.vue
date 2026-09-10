<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ConfirmDialog from '../../../components/common/ConfirmDialog.vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import GlassCard from '../../../components/glass/GlassCard.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
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
type ConfirmationName = 'finalize' | null

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
const correctionOpen = ref(false)
const correctionMessage = ref('')
const correctionDueAt = ref('')
const supplementOpen = ref(false)
const supplementDueAt = ref('')
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
const latestCorrection = computed(() => {
  const requests = detail.value?.correctionRequests ?? []
  return requests.reduce<typeof requests[number] | null>(
    (latest, request) => (!latest || request.request_no > latest.request_no ? request : latest),
    null,
  )
})
const confirmedFindings = computed(() =>
  detail.value?.findings.filter((finding) => finding.statusCode === 'CONFIRMED_ISSUE') ?? [],
)
const unresolvedMissingItems = computed(() =>
  detail.value?.missingItems.filter((item) => item.status === 'OPEN') ?? [],
)
const requestedMissingItems = computed(() =>
  unresolvedMissingItems.value.filter((item) => ['PENDING', 'SENT', 'ACKNOWLEDGED'].includes(item.notification_status ?? '')),
)
const requestableMissingItems = computed(() =>
  unresolvedMissingItems.value.filter((item) => !['PENDING', 'SENT', 'ACKNOWLEDGED'].includes(item.notification_status ?? '')),
)
const canRequestSupplement = computed(() => Boolean(
  canExecute.value
    && requestableMissingItems.value.length
    && detail.value?.reviewStatusCode !== 'REVIEW_COMPLETED',
))
const correctionGateBlockers = computed(() => {
  if (!detail.value) return ['尚未載入案件資料。']
  const blockers: string[] = []
  if (!canDecide.value) blockers.push('目前帳號沒有要求修正的權限。')
  if (latestRun.value?.runStatusCode !== 'COMPLETED') blockers.push('最新一次智慧審查尚未完成。')
  const openCount = detail.value.findings.filter((finding) => ['OPEN', 'REQUIRES_SUPPLEMENT'].includes(finding.statusCode)).length
  const expertCount = detail.value.findings.filter((finding) => finding.statusCode === 'EXPERT_REVIEW').length
  if (openCount) blockers.push(`仍有 ${openCount} 項疑點尚未完成判定。`)
  if (expertCount) blockers.push(`仍有 ${expertCount} 項疑點等待專業覆核。`)
  if (!confirmedFindings.value.length) blockers.push('至少需要一項已確認問題，才能要求估價端修正。')
  const active = latestCorrection.value
  if (active && active.status !== 'RECHECKED') blockers.push('目前已有進行中的修正通知。')
  return blockers
})
const canRequestCorrection = computed(() => correctionGateBlockers.value.length === 0)
const canSendCorrection = computed(() => Boolean(
  canDecide.value && latestCorrection.value?.status === 'DRAFT',
))
const canRecheckCorrection = computed(() => Boolean(
  canExecute.value && latestCorrection.value?.status === 'RESUBMITTED',
))
const correctionActionReason = computed(() => {
  if (latestCorrection.value?.status === 'DRAFT') return canSendCorrection.value ? '修正通知草稿已建立，可正式送出並退回估價端。' : '目前帳號沒有送出修正通知的權限。'
  if (latestCorrection.value?.status === 'SENT') return '修正通知已送出，等待估價端建立較新的正式版本並重新送審。'
  if (latestCorrection.value?.status === 'RESUBMITTED') return canRecheckCorrection.value ? '估價端已送回新版，可執行新版完整性與規則重檢。' : '目前帳號沒有執行新版重檢的權限。'
  return correctionGateBlockers.value[0] ?? '建立修正通知並送回估價端。'
})
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
  const incompleteMissingCount = detail.value.missingItems.filter((item) => item.status === 'OPEN').length
  if (incompleteMissingCount) blockers.push(`仍有 ${incompleteMissingCount} 項缺件尚未完成補齊。`)
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
    const handledFinding = detail.value?.findings.find((finding) => finding.findingId === value.findingId)
    if (handledFinding && handledFinding.statusCode !== 'OPEN') {
      const nextOpenFinding = detail.value?.findings.find((finding) => finding.statusCode === 'OPEN')
      if (nextOpenFinding) {
        selectedFindingId.value = nextOpenFinding.findingId
        await router.replace({ query: { ...route.query, finding: nextOpenFinding.findingId } })
      }
    }
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

function defaultCorrectionDueAt(): string {
  const due = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  const local = new Date(due.getTime() - due.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function defaultSupplementDueAt(): string {
  return defaultCorrectionDueAt()
}

function askSupplement(): void {
  if (!canRequestSupplement.value || mutating.value) return
  supplementDueAt.value = defaultSupplementDueAt()
  supplementOpen.value = true
}

async function sendSupplementRequest(): Promise<void> {
  if (!reviewId.value || !canRequestSupplement.value || mutating.value) return
  const due = new Date(supplementDueAt.value)
  if (!supplementDueAt.value || Number.isNaN(due.getTime()) || due.getTime() <= Date.now()) {
    actionError.value = '補件期限必須晚於目前時間。'
    return
  }
  mutating.value = true
  actionError.value = ''
  try {
    await reviewApi.requestSupplement(reviewId.value, due.toISOString())
    supplementOpen.value = false
    await refreshAfterMutation()
  } catch (caught: unknown) {
    actionError.value = safeReviewErrorMessage(caught)
    await refreshAfterMutation().catch(() => undefined)
  } finally {
    mutating.value = false
  }
}

function askCorrection(): void {
  if (!canRequestCorrection.value || mutating.value) return
  correctionMessage.value = confirmedFindings.value
    .map((finding) => `${finding.title}：${finding.description}`)
    .join('\n')
  correctionDueAt.value = defaultCorrectionDueAt()
  correctionOpen.value = true
}

async function createAndSendCorrection(): Promise<void> {
  if (!reviewId.value || !canRequestCorrection.value || mutating.value) return
  const message = correctionMessage.value.trim()
  const due = new Date(correctionDueAt.value)
  if (!message) {
    actionError.value = '請填寫要通知估價端的修正內容。'
    return
  }
  if (!correctionDueAt.value || Number.isNaN(due.getTime()) || due.getTime() <= Date.now()) {
    actionError.value = '修正期限必須晚於目前時間。'
    return
  }
  mutating.value = true
  actionError.value = ''
  let createdDraftId: string | null = null
  try {
    const draft = await reviewApi.createCorrectionRequest(reviewId.value, {
      message,
      due_at: due.toISOString(),
    })
    createdDraftId = draft.correction_request_id
    await reviewApi.sendCorrectionRequest(draft.correction_request_id)
    correctionOpen.value = false
    await refreshAfterMutation()
  } catch (caught: unknown) {
    // Draft creation and sending are two separate server transactions. If the
    // second call fails, close the create dialog and surface the persisted DRAFT
    // through the action bar so the reviewer can safely retry only the send.
    if (createdDraftId) correctionOpen.value = false
    actionError.value = safeReviewErrorMessage(caught)
    await refreshAfterMutation().catch(() => undefined)
  } finally {
    mutating.value = false
  }
}

async function sendExistingCorrection(): Promise<void> {
  const request = latestCorrection.value
  if (!request || request.status !== 'DRAFT' || !canSendCorrection.value || mutating.value) return
  mutating.value = true
  actionError.value = ''
  try {
    await reviewApi.sendCorrectionRequest(request.correction_request_id)
    await refreshAfterMutation()
  } catch (caught: unknown) {
    actionError.value = safeReviewErrorMessage(caught)
  } finally {
    mutating.value = false
  }
}

async function recheckCorrection(): Promise<void> {
  const request = latestCorrection.value
  if (!request || request.status !== 'RESUBMITTED' || !canRecheckCorrection.value || mutating.value) return
  mutating.value = true
  actionError.value = ''
  try {
    await reviewApi.recheckCorrectionRequest(request.correction_request_id)
    await refreshAfterMutation()
  } catch (caught: unknown) {
    actionError.value = safeReviewErrorMessage(caught)
    await refreshAfterMutation().catch(() => undefined)
  } finally {
    mutating.value = false
  }
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

async function confirmAction(): Promise<void> {
  const requested = confirmation.value
  if (!requested || mutating.value) return
  confirmation.value = null
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
          :can-request-correction="canRequestCorrection"
          :can-send-correction="canSendCorrection"
          :can-recheck-correction="canRecheckCorrection"
          :correction-status="latestCorrection?.status ?? null"
          :correction-action-reason="correctionActionReason"
          :review-status-code="detail.reviewStatusCode"
          :unresolved-finding-count="unresolvedCount"
          :latest-run-id="latestRun?.validationRunId"
          :report-document="latestReport"
          :report-action-reason="reportActionReason"
          :finalize-action-reason="finalizeActionReason"
          :busy="mutating"
          @finalize-request="askFinalize"
          @correction-request="askCorrection"
          @send-correction="sendExistingCorrection"
          @recheck-correction="recheckCorrection"
          @generate-report="generateReport"
          @open-result="openResult"
        />
        <p v-if="error || actionError" class="review-workbench__error" role="alert">{{ error || actionError }}</p>

        <section
          v-if="detail.missingItems.length"
          v-liquid-glass
          data-lg
          class="review-workbench__supplement lg"
          data-testid="review-missing-items"
          aria-labelledby="review-missing-items-title"
        >
          <div class="review-workbench__supplement-heading">
            <div>
              <span>COMPLETENESS</span>
              <strong id="review-missing-items-title">缺件與補件要求</strong>
            </div>
            <button
              v-if="canRequestSupplement"
              type="button"
              data-testid="request-supplement"
              :disabled="mutating"
              @click="askSupplement"
            >
              要求估價端補件
            </button>
          </div>
          <p v-if="requestableMissingItems.length" class="review-workbench__supplement-note">
            有 {{ requestableMissingItems.length }} 項完整性缺件尚未通知估價端；設定期限後可一次正式提出補件要求。
          </p>
          <p v-else-if="requestedMissingItems.length" class="review-workbench__supplement-note">
            已提出 {{ requestedMissingItems.length }} 項補件要求，等待估價端補齊資料。
          </p>
          <ul>
            <li v-for="item in detail.missingItems" :key="item.missing_item_id">
              <div>
                <strong>{{ item.item_name }}</strong>
                <span>{{ item.reason || '伺服器完整性檢查判定缺少必要資料。' }}</span>
                <small v-if="item.field_path">欄位：{{ item.field_path }}</small>
              </div>
              <div class="review-workbench__supplement-status">
                <b :data-status="item.notification_status || item.status">
                  {{ item.status !== 'OPEN' ? item.status : ['PENDING', 'SENT', 'ACKNOWLEDGED'].includes(item.notification_status || '') ? '已要求補件' : item.notification_status === 'FAILED' ? '通知失敗，可重送' : '待提出補件' }}
                </b>
                <small v-if="item.due_at">期限：{{ new Date(item.due_at).toLocaleString('zh-TW') }}</small>
              </div>
            </li>
          </ul>
        </section>

        <section v-if="latestCorrection" class="review-workbench__correction" data-testid="correction-status-panel">
          <div class="review-workbench__correction-heading">
            <div>
              <span>補正流程</span>
              <strong>第 {{ latestCorrection.request_no }} 次修正通知</strong>
            </div>
            <b :data-status="latestCorrection.status">{{ latestCorrection.status }}</b>
          </div>
          <p>{{ latestCorrection.message }}</p>
          <small>期限：{{ new Date(latestCorrection.due_at).toLocaleString('zh-TW') }}</small>
          <ul v-if="latestCorrection.items.length">
            <li v-for="item in latestCorrection.items" :key="item.correction_request_item_id">
              <strong>{{ item.issue_summary }}</strong>
              <span>要求修正：{{ item.requested_correction }}</span>
              <small v-if="item.recheck_outcome !== 'NOT_EVALUATED'">重檢：{{ item.recheck_outcome }}</small>
            </li>
          </ul>
        </section>

        <section
          v-if="detail.versionDiffs.length"
          v-liquid-glass
          data-lg
          class="review-workbench__diffs lg"
          data-testid="review-version-diffs"
          aria-labelledby="review-version-diffs-title"
        >
          <div class="review-workbench__diffs-heading">
            <div>
              <span>VERSION DIFF</span>
              <strong id="review-version-diffs-title">補正前後欄位差異</strong>
            </div>
            <small>{{ detail.versionDiffs.length }} 項變更</small>
          </div>
          <div class="review-workbench__diff-grid">
            <article v-for="diff in detail.versionDiffs" :key="diff.key">
              <div class="review-workbench__diff-title">
                <strong>{{ diff.fieldLabel }}</strong>
                <code>{{ diff.fieldPath || diff.fieldCode }}</code>
              </div>
              <div class="review-workbench__diff-values">
                <div class="is-before">
                  <span>補正前 · v{{ diff.previousDocumentVersion }}</span>
                  <strong>{{ diff.previousValue }}</strong>
                  <small v-if="diff.previousPageNumber">第 {{ diff.previousPageNumber }} 頁</small>
                  <p v-if="diff.previousRawText">{{ diff.previousRawText }}</p>
                </div>
                <span class="review-workbench__diff-arrow" aria-hidden="true">→</span>
                <div class="is-after">
                  <span>補正後 · v{{ diff.currentDocumentVersion }}</span>
                  <strong>{{ diff.currentValue }}</strong>
                  <small v-if="diff.currentPageNumber">第 {{ diff.currentPageNumber }} 頁</small>
                  <p v-if="diff.currentRawText">{{ diff.currentRawText }}</p>
                </div>
              </div>
            </article>
          </div>
        </section>

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

    <GlassModal
      :open="correctionOpen"
      id="review-correction-request"
      title="要求估價端修正"
      initial-focus="#review-correction-message"
      @close="correctionOpen = false"
    >
      <form class="review-workbench__correction-form" data-testid="correction-request-form" @submit.prevent="createAndSendCorrection">
        <p>修正通知會保存目前已確認問題的快照，送出後案件會正式退回估價端。估價端必須建立較新的正式版本再重新送審。</p>
        <label>
          <span>修正內容 *</span>
          <textarea id="review-correction-message" v-model="correctionMessage" rows="7" maxlength="4000" required />
        </label>
        <label>
          <span>修正期限 *</span>
          <input v-model="correctionDueAt" type="datetime-local" required />
        </label>
        <section class="review-workbench__correction-preview" aria-label="本次確認問題">
          <strong>本次會要求修正 {{ confirmedFindings.length }} 項</strong>
          <ul>
            <li v-for="finding in confirmedFindings" :key="finding.findingId">
              {{ finding.title }}｜{{ finding.fieldPathLabel }}
            </li>
          </ul>
        </section>
        <div class="review-workbench__correction-actions">
          <button type="button" :disabled="mutating" @click="correctionOpen = false">取消</button>
          <button type="submit" :disabled="mutating">{{ mutating ? '送出中…' : '建立並送出修正通知' }}</button>
        </div>
      </form>
    </GlassModal>

    <GlassModal
      :open="supplementOpen"
      id="review-supplement-request"
      title="要求估價端補件"
      initial-focus="#review-supplement-due-at"
      @close="supplementOpen = false"
    >
      <form class="review-workbench__correction-form" data-testid="supplement-request-form" @submit.prevent="sendSupplementRequest">
        <p>這是完整性缺件流程，不會把缺件冒充成審查疑點。送出後，所有目前 OPEN 的缺件會由後端標記為已要求補件並保存期限。</p>
        <section class="review-workbench__correction-preview" aria-label="本次補件項目">
          <strong>本次要求補件 {{ requestableMissingItems.length }} 項</strong>
          <ul>
            <li v-for="item in requestableMissingItems" :key="item.missing_item_id">
              {{ item.item_name }}{{ item.reason ? `｜${item.reason}` : '' }}
            </li>
          </ul>
        </section>
        <label>
          <span>補件期限 *</span>
          <input id="review-supplement-due-at" v-model="supplementDueAt" type="datetime-local" required>
        </label>
        <div class="review-workbench__correction-actions">
          <button type="button" :disabled="mutating" @click="supplementOpen = false">取消</button>
          <button type="submit" :disabled="mutating || !requestableMissingItems.length">{{ mutating ? '送出中…' : '正式要求補件' }}</button>
        </div>
      </form>
    </GlassModal>
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
.review-workbench__supplement,
.review-workbench__diffs,
.review-workbench__correction { display: grid; gap: 10px; margin-top: 12px; padding: 16px 18px; border: 1px solid rgba(206, 147, 48, .28); border-radius: var(--app-radius-sm); background: #fffbf1; }
.review-workbench__supplement { border-color: rgba(214, 166, 62, .30); background: #fffaf0; }
.review-workbench__supplement-heading,
.review-workbench__diffs-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.review-workbench__supplement-heading > div,
.review-workbench__diffs-heading > div { display: grid; gap: 3px; }
.review-workbench__supplement-heading span,
.review-workbench__diffs-heading span { color: var(--app-accent-deep); font-size: 9px; font-weight: 900; letter-spacing: .12em; }
.review-workbench__supplement-heading strong,
.review-workbench__diffs-heading strong { color: var(--app-ink); font-size: 15px; }
.review-workbench__supplement-heading button { min-height: 40px; padding: 7px 12px; border: 1px solid var(--app-accent); border-radius: 8px; color: #fff; background: var(--app-accent); cursor: pointer; font-size: 11px; font-weight: 900; }
.review-workbench__supplement-heading button:disabled { cursor: not-allowed; opacity: .55; }
.review-workbench__supplement-note { margin: 0; color: var(--app-ink-soft); font-size: 12px; line-height: 1.6; }
.review-workbench__supplement > ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.review-workbench__supplement > ul > li { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 11px 12px; border: 1px solid rgba(214, 166, 62, .20); border-radius: 9px; background: rgba(255,255,255,.80); }
.review-workbench__supplement > ul > li > div:first-child { display: grid; gap: 4px; min-width: 0; }
.review-workbench__supplement > ul strong { color: var(--app-ink); font-size: 12px; }
.review-workbench__supplement > ul span { color: var(--app-ink-soft); font-size: 11px; line-height: 1.5; }
.review-workbench__supplement > ul small { color: var(--app-muted); font-size: 10px; }
.review-workbench__supplement-status { display: grid; flex: 0 0 auto; gap: 4px; justify-items: end; text-align: right; }
.review-workbench__supplement-status b { padding: 5px 8px; border-radius: 999px; color: #7a5a15; background: #fff1c9; font-size: 10px; white-space: nowrap; }
.review-workbench__supplement-status b[data-status="PENDING"],
.review-workbench__supplement-status b[data-status="SENT"],
.review-workbench__supplement-status b[data-status="ACKNOWLEDGED"] { color: #2e5984; background: #edf4fb; }
.review-workbench__supplement-status b[data-status="FAILED"] { color: #9d2f2b; background: #fdeceb; }
.review-workbench__diffs { border-color: rgba(46,89,132,.20); background: #f6f9fd; }
.review-workbench__diffs-heading > small { color: var(--app-muted); font-size: 11px; }
.review-workbench__diff-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
.review-workbench__diff-grid article { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--app-line); border-radius: 9px; background: rgba(255,255,255,.82); }
.review-workbench__diff-title { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.review-workbench__diff-title strong { color: var(--app-ink); font-size: 12px; }
.review-workbench__diff-title code { overflow-wrap: anywhere; color: var(--app-muted); font-size: 9px; text-align: right; }
.review-workbench__diff-values { display: grid; grid-template-columns: minmax(0,1fr) auto minmax(0,1fr); align-items: stretch; gap: 8px; }
.review-workbench__diff-values > div { display: grid; align-content: start; gap: 4px; padding: 10px; border-radius: 8px; background: #f7f8fb; min-width: 0; }
.review-workbench__diff-values > div.is-after { background: #f2f8f4; }
.review-workbench__diff-values span { color: var(--app-muted); font-size: 9px; font-weight: 800; }
.review-workbench__diff-values strong { overflow-wrap: anywhere; color: var(--app-ink); font-size: 13px; }
.review-workbench__diff-values small { color: var(--app-muted); font-size: 9px; }
.review-workbench__diff-values p { margin: 3px 0 0; overflow-wrap: anywhere; color: var(--app-ink-soft); font-size: 10px; line-height: 1.45; }
.review-workbench__diff-arrow { align-self: center; color: var(--app-accent-deep) !important; font-size: 18px !important; }
.review-workbench__correction-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.review-workbench__correction-heading div { display: grid; gap: 3px; }
.review-workbench__correction-heading span { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.review-workbench__correction-heading strong { color: var(--app-ink); font-size: 14px; }
.review-workbench__correction-heading b { padding: 5px 8px; border-radius: 999px; color: #7a5a15; background: #fff1c9; font-size: 10px; }
.review-workbench__correction p { margin: 0; color: var(--app-ink-soft); font-size: 12px; line-height: 1.65; }
.review-workbench__correction > small { color: var(--app-muted); font-size: 11px; }
.review-workbench__correction ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.review-workbench__correction li { display: grid; gap: 3px; padding: 9px 10px; border-radius: 8px; background: rgba(255,255,255,.72); color: var(--app-ink-soft); font-size: 11px; }
.review-workbench__correction li strong { color: var(--app-ink); }
.review-workbench__correction-form { display: grid; gap: 14px; min-width: min(620px, 72vw); }
.review-workbench__correction-form > p { margin: 0; color: var(--app-muted); font-size: 12px; line-height: 1.7; }
.review-workbench__correction-form label { display: grid; gap: 6px; color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.review-workbench__correction-form textarea,
.review-workbench__correction-form input { width: 100%; box-sizing: border-box; padding: 10px 11px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink); background: #fff; font: inherit; }
.review-workbench__correction-preview { padding: 12px; border: 1px solid var(--app-line); border-radius: 9px; background: #f7f8fb; }
.review-workbench__correction-preview > strong { color: var(--app-ink); font-size: 12px; }
.review-workbench__correction-preview ul { margin: 8px 0 0; padding-left: 18px; color: var(--app-ink-soft); font-size: 11px; }
.review-workbench__correction-actions { display: flex; justify-content: flex-end; gap: 8px; }
.review-workbench__correction-actions button { min-height: 42px; padding: 8px 14px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-weight: 800; }
.review-workbench__correction-actions button[type="submit"] { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.review-workbench__correction-actions button:disabled { cursor: not-allowed; opacity: .55; }
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
  .review-workbench__diff-grid { grid-template-columns: 1fr; }
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
  .review-workbench__supplement-heading,
  .review-workbench__diffs-heading,
  .review-workbench__supplement > ul > li { align-items: stretch; flex-direction: column; }
  .review-workbench__supplement-heading button { width: 100%; }
  .review-workbench__supplement-status { justify-items: start; text-align: left; }
  .review-workbench__diff-values { grid-template-columns: 1fr; }
  .review-workbench__diff-arrow { justify-self: center; transform: rotate(90deg); }
  .review-workbench__left--open,
  .review-workbench__right--open { inset: 8px; width: auto; }
}
</style>
