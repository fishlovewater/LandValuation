<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhX as X } from '@phosphor-icons/vue'
import ConfirmDialog from '../../../components/common/ConfirmDialog.vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { useAuthStore } from '../../../stores/auth.store'
import EvidenceViewer from '../components/EvidenceViewer.vue'
import ExternalReviewIntake from '../components/ExternalReviewIntake.vue'
import FindingPanel from '../components/FindingPanel.vue'
import ReviewActionBar from '../components/ReviewActionBar.vue'
import ReviewProgressBar from '../components/ReviewProgressBar.vue'
import { reviewApi, safeReviewErrorMessage } from '../review.api'
import {
  correctionStatusLabel,
  fieldPathLabel,
  latestGeneratedReport,
  latestRunId as latestRunIdForDetail,
  mapWorkbenchDetail,
  missingItemStatusLabel,
  selectEvidenceDocument,
} from '../review.mappers'
import {
  canMutateExternalReviewInput,
  reviewInteractionCopy,
  reviewInteractionMode,
} from '../review.status'
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
const interactionMode = computed(() => reviewInteractionMode(detail.value?.reviewStatusCode ?? ''))
const interactionCopy = computed(() => reviewInteractionCopy(detail.value?.reviewStatusCode ?? ''))
const canMutateExternalInput = computed(() => Boolean(
  detail.value && canMutateExternalReviewInput(detail.value.reviewStatusCode),
))
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
const isPlatformCase = computed(() => detail.value?.caseSourceCode === 'PLATFORM')
const correctionRecipientLabel = computed(() => isPlatformCase.value ? '估價端' : '外部廠商')
const sourceSummary = computed(() => isPlatformCase.value
  ? '本次審查依平台送審時凍結的案件資料與文件版本進行，後續編輯不會改變本次審查依據。'
  : '本次審查以已匯入並確認的外部文件與案件資料版本進行。')
const inputVersionLabel = computed(() => {
  const current = detail.value
  if (!current) return ''
  if (current.caseSourceCode === 'PLATFORM') {
    return current.submissionNo !== null
      ? `第 ${current.submissionNo} 次送審 · 審查輸入已凍結`
      : current.submissionId
        ? '平台送審 · 審查輸入已凍結'
        : ''
  }
  return latestRun.value?.externalInputSnapshotNo
    ? `v${latestRun.value.externalInputSnapshotNo} 審查輸入已凍結`
    : ''
})
const inputVersionFingerprint = computed(() => isPlatformCase.value
  ? detail.value?.inputFingerprint ?? null
  : latestRun.value?.externalInputFingerprint ?? null)
const inputVersionFrozenAt = computed(() => isPlatformCase.value
  ? detail.value?.submittedAt ?? null
  : latestRun.value?.externalInputSnapshotCreatedAt ?? null)
const workflowSteps = computed(() => {
  const current = detail.value
  if (!current) return []
  const labels = current.caseSourceCode === 'PLATFORM'
    ? [
        ['received', '接收送審'],
        ['confirm', '資料確認'],
        ['validate', '智慧檢核'],
        ['triage', '人工判定'],
        ['recheck', '修正／重檢'],
        ['complete', '審查完成'],
      ]
    : [
        ['created', '建立案件'],
        ['documents', '文件匯入'],
        ['confirm', '欄位確認'],
        ['validate', '智慧檢核'],
        ['triage', '人工判定'],
        ['recheck', '修正／重檢'],
        ['complete', '審查完成'],
      ]
  const completeIndex = labels.length - 1
  const recheckIndex = labels.findIndex(([key]) => key === 'recheck')
  const triageIndex = labels.findIndex(([key]) => key === 'triage')
  const validateIndex = labels.findIndex(([key]) => key === 'validate')
  const confirmIndex = labels.findIndex(([key]) => key === 'confirm')
  const documentsIndex = labels.findIndex(([key]) => key === 'documents')
  const status = current.reviewStatusCode.toUpperCase()
  const correctionActive = Boolean(latestCorrection.value && latestCorrection.value.status !== 'RECHECKED')

  let activeIndex = confirmIndex
  if (['APPROVED', 'REVIEW_COMPLETED'].includes(status)) {
    activeIndex = completeIndex
  } else if (correctionActive || status === 'RETURNED_FOR_REVISION') {
    activeIndex = recheckIndex
  } else if (latestRun.value?.runStatusCode === 'RUNNING' || status === 'ANALYZING') {
    activeIndex = validateIndex
  } else if (latestRun.value?.runStatusCode === 'COMPLETED') {
    activeIndex = triageIndex
  } else if (current.caseSourceCode !== 'PLATFORM' && !current.documents.length && documentsIndex >= 0) {
    activeIndex = documentsIndex
  }

  return labels.map(([key, label], index) => ({
    key,
    label,
    state: index < activeIndex ? 'done' as const : index === activeIndex ? 'active' as const : 'upcoming' as const,
  }))
})
const activeWorkflowLabel = computed(() => workflowSteps.value.find((step) => step.state === 'active')?.label ?? '審查處理')
const supplementActionLabel = computed(() => isPlatformCase.value ? '要求估價端補件' : '建立外部補件要求')

function recheckOutcomeLabel(value: string): string {
  const labels: Record<string, string> = {
    NOT_EVALUATED: '尚未重新檢核',
    RESOLVED: '已修正',
    STILL_PRESENT: '仍需處理',
    CHANGED: '內容已變更，請再次確認',
  }
  return labels[value] ?? '已完成重新檢核'
}
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
    && ['PENDING_MATERIALS', 'SUPPLEMENT_REQUIRED'].includes(detail.value?.reviewStatusCode ?? ''),
))
const correctionGateBlockers = computed(() => {
  if (!detail.value) return ['尚未載入案件資料。']
  const blockers: string[] = []
  if (!canDecide.value) blockers.push('目前帳號沒有要求修正的權限。')
  if (detail.value.reviewStatusCode !== 'REVIEW_REQUIRED') blockers.push('只有待人工決策中的案件可建立修正通知。')
  if (latestRun.value?.runStatusCode !== 'COMPLETED') blockers.push('最新一次智慧審查尚未完成。')
  const openCount = detail.value.findings.filter((finding) => ['OPEN', 'REQUIRES_SUPPLEMENT'].includes(finding.statusCode)).length
  const expertCount = detail.value.findings.filter((finding) => finding.statusCode === 'EXPERT_REVIEW').length
  if (openCount) blockers.push(`仍有 ${openCount} 項疑點尚未完成判定。`)
  if (expertCount) blockers.push(`仍有 ${expertCount} 項疑點等待專業覆核。`)
  if (!confirmedFindings.value.length) blockers.push(`至少需要一項已確認問題，才能要求${correctionRecipientLabel.value}修正。`)
  const active = latestCorrection.value
  if (active && active.status !== 'RECHECKED') blockers.push('目前已有進行中的修正通知。')
  return blockers
})
const canRequestCorrection = computed(() => correctionGateBlockers.value.length === 0)
const canSendCorrection = computed(() => Boolean(
  canDecide.value
    && detail.value?.reviewStatusCode === 'REVIEW_REQUIRED'
    && latestCorrection.value?.status === 'DRAFT',
))
const canRecheckCorrection = computed(() => Boolean(
  canExecute.value
    && detail.value?.reviewStatusCode === 'RETURNED_FOR_REVISION'
    && latestCorrection.value?.status === 'RESUBMITTED',
))
const correctionActionReason = computed(() => {
  if (latestCorrection.value?.status === 'DRAFT') {
    if (detail.value?.reviewStatusCode !== 'REVIEW_REQUIRED') return '目前案件狀態不可送出修正通知。'
    if (!canSendCorrection.value) return '目前帳號沒有送出修正通知的權限。'
    return isPlatformCase.value
      ? '修正通知草稿已建立，可正式送出並退回估價端。'
      : '修正通知草稿已建立；請先透過既有外部管道通知廠商，再於系統確認已對外通知。'
  }
  if (latestCorrection.value?.status === 'SENT') {
    return isPlatformCase.value
      ? '修正通知已送出，等待估價端建立較新的正式版本並重新送審。'
      : '已記錄完成對外通知，等待外部廠商回傳新版文件。'
  }
  if (latestCorrection.value?.status === 'RESUBMITTED') {
    if (detail.value?.reviewStatusCode !== 'RETURNED_FOR_REVISION') return '只有等待補正的案件可執行新版重檢。'
    if (!canRecheckCorrection.value) return '目前帳號沒有執行新版重檢的權限。'
    return isPlatformCase.value
      ? '估價端已送回新版，可執行新版完整性與規則重檢。'
      : '外部廠商新版文件已匯入，可執行新版完整性與規則重檢。'
  }
  return correctionGateBlockers.value[0] ?? `建立修正通知並要求${correctionRecipientLabel.value}修正。`
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
const canFinalize = computed(() => Boolean(
  canDecide.value
    && detail.value?.reviewStatusCode === 'REVIEW_REQUIRED'
    && completionBlockers.value.length === 0,
))
const finalizeActionReason = computed(() => {
  if (detail.value?.reviewStatusCode !== 'REVIEW_REQUIRED') return '只有待人工決策中的案件可完成審查。'
  return completionBlockers.value[0] ?? '完成審查前會顯示未處理疑點數量。'
})
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
    source: stringQuery('source') || undefined,
    district: stringQuery('district') || undefined,
    urgency: stringQuery('urgency') || undefined,
    sortBy: stringQuery('sortBy') || undefined,
    sortDirection: stringQuery('sortDirection') === 'asc' ? 'asc' as const : 'desc' as const,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  }
}

function queueQuery(): Record<string, string> {
  const names = [
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
  ]
  return Object.fromEntries(
    names
      .map((name) => [name, stringQuery(name)] as const)
      .filter(([, value]) => value),
  )
}

function syncAssistantContextQuery(): void {
  const currentDetail = detail.value
  if (!currentDetail) return
  const nextQuery = {
    ...route.query,
    caseId: currentDetail.caseId,
    ...(selectedFindingId.value ? { finding: selectedFindingId.value } : {}),
  }
  if (
    route.query.caseId === currentDetail.caseId
    && (!selectedFindingId.value || route.query.finding === selectedFindingId.value)
  ) return
  void router.replace({ query: nextQuery })
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
    syncAssistantContextQuery()
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
  syncAssistantContextQuery()
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
    actionError.value = `請填寫要通知${correctionRecipientLabel.value}的修正內容。`
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
    correctionOpen.value = false
    if (isPlatformCase.value) {
      await reviewApi.sendCorrectionRequest(draft.correction_request_id)
    }
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
  if (drawer.value === 'left') closeDrawer()
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
      eyebrow="案件審查"
      :title="detail?.caseTitle ?? '案件審查'"
      :description="detail ? `${detail.caseNo} · ${detail.districtLabel} · 評價基準日 ${detail.valuationBaseDate}` : '讀取審查案件與證據。'"
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
        <ReviewProgressBar :steps="workflowSteps" />

        <section class="review-workbench__source-strip" data-testid="review-source-strip" aria-label="案件來源與目前流程">
          <div class="review-workbench__source-main">
            <span class="review-workbench__source-badge" :data-source="detail.caseSourceCode">{{ detail.caseSourceLabel }}</span>
            <div>
              <strong>目前階段：{{ activeWorkflowLabel }}</strong>
              <p>{{ sourceSummary }}</p>
            </div>
          </div>
          <div class="review-workbench__source-stats" aria-label="案件摘要">
            <span><b>{{ detail.documents.length }}</b> 份文件</span>
            <span><b>{{ detail.findings.length }}</b> 項疑點</span>
            <span><b>{{ unresolvedMissingItems.length }}</b> 項待補資料</span>
            <span
              v-if="inputVersionLabel"
              data-testid="review-input-provenance"
              :title="inputVersionFingerprint ? `輸入指紋 ${inputVersionFingerprint}` : undefined"
            >
              <b>{{ inputVersionLabel }}</b>
            </span>
          </div>
          <div class="review-workbench__source-actions">
            <button
              type="button"
              data-testid="open-review-context"
              aria-controls="review-context-drawer"
              :aria-expanded="drawer === 'left'"
              @click="openDrawer('left', $event)"
            >
              案件資料
            </button>
            <button
              type="button"
              data-testid="open-review-finding"
              aria-controls="review-finding-drawer"
              :aria-expanded="drawer === 'right'"
              :disabled="!detail.findings.length"
              @click="openDrawer('right', $event)"
            >
              疑點內容<span v-if="detail.findings.length">（{{ unresolvedCount }} 待處理）</span>
            </button>
          </div>
        </section>

        <section
          v-if="interactionMode !== 'EDITABLE'"
          class="review-workbench__readonly-banner"
          :data-mode="interactionMode"
          data-testid="review-readonly-mode"
          role="status"
        >
          <strong>{{ interactionCopy.title }}</strong>
          <p>{{ interactionCopy.description }}</p>
        </section>

        <ExternalReviewIntake
          v-if="detail.caseSourceCode === 'EXTERNAL'"
          :review-id="detail.reviewId"
          :documents="detail.documents"
          :correction-request="latestCorrection"
          :can-mutate="canMutateExternalInput"
          @changed="loadDetail"
        />

        <div v-if="showStartReview" class="review-workbench__start-panel" data-testid="review-start-panel">
          <div>
            <strong>尚未開始智慧審查</strong>
            <p>先執行資料完整性與規則檢核，完成後才能處理疑點並完成審查。</p>
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
          :case-source-code="detail.caseSourceCode"
          :correction-action-reason="correctionActionReason"
          :review-status-code="detail.reviewStatusCode"
          :total-finding-count="detail.findings.length"
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
          class="review-workbench__supplement"
          data-testid="review-missing-items"
          aria-labelledby="review-missing-items-title"
        >
          <div class="review-workbench__supplement-heading">
            <div>
              <span>資料完整性</span>
              <strong id="review-missing-items-title">缺件與補件要求</strong>
            </div>
            <button
              v-if="canRequestSupplement"
              type="button"
              data-testid="request-supplement"
              :disabled="mutating"
              @click="askSupplement"
            >
              {{ supplementActionLabel }}
            </button>
          </div>
          <p v-if="requestableMissingItems.length" class="review-workbench__supplement-note">
            有 {{ requestableMissingItems.length }} 項完整性缺件尚未通知{{ correctionRecipientLabel }}；設定期限後可一次正式提出補件要求。
          </p>
          <p v-else-if="requestedMissingItems.length" class="review-workbench__supplement-note">
            已提出 {{ requestedMissingItems.length }} 項補件要求，等待{{ correctionRecipientLabel }}補齊資料。
          </p>
          <ul>
            <li v-for="item in detail.missingItems" :key="item.missing_item_id">
              <div>
                <strong>{{ item.item_name }}</strong>
                <span>{{ item.reason || '系統檢查後發現缺少必要資料。' }}</span>
                <small v-if="item.field_path">相關欄位：{{ fieldPathLabel(item.field_path) }}</small>
              </div>
              <div class="review-workbench__supplement-status">
                <b :data-status="item.notification_status || item.status">
                  {{ item.status !== 'OPEN' ? missingItemStatusLabel(item.status) : ['PENDING', 'SENT', 'ACKNOWLEDGED'].includes(item.notification_status || '') ? '已要求補件' : item.notification_status === 'FAILED' ? '通知失敗，可重送' : '待提出補件' }}
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
            <b :data-status="latestCorrection.status">{{ correctionStatusLabel(latestCorrection.status) }}</b>
          </div>
          <p>{{ latestCorrection.message }}</p>
          <small>期限：{{ new Date(latestCorrection.due_at).toLocaleString('zh-TW') }}</small>
          <ul v-if="latestCorrection.items.length">
            <li v-for="item in latestCorrection.items" :key="item.correction_request_item_id">
              <strong>{{ item.issue_summary }}</strong>
              <span>要求修正：{{ item.requested_correction }}</span>
              <small v-if="item.recheck_outcome !== 'NOT_EVALUATED'">重新檢核：{{ recheckOutcomeLabel(item.recheck_outcome) }}</small>
            </li>
          </ul>
        </section>

        <section
          v-if="detail.versionDiffs.length"
          class="review-workbench__diffs"
          data-testid="review-version-diffs"
          aria-labelledby="review-version-diffs-title"
        >
          <div class="review-workbench__diffs-heading">
            <div>
              <span>版本變更</span>
              <strong id="review-version-diffs-title">補正前後欄位差異</strong>
            </div>
            <small>{{ detail.versionDiffs.length }} 項變更</small>
          </div>
          <div class="review-workbench__diff-grid">
            <article v-for="diff in detail.versionDiffs" :key="diff.key">
              <div class="review-workbench__diff-title">
                <strong>{{ diff.fieldLabel }}</strong>
              </div>
              <div class="review-workbench__diff-values">
                <div class="is-before">
                  <span>補正前 · 第 {{ diff.previousDocumentVersion }} 版</span>
                  <strong>{{ diff.previousValue }}</strong>
                  <small v-if="diff.previousPageNumber">第 {{ diff.previousPageNumber }} 頁</small>
                  <p v-if="diff.previousRawText">{{ diff.previousRawText }}</p>
                </div>
                <span class="review-workbench__diff-arrow" aria-hidden="true">→</span>
                <div class="is-after">
                  <span>補正後 · 第 {{ diff.currentDocumentVersion }} 版</span>
                  <strong>{{ diff.currentValue }}</strong>
                  <small v-if="diff.currentPageNumber">第 {{ diff.currentPageNumber }} 頁</small>
                  <p v-if="diff.currentRawText">{{ diff.currentRawText }}</p>
                </div>
              </div>
            </article>
          </div>
        </section>

        <button
          v-if="drawer"
          type="button"
          class="review-workbench__drawer-backdrop"
          data-testid="review-drawer-backdrop"
          :aria-label="drawer === 'left' ? '關閉案件資料' : '關閉疑點內容'"
          @click="closeDrawer"
        />

        <div class="review-workbench__layout">
          <aside
            id="review-context-drawer"
            class="review-workbench__left"
            :class="{ 'review-workbench__left--open': drawer === 'left' }"
            :role="drawer === 'left' ? 'dialog' : undefined"
            :aria-modal="drawer === 'left' ? 'true' : undefined"
            aria-labelledby="review-context-title"
            aria-label="案件資料"
          >
            <div class="review-workbench__panel-heading">
              <div><p>案件資料</p><h2 id="review-context-title">案件概況</h2></div>
              <button v-if="drawer === 'left'" type="button" aria-label="關閉案件資料" @click="closeDrawer">
                <X :size="20" weight="bold" aria-hidden="true" />
              </button>
            </div>
            <dl class="review-workbench__case-facts">
              <div><dt>案件編號</dt><dd>{{ detail.caseNo }}</dd></div>
              <div><dt>案件狀態</dt><dd>{{ detail.caseStatusLabel }}</dd></div>
              <div><dt>審查狀態</dt><dd>{{ detail.reviewStatusLabel }}</dd></div>
              <div><dt>風險</dt><dd>{{ detail.riskLevelLabel }}</dd></div>
            </dl>
            <section v-if="inputVersionLabel" class="review-workbench__context-section" data-testid="review-input-context">
              <h3>審查依據版本</h3>
              <dl class="review-workbench__case-facts review-workbench__provenance-facts">
                <div><dt>資料來源</dt><dd>{{ detail.caseSourceLabel }}</dd></div>
                <div><dt>凍結版本</dt><dd>{{ inputVersionLabel }}</dd></div>
                <div v-if="inputVersionFrozenAt"><dt>凍結時間</dt><dd>{{ new Date(inputVersionFrozenAt).toLocaleString('zh-TW') }}</dd></div>
                <div v-if="inputVersionFingerprint"><dt>內容指紋</dt><dd class="review-workbench__fingerprint">{{ inputVersionFingerprint }}</dd></div>
              </dl>
              <p class="review-workbench__muted">本次檢核與審查結果綁定此凍結版本；後續案件或文件變更不會回寫到既有審查依據。</p>
            </section>
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
              <h3>檢核紀錄（{{ detail.runs.length }}）</h3>
              <ul v-if="detail.runs.length" class="review-workbench__plain-list">
                <li v-for="run in detail.runs" :key="run.validationRunId">
                  <span>第 {{ run.runNo ?? '—' }} 次：{{ run.runStatusLabel }}</span>
                  <small>{{ run.failedCount }} 個阻擋項目</small>
                </li>
              </ul>
              <p v-else class="review-workbench__muted">目前沒有檢核紀錄。</p>
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
              <p>補正通知 {{ detail.correctionRequests.length }} 件 · 已儲存決定 {{ detail.decisions.length }} 筆</p>
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
            <button v-if="drawer === 'right'" type="button" class="review-workbench__drawer-close" aria-label="關閉疑點內容" @click="closeDrawer">
              <X :size="20" weight="bold" aria-hidden="true" />
            </button>
            <section class="review-workbench__finding-queue" aria-labelledby="review-finding-queue-title">
              <div class="review-workbench__finding-queue-heading">
                <div>
                  <span>人工判定</span>
                  <strong id="review-finding-queue-title">疑點佇列</strong>
                </div>
                <small>{{ unresolvedCount }} 項待處理</small>
              </div>
              <div v-if="detail.findings.length" class="review-workbench__finding-tabs">
                <button
                  v-for="finding in detail.findings"
                  :key="finding.findingId"
                  type="button"
                  :class="{ 'is-selected': finding.findingId === selectedFindingId }"
                  :aria-pressed="finding.findingId === selectedFindingId"
                  @click="selectFinding(finding.findingId)"
                >
                  <span>{{ finding.title }}</span>
                  <small>{{ finding.severityLabel }} · {{ finding.statusLabel }}</small>
                </button>
              </div>
              <p v-else class="review-workbench__muted">目前沒有需要人工判定的疑點。</p>
            </section>
            <div class="review-workbench__finding-frame" data-testid="right-finding-frame">
              <FindingPanel
                :finding="selectedFinding"
                :decision="selectedDecision"
                :can-decide="canDecide"
                :can-triage="canTriage"
                :readonly-reason="triageReadonlyReason"
                :saving="mutating"
                @save="saveFindingDecision"
              />
            </div>
          </aside>
        </div>
      </template>
    </template>

    <ConfirmDialog
      :open="confirmation === 'finalize'"
      title="完成審查確認"
      :message="`目前有 ${unresolvedCount} 個尚未處理的疑點。系統會再次確認案件狀態，確定要完成審查嗎？`"
      confirm-label="完成審查"
      :busy="mutating"
      @cancel="confirmation = null"
      @close="confirmation = null"
      @confirm="confirmAction"
    />

    <GlassModal
      :open="correctionOpen"
      id="review-correction-request"
      :title="isPlatformCase ? '要求估價端修正' : '建立外部修正通知'"
      initial-focus="#review-correction-message"
      @close="correctionOpen = false"
    >
      <form class="review-workbench__correction-form" data-testid="correction-request-form" @submit.prevent="createAndSendCorrection">
        <p v-if="isPlatformCase">送出後會儲存本次已確認的問題內容，案件將正式退回估價端；估價端修正後需以新版資料重新送審。</p>
        <p v-else>建立後會先儲存本次已確認的問題內容。請透過既有外部管道將修正內容提供給廠商，再回到系統確認已對外通知；收到新版文件後再匯入並重新檢核。</p>
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
          <button type="submit" :disabled="mutating">{{ mutating ? '處理中…' : isPlatformCase ? '建立並送出修正通知' : '建立修正通知' }}</button>
        </div>
      </form>
    </GlassModal>

    <GlassModal
      :open="supplementOpen"
      id="review-supplement-request"
      :title="isPlatformCase ? '要求估價端補件' : '建立外部補件要求'"
      initial-focus="#review-supplement-due-at"
      @close="supplementOpen = false"
    >
      <form class="review-workbench__correction-form" data-testid="supplement-request-form" @submit.prevent="sendSupplementRequest">
        <p v-if="isPlatformCase">送出後，尚未補齊的必要資料會正式列為補件項目，並儲存你設定的補件期限。</p>
        <p v-else>系統會記錄尚未補齊的必要資料與期限；請再透過既有外部管道通知廠商，收到資料後匯入案件。</p>
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
.review-workbench__source-strip { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 18px; margin-top: 12px; padding: 14px 16px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #f8fafc; }
.review-workbench__source-main { display: flex; align-items: flex-start; gap: 12px; min-width: 0; }
.review-workbench__source-main > div { display: grid; gap: 3px; min-width: 0; }
.review-workbench__source-main strong { color: var(--app-ink); font-size: 13px; }
.review-workbench__source-main p { margin: 0; color: var(--app-muted); font-size: 11px; line-height: 1.55; }
.review-workbench__source-badge { flex: 0 0 auto; padding: 5px 8px; border-radius: 999px; color: #2e5984; background: #edf4fb; font-size: 10px; font-weight: 900; white-space: nowrap; }
.review-workbench__source-badge[data-source="EXTERNAL"] { color: #765514; background: #fff2c9; }
.review-workbench__source-stats { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 12px; color: var(--app-muted); font-size: 10px; white-space: nowrap; }
.review-workbench__source-stats b { color: var(--app-ink); font-size: 12px; }
.review-workbench__source-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.review-workbench__source-actions button { min-height: 40px; padding: 7px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 11px; font-weight: 900; white-space: nowrap; }
.review-workbench__source-actions button:hover:not(:disabled) { border-color: rgba(200, 91, 67, .35); color: var(--app-accent-deep); }
.review-workbench__source-actions button:disabled { cursor: not-allowed; opacity: .5; }
.review-workbench__readonly-banner { display: grid; gap: 4px; margin-top: 12px; padding: 12px 14px; border: 1px solid #d8c48d; border-radius: var(--app-radius-sm); background: #fff9e8; }
.review-workbench__readonly-banner[data-mode="READ_ONLY"] { border-color: var(--app-line); background: #f5f7f9; }
.review-workbench__readonly-banner strong { color: var(--app-ink); font-size: 12px; }
.review-workbench__readonly-banner p { margin: 0; color: var(--app-muted); font-size: 11px; line-height: 1.55; }
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
.review-workbench :deep(.review-action-bar) { position: sticky; z-index: 18; top: 104px; margin-top: 12px; box-shadow: 0 12px 28px rgba(30, 52, 78, .12); }
.review-workbench__layout { display: block; margin-top: 16px; }
.review-workbench__left,
.review-workbench__right { display: none; }
.review-workbench__left--open { position: fixed; z-index: 50; inset: 16px auto 16px 16px; display: grid; width: min(360px, calc(100vw - 32px)); max-height: none; gap: 16px; overflow: auto; padding: 18px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #f7f8fb; box-shadow: 0 18px 50px rgba(33, 48, 74, .22); }
.review-workbench__center { min-width: 0; width: 100%; }
.review-workbench__right--open { position: fixed; z-index: 50; inset: 16px 16px 16px auto; display: grid; align-content: start; width: min(460px, calc(100vw - 32px)); max-height: none; gap: 10px; overflow: auto; padding: 18px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #fff; box-shadow: 0 18px 50px rgba(33, 48, 74, .22); }
.review-workbench__finding-frame { padding: 0; overflow: hidden; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fff; }
.review-workbench__finding-queue { display: grid; gap: 9px; margin-bottom: 10px; padding: 12px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #f8fafc; }
.review-workbench__finding-queue-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.review-workbench__finding-queue-heading > div { display: grid; gap: 2px; }
.review-workbench__finding-queue-heading span { color: var(--app-accent-deep); font-size: 9px; font-weight: 900; letter-spacing: .12em; }
.review-workbench__finding-queue-heading strong { color: var(--app-ink); font-size: 13px; }
.review-workbench__finding-queue-heading small { color: var(--app-muted); font-size: 10px; }
.review-workbench__finding-tabs { display: grid; gap: 6px; max-height: 188px; overflow: auto; }
.review-workbench__finding-tabs button { display: grid; gap: 3px; width: 100%; padding: 8px 9px; border: 1px solid transparent; border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; text-align: left; }
.review-workbench__finding-tabs button:hover,
.review-workbench__finding-tabs button.is-selected { border-color: rgba(200, 91, 67, .24); color: var(--app-accent-deep); background: var(--app-accent-soft); }
.review-workbench__finding-tabs span { font-size: 11px; font-weight: 800; line-height: 1.4; }
.review-workbench__finding-tabs small { color: var(--app-muted); font-size: 9px; }
.review-workbench__panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.review-workbench__panel-heading p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 9px; font-weight: 900; letter-spacing: .14em; }
.review-workbench__panel-heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 21px; }
.review-workbench__panel-heading button,
.review-workbench__drawer-close { display: grid; width: 42px; height: 42px; place-items: center; border: 0; border-radius: 8px; color: var(--app-ink-soft); background: transparent; cursor: pointer; }
.review-workbench__drawer-close { position: absolute; z-index: 1; top: 8px; right: 8px; }
.review-workbench__case-facts { display: grid; gap: 10px; margin: 0; }
.review-workbench__case-facts div { display: grid; gap: 3px; }
.review-workbench__case-facts dt { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.review-workbench__case-facts dd { margin: 0; color: var(--app-ink); font-size: 13px; font-weight: 800; overflow-wrap: anywhere; }
.review-workbench__provenance-facts { gap: 8px; }
.review-workbench__fingerprint { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px !important; word-break: break-all; }
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
.review-workbench__drawer-backdrop { position: fixed; z-index: 49; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(23, 34, 56, .24); cursor: default; }
.review-workbench__empty { max-width: 720px; margin: 28px auto; }

@media (max-width: 1180px) {
  .review-workbench { padding-inline: 18px; }
  .review-workbench__source-strip { grid-template-columns: minmax(0, 1fr) auto; }
  .review-workbench__source-stats { grid-column: 1 / -1; grid-row: 2; justify-content: flex-start; }
  .review-workbench__source-actions { grid-column: 2; grid-row: 1; }
}

@media (max-width: 980px) {
  .review-workbench :deep(.review-action-bar) { position: static; margin-top: 12px; box-shadow: none; }
  .review-workbench__diff-grid { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .review-workbench { padding-inline: 14px; }
  .review-workbench__source-strip { grid-template-columns: 1fr; align-items: stretch; gap: 10px; }
  .review-workbench__source-main { align-items: flex-start; flex-direction: column; }
  .review-workbench__source-stats { grid-column: auto; grid-row: auto; justify-content: flex-start; white-space: normal; }
  .review-workbench__source-actions { grid-column: auto; grid-row: auto; align-items: stretch; flex-direction: column; }
  .review-workbench__source-actions button { width: 100%; }
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
