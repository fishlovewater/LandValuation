<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import { useAuthStore } from '../../../stores/auth.store'
import type { DocumentTextPreviewDto } from '../../../types/documentPreview'
import type { SpreadsheetPreviewDto } from '../../../types/spreadsheet'
import { statusLabel } from '../../../utils/enumLabels'
import { userStructuredValue } from '../../../utils/fieldLabels'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import { valuationStageFromRouteName, valuationStageRoute } from '../valuation.navigation'
import { newTaipeiDistrictName } from '../newTaipei'
import {
  analysisProviderLabel,
  extractedFieldStatusLabel,
  valuationFieldLabel,
} from '../valuation.labels'
import {
  mapBenchmarkLandResponse,
  mapCalculationResponse,
  mapCaseResponse,
  mapDocumentResponse,
  mapF03DraftResponse,
  mapF03Update,
  mapFormResponse,
  mapReportResponse,
  mapValidationResponse,
  selectAuthoritativeF02,
  sourceForCalculatedValue,
} from '../valuation.mappers'
import {
  resetValuationFlow,
  valuationFlowState,
  type AutomatedCandidateConfirmationDto,
  type AutomatedWorkflowResponseDto,
  type BenchmarkLandCreateDto,
  type DocumentCategory,
  type DocumentArtifactModel,
  type ExtractedFieldResponseDto,
  type F03EditableValues,
  type ParcelImportPreviewDto,
  type ParcelImportRowDto,
  type ParcelCreateDto,
  type ParcelResponseDto,
  type ReportPageCode,
  type ReportProgressResponseDto,
  type ValidationFindingModel,
  type ValuationLocationDto,
  type ValuationReviewHandoffDto,
  type ValuationFormModel,
} from '../valuation.types'
import ValuationCaseWorkspaceHeader, { type ValuationWorkspaceStage } from '../components/ValuationCaseWorkspaceHeader.vue'
import ValuationCaseOverview from '../components/ValuationCaseOverview.vue'
import ValuationDataStageNavigator from '../components/ValuationDataStageNavigator.vue'
import ValuationIssueDrawer from '../components/ValuationIssueDrawer.vue'
import ValuationWizardFooter from '../components/ValuationWizardFooter.vue'
import ValuationWorkflowStatus from '../components/ValuationWorkflowStatus.vue'
import ValuationDocumentStage from '../components/ValuationDocumentStage.vue'
import ValuationCandidateWorkspace from '../components/ValuationCandidateWorkspace.vue'
import ValuationManualFieldsSection from '../components/ValuationManualFieldsSection.vue'
import ValuationLandContext from '../components/ValuationLandContext.vue'
import ValuationF03Section from '../components/ValuationF03Section.vue'
import ValuationValidationSection from '../components/ValuationValidationSection.vue'
import ValuationReviewHandoffPanel from '../components/ValuationReviewHandoffPanel.vue'

const props = defineProps<{
  stage?: Exclude<ValuationWorkspaceStage, 'report'>
}>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const flow = valuationFlowState
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const uploading = ref(false)
const dirty = ref(false)
const error = ref('')
const notice = ref('')
const workflowGuidance = ref<AutomatedWorkflowResponseDto | null>(null)
const reviewHandoff = ref<ValuationReviewHandoffDto | null>(null)
const reportProgress = ref<ReportProgressResponseDto | null>(null)
const revisionInitializing = ref(false)
const uploadCategory = ref<DocumentCategory>('original')
const uploadFile = ref<File | null>(null)
const parcels = ref<ParcelResponseDto[]>([])
const locations = ref<ValuationLocationDto[]>([])
const activeLocationId = ref<string | null>(null)
const newLocationLabel = ref('')
const extractionCandidates = ref<ExtractedFieldResponseDto[]>([])
const extractionBusyDocumentId = ref<string | null>(null)
const confirmingCandidates = ref(false)
const candidateDecision = reactive<Record<string, 'CONFIRM' | 'REJECT' | ''>>({})
const candidateValue = reactive<Record<string, string>>({})
const manualFieldValue = reactive<Record<string, string>>({})
const manualFieldsSaving = ref(false)
const documentActionId = ref<string | null>(null)
const documentCategoryDraft = reactive<Record<string, DocumentCategory>>({})
type FieldAnalysisFormCode = 'S01' | 'F01' | 'F02' | 'F02-RF' | 'F03' | 'F04'
const activeManualForm = ref<FieldAnalysisFormCode>('F03')
const documentAnalysisForm = reactive<Record<string, FieldAnalysisFormCode>>({})
const landContextSaving = ref(false)
const editingParcelId = ref<string | null>(null)
type WizardStep = 1 | 2 | 3 | 4
type DataSection = 'overview' | 'manual' | 'land' | 'f03'
const activeWizardStep = ref<WizardStep>(1)
const activeIntakeStage = ref<'documents' | 'ai-review'>('documents')
const activeDataSection = ref<DataSection>('overview')
const confirmingCaseInfo = ref(false)
const workspacePersistenceReady = ref(false)
const lastPersistedWorkspaceStage = ref<ValuationWorkspaceStage | null>(null)
let workspaceUrlSyncSerial = 0
let workspaceUrlSyncInFlight = false
const previewDocumentId = ref<string | null>(null)
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const previewPage = ref<number | null>(null)
const spreadsheetPreview = ref<SpreadsheetPreviewDto | null>(null)
const textPreview = ref<DocumentTextPreviewDto | null>(null)
const selectedCandidateId = ref<string | null>(null)
const parcelImportPreview = ref<ParcelImportPreviewDto | null>(null)
const parcelImportLoading = ref(false)
const parcelImporting = ref(false)
const activeLocation = computed(() => (
  locations.value.find((item) => item.location_id === activeLocationId.value) ?? null
))
const locationDocuments = computed(() => activeLocationId.value
  ? flow.documents.filter((item) => item.locationId === activeLocationId.value)
  : flow.documents)
const locationParcels = computed(() => activeLocationId.value
  ? parcels.value.filter((item) => item.location_id === activeLocationId.value)
  : parcels.value)

const FORM_DISPLAY_NAMES: Readonly<Record<string, string>> = {
  S01: '地價區段勘查表',
  F01: '買賣實例調查估價表',
  F02: '比較法調查估價表',
  'F02-RF': '影響地價區域因素分析明細表',
  F03: '比準地地價估計表',
  F04: '徵收土地宗地市價估計表',
}

function formDisplayName(code: string): string {
  return FORM_DISPLAY_NAMES[code] ?? '查估書表'
}

const FIELD_ANALYSIS_FORM_CODES: readonly FieldAnalysisFormCode[] = [
  'F01',
  'F02',
  'F02-RF',
  'F03',
  'F04',
  'S01',
]

function inferDocumentAnalysisForm(filename: string): FieldAnalysisFormCode {
  if (filename.includes('宗地個別因素') || filename.includes('宗地清冊') || filename.includes('徵收土地清冊')) return 'F04'
  if (filename.includes('買賣實例')) return 'F01'
  if (filename.includes('比較法')) return 'F02'
  if (filename.includes('比準地')) return 'F03'
  if (filename.includes('宗地市價') || filename.includes('土地市價')) return 'F04'
  if (filename.includes('地價區段')) return 'S01'
  return 'F03'
}

function setDocumentAnalysisForm(documentId: string, formCode: FieldAnalysisFormCode): void {
  documentAnalysisForm[documentId] = formCode
}

function setDocumentCategory(documentId: string, category: DocumentCategory): void {
  documentCategoryDraft[documentId] = category
}

function setCandidateValue(candidateId: string, value: string): void {
  candidateValue[candidateId] = value
}

function setManualFieldValue(key: string, value: string): void {
  manualFieldValue[key] = value
}

const parcelDraft = reactive({
  districtCode: '',
  sectionName: '',
  subsectionName: '',
  landNo: '',
  areaSqm: '',
  landUseZone: '',
  designatedUse: '',
  sourceDocumentId: '',
})

const benchmarkDraft = reactive({
  parcelId: '',
  benchmarkLandNo: '',
  priceZoneNo: '',
  landConsolidationSerial: '',
  latitude: '',
  longitude: '',
})

const draft = reactive<F03EditableValues>({
  benchmarkLandId: null,
  comparisonAnalysisId: null,
  valuationBaseDate: null,
  comparisonPrice: null,
  comparisonWeight: null,
  incomePrice: null,
  incomeWeight: null,
  marketPeriodStart: null,
  marketPeriodEnd: null,
  marketCondition: null,
  selectionScopeReason: null,
  decisionReason: null,
})

const caseId = computed(() => String(route.params.caseId ?? ''))
const f03Form = computed<ValuationFormModel | null>(
  () => flow.forms
    .filter((form) => form.formCode === 'F03')
    .reduce<ValuationFormModel | null>(
      (latest, form) => (!latest || form.versionNo > latest.versionNo ? form : latest),
      null,
    ),
)
const isRevisionRequired = computed(() => reviewHandoff.value?.case_status === 'REVISION_REQUIRED')
const latestReportForms = computed(() => {
  const reportId = reportProgress.value?.report_id
  if (!reportId) return []
  return flow.forms.filter((form) =>
    form.reportId === reportId && ['S01', 'F02-RF', 'F02'].includes(form.formCode),
  )
})
const revisionDraftReady = computed(() => Boolean(
  isRevisionRequired.value
    && f03Form.value?.status === 'DRAFT'
    && reportProgress.value?.report_id
    && latestReportForms.value.length === 3
    && latestReportForms.value.every((form) => form.status === 'DRAFT'),
))
const canEditF03 = computed(() => f03Form.value?.status === 'DRAFT')
const canEditLandContext = computed(() => auth.permissions.includes('case.update'))
type CorrectionItem = NonNullable<ValuationReviewHandoffDto['correction']>['items'][number]
type HandoffMissingItem = ValuationReviewHandoffDto['missing_items'][number]
const formalSupplementMissingItems = computed(() =>
  reviewHandoff.value?.missing_items.filter((item) =>
    item.status === 'OPEN' && ['PENDING', 'SENT', 'ACKNOWLEDGED'].includes(item.notification_status ?? ''),
  ) ?? [],
)
const calculatedSource = sourceForCalculatedValue()
const canUpload = computed(() => auth.permissions.includes('document.upload'))
const canPersistWorkspace = computed(() => Boolean(
  flow.case
    && auth.permissions.includes('valuation.update')
    && ['DRAFT', 'PROCESSING', 'CORRECTION', 'REVISION_REQUIRED'].includes(flow.case.status),
))
const canReadAutomatedWorkflow = computed(() => [
  'case.create',
  'case.read',
  'valuation.update',
  'document.upload',
  'document.download',
].every((permission) => auth.permissions.includes(permission)))
const canProceedToSubmit = computed(() => Boolean(flow.validation?.canGenerateReport && flow.report))
const f03Guidance = computed(() => workflowGuidance.value?.form_guidance.find((item) => item.form_code === 'F03') ?? null)
const workflowMissingItems = computed(() => workflowGuidance.value?.missing_items ?? [])
const allCandidates = computed(() => {
  const merged = new Map<string, ExtractedFieldResponseDto>()
  for (const candidate of workflowGuidance.value?.candidates ?? []) {
    merged.set(candidate.extracted_field_id, candidate)
  }
  for (const candidate of extractionCandidates.value) {
    merged.set(candidate.extracted_field_id, candidate)
  }
  const candidates = [...merged.values()]
  if (!activeLocationId.value) return candidates
  return candidates.filter((candidate) => candidate.location_id === activeLocationId.value)
})
const pendingCandidates = computed(() => allCandidates.value.filter(
  (candidate) => candidate.field_status === 'NEEDS_CONFIRMATION',
))
const processedCandidates = computed(() => allCandidates.value.filter(
  (candidate) => ['APPLIED', 'CONFIRMED', 'REJECTED'].includes(candidate.field_status)
    && !candidateDecision[candidate.extracted_field_id],
))
const candidateDecisionTargets = computed(() => allCandidates.value.filter(
  (candidate) => candidate.field_status === 'NEEDS_CONFIRMATION' || Boolean(candidateDecision[candidate.extracted_field_id]),
))
const selectedCandidateCount = computed(() => candidateDecisionTargets.value.filter(
  (candidate) => Boolean(candidateDecision[candidate.extracted_field_id]),
).length)
const selectedCandidate = computed(() => allCandidates.value.find(
  (candidate) => candidate.extracted_field_id === selectedCandidateId.value,
) ?? null)
const previewDocument = computed(() => flow.documents.find(
  (document) => document.documentId === previewDocumentId.value,
) ?? null)
const previewSourceUrl = computed(() => {
  if (!previewUrl.value) return ''
  if (previewDocument.value?.mimeType.toLowerCase() === 'application/pdf' && previewPage.value) {
    return `${previewUrl.value}#page=${previewPage.value}`
  }
  return previewUrl.value
})
const previewIsPdf = computed(() => previewDocument.value?.mimeType.toLowerCase() === 'application/pdf')
const previewIsImage = computed(() => previewDocument.value?.mimeType.toLowerCase().startsWith('image/') ?? false)
const previewIsSpreadsheet = computed(() => {
  const mime = previewDocument.value?.mimeType.toLowerCase()
  return mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    || mime === 'application/vnd.ms-excel'
})
const previewIsDocx = computed(() => previewDocument.value?.mimeType.toLowerCase() === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
function f03DraftHasField(fieldName: string): boolean {
  if (fieldName === 'benchmark_land_id') return Boolean(draft.benchmarkLandId)
  if (fieldName === 'valuation_base_date') return Boolean(draft.valuationBaseDate)
  return false
}
const unresolvedF03RequiredFields = computed(() =>
  (f03Guidance.value?.missing_required_fields ?? []).filter((field) => !f03DraftHasField(field)),
)
const allManualFieldEntries = computed(() => {
  const keys = new Set<string>()
  for (const guidance of workflowGuidance.value?.form_guidance ?? []) {
    for (const field of guidance.missing_required_fields) {
      if (guidance.form_code === 'F03' && f03DraftHasField(field)) continue
      keys.add(`${guidance.form_code}.${field}`)
    }
  }
  for (const [formCode, fields] of Object.entries(workflowGuidance.value?.manual_field_values ?? {})) {
    for (const field of Object.keys(fields)) keys.add(`${formCode}.${field}`)
  }
  // Show the approved manual fields for every form, rather than exposing only
  // whichever form happens to have a current validation error.
  for (const key of Object.keys(MANUAL_FIELD_METADATA)) keys.add(key)
  return [...keys].sort().map((key) => {
    const split = key.indexOf('.')
    return { key, formCode: key.slice(0, split), fieldName: key.slice(split + 1) }
  })
})
const manualFieldEntries = computed(() => allManualFieldEntries.value.filter(
  (entry) => entry.formCode === activeManualForm.value,
))
const manualEditableEntries = computed(() => manualFieldEntries.value.filter(
  (entry) => !(entry.formCode === 'F03' && entry.fieldName === 'benchmark_land_id'),
))
const dataIssueCounts = computed(() => ({
  overview: unresolvedF03RequiredFields.value.length + (!locationParcels.value.length ? 1 : 0) + (!flow.benchmarks.length ? 1 : 0),
  manual: allManualFieldEntries.value.length,
  land: (!locationParcels.value.length ? 1 : 0) + (!flow.benchmarks.length ? 1 : 0),
  f03: unresolvedF03RequiredFields.value.length,
}))
const preCalculationIssueCount = computed(() => dataIssueCounts.value.overview + pendingCandidates.value.length)
const canRunValuation = computed(() => Boolean(
  canEditF03.value
    && flow.f03
    && preCalculationIssueCount.value === 0,
))
const wizardIssueCounts = computed<Partial<Record<WizardStep, number>>>(() => ({
  2: pendingCandidates.value.length + (!flow.documents.length ? 1 : 0),
  3: dataIssueCounts.value.overview,
  4: flow.validation?.failedCount ?? 0,
}))
const workspaceStage = computed<ValuationWorkspaceStage>(() => {
  if (activeWizardStep.value === 1) return 'case'
  if (activeWizardStep.value === 2) return activeIntakeStage.value
  if (activeWizardStep.value === 3) return 'data'
  return 'calculation'
})
const workspaceIssueCounts = computed(() => ({
  documents: flow.documents.length ? 0 : 1,
  'ai-review': pendingCandidates.value.length,
  data: dataIssueCounts.value.overview,
  calculation: flow.validation?.failedCount ?? 0,
  report: canProceedToSubmit.value ? 0 : 1,
}))
const caseProgressPercent = computed(() => {
  let progress = 0
  if (flow.documents.length) progress += 20
  if (allCandidates.value.length && pendingCandidates.value.length === 0) progress += 20
  if (dataIssueCounts.value.overview === 0) progress += 20
  if (flow.validation?.canGenerateReport && flow.report) progress += 20
  return progress
})
const workflowIssues = computed(() => {
  const items: Array<{ id: string; title: string; detail: string; target: string; severity: 'error' | 'warning' | 'pending' }> = []
  if (!flow.documents.length) items.push({ id: 'documents', title: '尚未上傳案件啟動資料', detail: '建議先上傳宗地個別因素清冊、預定徵收範圍地籍圖與土地登記資料；系統會保留來源並協助辨識可用欄位。', target: 'documents', severity: 'pending' })
  if (pendingCandidates.value.length) items.push({ id: 'candidates', title: '智能辨識結果待確認', detail: `還有 ${pendingCandidates.value.length} 筆辨識結果需要人工確認或修改。`, target: 'candidates', severity: 'warning' })
  if (!parcels.value.length) items.push({ id: 'parcel', title: '尚未建立宗地資料', detail: '建立本案宗地後，才能完成正式估價資料。', target: 'land', severity: 'pending' })
  if (!flow.benchmarks.length) items.push({ id: 'benchmark', title: '尚未建立比準地', detail: '至少需要一筆比準地資料供後續估價流程使用。', target: 'land', severity: 'pending' })
  const missingCount = unresolvedF03RequiredFields.value.length
  if (missingCount) items.push({ id: 'required-fields', title: '必要欄位尚未補齊', detail: `${missingCount} 個必要欄位仍缺值，可直接前往人工補充。`, target: manualFieldEntries.value.length ? 'manual' : 'f03', severity: 'warning' })
  if (dirty.value) items.push({ id: 'unsaved-f03', title: '比準地地價估計表有尚未儲存的修改', detail: '先儲存目前修改，避免後續計算仍使用前一版資料。', target: 'f03', severity: 'warning' })
  if ((flow.validation?.failedCount ?? 0) > 0) items.push({ id: 'validation-errors', title: '正式檢核仍有阻擋錯誤', detail: `有 ${flow.validation?.failedCount ?? 0} 個阻擋錯誤必須修正後才能產出查估書。`, target: 'validation', severity: 'error' })
  return items
})
const wizardStepTitle = computed(() => {
  if (activeWizardStep.value === 1) return '案件基本資料'
  if (activeWizardStep.value === 2) return activeIntakeStage.value === 'documents' ? '文件與辨識' : 'AI 結果確認'
  if (activeWizardStep.value === 3) return '資料補齊'
  return '計算與檢核'
})
const workspaceStepLabel = computed(() => {
  if (workspaceStage.value === 'case') return '案件資料確認'
  const index = ['documents', 'ai-review', 'data', 'calculation', 'report'].indexOf(workspaceStage.value)
  return index >= 0 ? `流程 ${index + 1} / 5` : '案件流程'
})
const wizardNextLabel = computed(() => {
  if (activeWizardStep.value === 1) {
    return flow.case?.basicInfoConfirmedAt ? '下一步：文件與辨識' : '確認並開始估價'
  }
  if (activeWizardStep.value === 2 && activeIntakeStage.value === 'documents') return allCandidates.value.length ? '下一步：AI 結果確認' : '下一步：資料補齊'
  if (activeWizardStep.value === 2) return pendingCandidates.value.length ? `先處理 ${pendingCandidates.value.length} 筆待確認` : '下一步：資料補齊'
  if (activeWizardStep.value === 3) return dataIssueCounts.value.overview ? `尚有 ${dataIssueCounts.value.overview} 項資料待處理` : '下一步：計算與檢核'
  return canProceedToSubmit.value ? '下一步：查估書確認' : '通過檢核後才能繼續'
})
const SOURCE_DOCUMENT_CATEGORIES: readonly DocumentCategory[] = [
  'parcel-factor-list',
  'original',
  'land-register',
  'cadastral-map',
  'photos',
  'attachments',
  'map-section-sketch',
  'map-zoning',
  'map-land-value-section',
]
let activeCaseToken = 0

const FIELD_TARGET_IDS: Readonly<Record<string, string>> = {
  benchmark_land_id: 'f03-benchmark-land',
  valuation_base_date: 'f03-valuation-base-date',
  comparison_price: 'f03-comparison-price',
  comparison_weight: 'f03-comparison-weight',
  income_price: 'f03-income-price',
  income_weight: 'f03-income-weight',
  market_period_start: 'f03-market-period-start',
  market_period_end: 'f03-market-period-end',
  market_condition: 'f03-market-condition',
  selection_scope_reason: 'f03-selection-scope-reason',
  decision_reason: 'f03-decision-reason',
  documents: 'valuation-document-workspace',
  object_key: 'valuation-document-workspace',
  prices: 'f03-comparison-price',
  'case/form/benchmark/date': 'f03-benchmark-land',
  benchmark_land_price: 'run-valuation',
}

const FIELD_LABELS: Readonly<Record<string, string>> = {
  benchmark_land_id: '比準地地價估計表 → 比準地',
  valuation_base_date: '比準地地價估計表 → 估價基準日',
  comparison_price: '比準地地價估計表 → 比準地比較價格',
  comparison_weight: '比準地地價估計表 → 比較價格權重',
  income_price: '比準地地價估計表 → 比準地收益價格',
  income_weight: '比準地地價估計表 → 收益價格權重',
  market_period_start: '比準地地價估計表 → 市場期間起日',
  market_period_end: '比準地地價估計表 → 市場期間迄日',
  market_condition: '比準地地價估計表 → 市場條件',
  selection_scope_reason: '比準地地價估計表 → 選擇範圍理由',
  decision_reason: '比準地地價估計表 → 決定理由',
  documents: '案件與文件 → 來源文件',
  object_key: '案件與文件 → 來源文件儲存狀態',
  prices: '比準地地價估計表 → 比準地比較／收益價格',
  'case/form/benchmark/date': '比準地地價估計表 → 比準地與估價基準日',
  benchmark_land_price: '比準地地價估計表 → 比準地地價',
}

type ManualFieldMetadata = { label: string; guidance: string; inputType?: 'date' | 'text' }

// This workspace contains the formal workflow's required fields, not only AI
// candidates.  Keep their displayed names explicit: a generic "pending field"
// gives the appraiser no usable instruction and was the source of the labels
// shown in the screenshot.
const MANUAL_FIELD_METADATA: Readonly<Record<string, ManualFieldMetadata>> = {
  'F01.transaction_no': { label: '實例編號', guidance: '填寫買賣實例或交易案件編號。' },
  'F01.transaction_date': { label: '交易日期', guidance: '填寫該筆買賣成交日期。格式：YYYY-MM-DD。', inputType: 'date' },
  'F01.transaction_total_price': { label: '交易總價（元）', guidance: '填寫契約或實價登錄的成交總價；可輸入含千分位逗號的金額。' },
  'F01.location': { label: '土地坐落', guidance: '填寫土地所在行政區、段／小段與地號等可辨識的坐落資訊。' },
  'F01.land_area_sqm': { label: '土地面積（㎡）', guidance: '填寫交易標的土地面積，單位為平方公尺。' },

  'S01.administrative_area': { label: '行政區', guidance: '填寫查估區段所在行政區，例如金山區。' },
  'S01.valuation_base_date': { label: '估價基準日', guidance: '填寫本案估價基準日。格式：YYYY-MM-DD。', inputType: 'date' },
  'S01.price_zone_no': { label: '地價區段號', guidance: '填寫地價區段勘查表使用的區段編號。' },
  'S01.zone_boundary_description': { label: '區段範圍說明', guidance: '填寫地價區段的範圍、界線或主要道路描述。' },
  'S01.urban_plan_scope': { label: '都市計畫內外', guidance: '填寫都市計畫內、都市計畫外或原文件記載的範圍。' },
  'S01.land_use_zone_category': { label: '使用分區／使用地類別', guidance: '填寫法定使用分區或使用地類別。' },
  'S01.main_road_name': { label: '區段內主要道路名稱', guidance: '填寫區段內主要道路名稱。' },
  'S01.main_road_width_m': { label: '區段內主要道路寬度（公尺）', guidance: '填寫主要道路寬度，單位為公尺，例如 12.5。' },
  'S01.survey_date': { label: '勘查日期', guidance: '填寫現地勘查日期。格式：YYYY-MM-DD。', inputType: 'date' },

  'F02.parcel_id': { label: '宗地', guidance: '請先在「宗地與比準地」建立或選擇宗地，無須手動輸入系統 ID。' },
  'F02.benchmark_land_no': { label: '比準地地號', guidance: '填寫或選擇比準地的段／小段與地號。' },
  'F02.price_zone_no': { label: '地價區段號', guidance: '填寫比準地所在的地價區段號。' },
  'F02.valuation_base_date': { label: '估價基準日', guidance: '填寫本案估價基準日。格式：YYYY-MM-DD。', inputType: 'date' },

  'F02-RF.benchmark_land_id': { label: '比準地', guidance: '請在「宗地與比準地」建立或選擇比準地，無須手動輸入系統 ID。' },
  'F02-RF.comparison_analysis_id': { label: '比較分析', guidance: '請先建立比較法分析，再回到此處套用。' },
  'F02-RF.comparison_targets': { label: '比較標的（1 至 3）', guidance: '請先完成比較標的資料，再進行區域因素分析。' },
  'F02-RF.confirmed_factor_levels': { label: '區域因素確認值', guidance: '確認每一項區域因素的文件證據或人工判定值。' },
  'F02-RF.rule_version_id': { label: '發布法規版本', guidance: '由系統套用已發布的法規版本，無須手動輸入 ID。' },

  'F03.valuation_base_date': { label: '估價基準日', guidance: '填寫本案估價基準日。格式：YYYY-MM-DD。', inputType: 'date' },
  'F03.benchmark_land_id': { label: '比準地', guidance: '請在「宗地與比準地」建立或選擇比準地，無須手動輸入系統 ID。' },

  'F04.benchmark_valuation_id': { label: '比準地估價結果', guidance: '完成 F03 比準地估價後由系統帶入，無須手動輸入 ID。' },
  'F04.valuation_base_date': { label: '估價基準日', guidance: '填寫本案估價基準日。格式：YYYY-MM-DD。', inputType: 'date' },
  'F04.price_zone_no': { label: '地價區段號', guidance: '填寫宗地所在的地價區段號。' },
}

function manualFieldMetadata(formCode: string, fieldName: string): ManualFieldMetadata {
  const explicit = MANUAL_FIELD_METADATA[`${formCode}.${fieldName}`]
  if (explicit) return explicit
  const label = valuationFieldLabel(fieldName)
  return {
    label,
    guidance: `請依原始文件或正式表單規則確認「${label}」的值。`,
  }
}

function emptyDraft(): F03EditableValues {
  return {
    benchmarkLandId: null,
    comparisonAnalysisId: null,
    valuationBaseDate: null,
    comparisonPrice: null,
    comparisonWeight: null,
    incomePrice: null,
    incomeWeight: null,
    marketPeriodStart: null,
    marketPeriodEnd: null,
    marketCondition: null,
    selectionScopeReason: null,
    decisionReason: null,
  }
}

function clearReactiveRecord(record: Record<string, unknown>): void {
  for (const key of Object.keys(record)) delete record[key]
}

function resetParcelDraft(): void {
  editingParcelId.value = null
  Object.assign(parcelDraft, {
    districtCode: flow.case?.districtCode ?? '',
    sectionName: '',
    subsectionName: '',
    landNo: '',
    areaSqm: '',
    landUseZone: '',
    designatedUse: '',
    sourceDocumentId: '',
  })
}

function resetBenchmarkDraft(): void {
  Object.assign(benchmarkDraft, {
    parcelId: locationParcels.value[0]?.parcel_id ?? '',
    benchmarkLandNo: '',
    priceZoneNo: '',
    landConsolidationSerial: '',
    latitude: '',
    longitude: '',
  })
}

function displayCandidateValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'bigint') return String(value)
  return userStructuredValue(value)
}

function fieldDisplayLabel(formCode: string, fieldName: string): string {
  const manualLabel = MANUAL_FIELD_METADATA[`${formCode}.${fieldName}`]?.label
  if (manualLabel) return manualLabel
  const known = FIELD_LABELS[fieldName]?.replace(/^比準地地價估計表 → /, '')
  if (known) return known
  return valuationFieldLabel(fieldName)
}

function candidateStatusLabel(status: string): string {
  if (status === 'APPLIED') return '已採用'
  if (status === 'REJECTED') return '已略過'
  return extractedFieldStatusLabel(status)
}

function candidateProviderLabel(provider: string): string {
  return analysisProviderLabel(provider)
}

function initializeManualFieldInputs(response: AutomatedWorkflowResponseDto): void {
  const scopedValues = activeLocationId.value
    ? response.manual_field_values_by_location?.[activeLocationId.value] ?? {}
    : {}
  for (const [formCode, fields] of Object.entries(scopedValues)) {
    for (const [fieldName, value] of Object.entries(fields)) {
      manualFieldValue[`${formCode}.${fieldName}`] = displayCandidateValue(value)
    }
  }
  for (const [formCode, fields] of Object.entries(response.manual_field_values ?? {})) {
    for (const [fieldName, value] of Object.entries(fields)) {
      const key = `${formCode}.${fieldName}`
      if (!(key in manualFieldValue)) manualFieldValue[key] = displayCandidateValue(value)
    }
  }
}

function initializeDocumentCategories(): void {
  for (const document of flow.documents) {
    if (SOURCE_DOCUMENT_CATEGORIES.includes(document.documentType as DocumentCategory)) {
      documentCategoryDraft[document.documentId] = document.documentType as DocumentCategory
    }
    documentAnalysisForm[document.documentId] ??= inferDocumentAnalysisForm(document.filename)
  }
}

function candidateDocumentName(documentId: string): string {
  return flow.documents.find((document) => document.documentId === documentId)?.filename ?? '來源文件'
}

function canExtractDocument(document: { mimeType: string; isActive: boolean }): boolean {
  const mime = document.mimeType.toLowerCase()
  return document.isActive && auth.permissions.includes('valuation.update') && (
    mime === 'application/pdf'
    || mime === 'application/vnd.ms-excel'
    || mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  )
}

function canManageSourceDocument(document: { documentType: string; isActive: boolean }): boolean {
  return document.isActive
    && canUpload.value
    && SOURCE_DOCUMENT_CATEGORIES.includes(document.documentType as DocumentCategory)
}

function documentCategoryLabel(category: string): string {
  return ({
    original: '其他原始查估文件',
    'parcel-factor-list': '宗地個別因素清冊',
    'land-register': '土地登記資料',
    'cadastral-map': '地籍圖',
    photos: '照片',
    attachments: '其他附件',
    'map-section-sketch': '地段示意圖',
    'map-zoning': '使用分區圖',
    'map-land-value-section': '地價區段圖',
    'generated-report': '系統產生報告',
    'complete-valuation-report': '完整送審 PDF',
  } as Record<string, string>)[category] ?? '其他文件'
}

function candidateConfidenceLabel(candidate: ExtractedFieldResponseDto): string {
  const confidence = Number(candidate.confidence)
  if (!Number.isFinite(confidence)) return '未提供'
  const percent = confidence <= 1 ? confidence * 100 : confidence
  return `${percent.toFixed(percent >= 10 ? 0 : 1)}%`
}

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '大小未知'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function documentCandidateCount(documentId: string): number {
  return allCandidates.value.filter((candidate) => candidate.document_id === documentId).length
}

function documentPendingCount(documentId: string): number {
  return pendingCandidates.value.filter((candidate) => candidate.document_id === documentId).length
}

function documentAiStatus(documentId: string): string {
  const total = documentCandidateCount(documentId)
  const pending = documentPendingCount(documentId)
  if (extractionBusyDocumentId.value === documentId) return '智能辨識中'
  if (!total) return '尚未辨識'
  if (pending) return `${total} 欄位 · ${pending} 待確認`
  return `${total} 欄位 · 已完成確認`
}

function canPreviewDocument(document: DocumentArtifactModel): boolean {
  const mime = document.mimeType.toLowerCase()
  return mime === 'application/pdf'
    || mime.startsWith('image/')
    || mime === 'application/vnd.ms-excel'
    || mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    || mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
}

function clearPreviewUrl(): void {
  if (previewUrl.value && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
  spreadsheetPreview.value = null
  textPreview.value = null
}

async function openDocumentPreview(
  documentId: string,
  page: number | null = null,
  switchToDocumentStage = true,
): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const source = flow.documents.find((item) => item.documentId === documentId)
  if (!source || !isCurrentCase(token, requestedCaseId)) return

  if (switchToDocumentStage) {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
  }
  previewDocumentId.value = documentId
  previewPage.value = page
  previewError.value = ''
  clearPreviewUrl()

  if (!canPreviewDocument(source)) {
    previewError.value = '此格式目前可下載，但不提供內嵌預覽。PDF 與圖片可直接在此檢視。'
    return
  }

  previewLoading.value = true
  try {
    if (
      source.mimeType.toLowerCase() === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      || source.mimeType.toLowerCase() === 'application/vnd.ms-excel'
    ) {
      spreadsheetPreview.value = await valuationApi.previewSpreadsheet(requestedCaseId, documentId)
      return
    }
    if (source.mimeType.toLowerCase() === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
      textPreview.value = await valuationApi.previewTextDocument(requestedCaseId, documentId)
      return
    }
    const blob = await valuationApi.downloadDocument(requestedCaseId, documentId)
    if (!isCurrentCase(token, requestedCaseId) || previewDocumentId.value !== documentId) return
    if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
      previewError.value = '目前瀏覽器環境無法建立文件預覽，可改用下載查看。'
      return
    }
    previewUrl.value = URL.createObjectURL(blob)
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) previewError.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId) && previewDocumentId.value === documentId) previewLoading.value = false
  }
}

function goToWorkflowIssue(target: string): void {
  if (target === 'documents') {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    void focusElementById('valuation-document-workspace')
    return
  }
  if (target === 'candidates') {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'ai-review'
    selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? null
    void focusElementById('valuation-candidate-workspace')
    return
  }
  if (target === 'manual' || target === 'land' || target === 'f03') {
    jumpToDataSection(target as DataSection)
    return
  }
  if (target === 'validation') {
    activeWizardStep.value = 4
    void focusElementById('validation-results')
  }
}

async function downloadSourceDocument(document: DocumentArtifactModel): Promise<void> {
  error.value = ''
  try {
    const blob = await valuationApi.downloadDocument(caseId.value, document.documentId)
    if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return
    const url = URL.createObjectURL(blob)
    const anchor = window.document.createElement('a')
    anchor.href = url
    anchor.download = document.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  }
}

function candidateEditorType(candidate: ExtractedFieldResponseDto): 'date' | 'number' | 'text' {
  const field = candidate.field_name.toLowerCase()
  if (field.includes('date')) return 'date'
  if (['price', 'weight', 'rate', 'area', 'sqm', 'latitude', 'longitude', 'amount', 'total'].some((part) => field.includes(part))) {
    return 'number'
  }
  return 'text'
}

function candidateInputType(candidate: ExtractedFieldResponseDto): 'date' | 'text' {
  const editorType = candidateEditorType(candidate)
  if (editorType === 'date') {
    const value = displayCandidateValue(candidate.confirmed_value ?? candidate.extracted_value).trim()
    // ROC dates, dates with units, and other raw OCR formats are deliberately
    // kept as text so the browser does not hide a valid non-ISO value.
    return /^\d{4}-\d{2}-\d{2}$/.test(value) ? 'date' : 'text'
  }
  // Numeric OCR values may contain grouping commas, %, or source units. A
  // text input preserves the actual candidate instead of rendering it blank
  // because HTML type=number rejects formats such as "45,000,000".
  return 'text'
}

function candidateInputMode(candidate: ExtractedFieldResponseDto): 'decimal' | undefined {
  return candidateEditorType(candidate) === 'number' ? 'decimal' : undefined
}

function candidateUnit(candidate: ExtractedFieldResponseDto): string {
  const field = candidate.field_name.toLowerCase()
  if (field.includes('sqm') || field.includes('area')) return 'm²'
  if (field.includes('price') || field.includes('amount') || field.includes('total')) return '元'
  return ''
}

async function openCandidateSource(candidate: ExtractedFieldResponseDto): Promise<void> {
  selectedCandidateId.value = candidate.extracted_field_id
  await openDocumentPreview(candidate.document_id, candidate.source_page ?? null, false)
}

function selectCandidate(candidateId: string): void {
  selectedCandidateId.value = candidateId
  const candidate = allCandidates.value.find((item) => item.extracted_field_id === candidateId)
  if (!candidate) return
  if (
    previewDocumentId.value === candidate.document_id
    && previewPage.value === (candidate.source_page ?? null)
  ) return
  void openDocumentPreview(candidate.document_id, candidate.source_page ?? null, false)
}

function backToDashboard(): void {
  void router.push({ name: 'valuation-dashboard' })
}

function hasExplicitWorkflowTarget(): boolean {
  return ['step', 'focus', 'field'].some((key) => typeof route.query[key] === 'string')
}

function canonicalRouteStage(): ValuationWorkspaceStage | null {
  return props.stage ?? valuationStageFromRouteName(route.name)
}

function syncWorkspaceUrl(stage: ValuationWorkspaceStage): void {
  if (!caseId.value || canonicalRouteStage() === stage) return
  const serial = ++workspaceUrlSyncSerial
  workspaceUrlSyncInFlight = true
  void router.replace(valuationStageRoute(caseId.value, stage, route.query))
    .catch(() => undefined)
    .finally(() => {
      if (serial !== workspaceUrlSyncSerial) return
      workspaceUrlSyncInFlight = false
      const currentStage = workspaceStage.value
      if (canonicalRouteStage() !== currentStage) syncWorkspaceUrl(currentStage)
    })
}

function applyWorkspaceStage(stage: ValuationWorkspaceStage): ValuationWorkspaceStage {
  if (stage === 'case') {
    activeWizardStep.value = 1
    return 'case'
  }
  if (stage === 'documents') {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    return 'documents'
  }
  if (stage === 'ai-review') {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'ai-review'
    selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? selectedCandidateId.value
    return 'ai-review'
  }
  if (stage === 'data') {
    activeWizardStep.value = 3
    activeDataSection.value = 'overview'
    return 'data'
  }
  if (stage === 'calculation') {
    if (!canRunValuation.value) {
      activeWizardStep.value = 3
      activeDataSection.value = 'overview'
      return 'data'
    }
    activeWizardStep.value = 4
    return 'calculation'
  }
  if (!canProceedToSubmit.value) {
    return applyWorkspaceStage(canRunValuation.value ? 'calculation' : 'data')
  }
  return 'report'
}

async function persistWorkspaceStage(stage: ValuationWorkspaceStage): Promise<void> {
  if (
    stage === 'case'
    || !workspacePersistenceReady.value
    || !flow.case?.basicInfoConfirmedAt
    || !canPersistWorkspace.value
    || lastPersistedWorkspaceStage.value === stage
  ) return
  try {
    const updated = await valuationApi.updateCaseWorkspace(caseId.value, {
      last_workspace_stage: stage,
    })
    flow.case = mapCaseResponse(updated)
    lastPersistedWorkspaceStage.value = stage
  } catch {
    // Navigation must remain usable if the case changes to a non-editable state
    // while it is open. The next successful editable transition will retry.
  }
}

async function confirmCaseInfoAndStart(): Promise<void> {
  if (!flow.case || confirmingCaseInfo.value || !canPersistWorkspace.value) return
  confirmingCaseInfo.value = true
  error.value = ''
  notice.value = ''
  try {
    const updated = await valuationApi.updateCaseWorkspace(caseId.value, {
      confirm_basic_info: true,
      last_workspace_stage: 'documents',
    })
    flow.case = mapCaseResponse(updated)
    lastPersistedWorkspaceStage.value = 'documents'
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    notice.value = '案件基本資料已確認，可以開始上傳與辨識來源文件。'
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    confirmingCaseInfo.value = false
  }
}

function navigateWorkspaceStage(stage: ValuationWorkspaceStage): void {
  if (stage !== 'case' && !flow.case?.basicInfoConfirmedAt) {
    notice.value = '請先確認案件基本資料，再開始估價流程。'
    activeWizardStep.value = 1
    return
  }
  const applied = applyWorkspaceStage(stage)
  if (applied === 'documents') {
    void focusElementById('valuation-document-workspace')
  }
  if (applied === 'ai-review') {
    void focusElementById('valuation-candidate-workspace')
  }
  if (applied === 'report') {
    void goToSubmit()
    return
  }
  syncWorkspaceUrl(applied)
  void persistWorkspaceStage(applied)
}

function jumpToDataSection(section: DataSection): void {
  activeWizardStep.value = 3
  activeDataSection.value = section
}

function jumpToFirstDataIssue(): void {
  if (manualFieldEntries.value.length) jumpToDataSection('manual')
  else if (!parcels.value.length || !flow.benchmarks.length) jumpToDataSection('land')
  else jumpToDataSection('f03')
}

function wizardPrevious(): void {
  if (activeWizardStep.value <= 1) return
  if (activeWizardStep.value === 2 && activeIntakeStage.value === 'ai-review') {
    activeIntakeStage.value = 'documents'
    return
  }
  activeWizardStep.value = Math.max(1, activeWizardStep.value - 1) as WizardStep
}

async function wizardNext(): Promise<void> {
  if (activeWizardStep.value === 1) {
    if (!flow.case?.basicInfoConfirmedAt) {
      await confirmCaseInfoAndStart()
      return
    }
    navigateWorkspaceStage('documents')
    return
  }
  if (activeWizardStep.value === 2) {
    if (activeIntakeStage.value === 'documents') {
      if (allCandidates.value.length || pendingCandidates.value.length) {
        navigateWorkspaceStage('ai-review')
        selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? allCandidates.value[0]?.extracted_field_id ?? null
        return
      }
      navigateWorkspaceStage('data')
      return
    }
    if (pendingCandidates.value.length) {
      selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? null
      notice.value = `還有 ${pendingCandidates.value.length} 筆智能辨識結果待確認，先完成確認再進入正式資料。`
      void focusElementById('valuation-candidate-workspace')
      return
    }
    navigateWorkspaceStage('data')
    return
  }
  if (activeWizardStep.value === 3) {
    if (dataIssueCounts.value.overview) {
      notice.value = `目前仍有 ${dataIssueCounts.value.overview} 項資料待處理，已帶你前往第一個待處理區域。`
      jumpToFirstDataIssue()
      return
    }
    navigateWorkspaceStage('calculation')
    return
  }
  if (activeWizardStep.value === 4) {
    if (canProceedToSubmit.value) goToSubmit()
    else notice.value = '請先完成計算與檢核，並處理所有待修正項目。'
  }
}

function initializeCandidateInputs(candidates: ExtractedFieldResponseDto[]): void {
  for (const candidate of candidates) {
    if (!(candidate.extracted_field_id in candidateValue)) {
      candidateValue[candidate.extracted_field_id] = displayCandidateValue(
        candidate.confirmed_value ?? candidate.extracted_value,
      )
    }
    if (!(candidate.extracted_field_id in candidateDecision)) {
      candidateDecision[candidate.extracted_field_id] = ''
    }
  }
}

function isCurrentCase(token: number, requestedCaseId: string): boolean {
  return token === activeCaseToken && requestedCaseId === caseId.value
}

function copyDraft(): void {
  if (!flow.f03) return
  Object.assign(draft, flow.f03.editable)
  dirty.value = false
}

async function loadF03(form: ValuationFormModel, token: number, requestedCaseId: string): Promise<void> {
  const dto = await valuationApi.getF03(requestedCaseId, form.formInstanceId)
  if (!isCurrentCase(token, requestedCaseId)) return
  flow.f03 = mapF03DraftResponse(dto, form.sourceDocumentId, form.formInstanceId)
  copyDraft()
}

async function loadWorkflowGuidance(token = activeCaseToken, requestedCaseId = caseId.value): Promise<void> {
  if (!canReadAutomatedWorkflow.value || !isCurrentCase(token, requestedCaseId)) {
    workflowGuidance.value = null
    return
  }
  try {
    const response = await valuationApi.getWorkflowReview(requestedCaseId)
    if (isCurrentCase(token, requestedCaseId)) {
      workflowGuidance.value = response
      initializeCandidateInputs(response.candidates)
      initializeManualFieldInputs(response)
    }
  } catch {
    // The workflow helper only exists for cases initialized through the automated
    // intake. The regular valuation flow remains usable when it is unavailable.
    if (isCurrentCase(token, requestedCaseId)) workflowGuidance.value = null
  }
}

async function loadReviewHandoff(token = activeCaseToken, requestedCaseId = caseId.value): Promise<void> {
  if (!isCurrentCase(token, requestedCaseId)) return
  try {
    const response = await valuationApi.getReviewHandoff(requestedCaseId)
    if (isCurrentCase(token, requestedCaseId)) reviewHandoff.value = response
  } catch {
    // The handoff is supplemental for ordinary draft cases. Do not block the
    // valuation editor if an older backend does not expose it yet.
    if (isCurrentCase(token, requestedCaseId)) reviewHandoff.value = null
  }
}

function editableReportPagePayload(
  pageCode: ReportPageCode,
  data: Record<string, unknown>,
): Record<string, unknown> {
  const allowed: Record<ReportPageCode, readonly string[]> = {
    S01: [
      'district_name', 'district_boundary', 'survey_date', 'urban_plan_status',
      'land_use_zone', 'building_coverage_rate', 'floor_area_ratio',
      'prohibited_building', 'restricted_building', 'main_road_name',
      'main_road_width_m', 'average_road_width_m', 'observations', 'notes',
      'site_opinion', 'handler_name', 'section_head_name', 'director_name',
      'appraiser_name',
    ],
    'F02-RF': [
      'benchmark_land_id', 'comparison_analysis_id', 'rule_version_id',
      'factor_rows', 'other_influences', 'notes', 'appraiser_name',
    ],
    F02: [
      'benchmark_land_id', 'comparison_analysis_id', 'comparison_targets',
      'benchmark_notes', 'notes', 'handler_name', 'section_head_name',
      'director_name', 'appraiser_name',
    ],
  }
  return Object.fromEntries(
    allowed[pageCode]
      .filter((key) => Object.prototype.hasOwnProperty.call(data, key))
      .map((key) => [key, data[key]]),
  )
}

async function ensureRevisionDrafts(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (!isRevisionRequired.value || revisionInitializing.value || !isCurrentCase(token, requestedCaseId)) return

  revisionInitializing.value = true
  error.value = ''
  notice.value = ''
  try {
    const currentF03 = f03Form.value
    const f03SourceValues = flow.f03 ? { ...flow.f03.editable } : null
    const currentReportId = reportProgress.value?.report_id ?? null
    const reportSourcePages = currentReportId
      ? await Promise.all(
          (['S01', 'F02-RF', 'F02'] as ReportPageCode[]).map((pageCode) =>
            valuationApi.getReportPage(requestedCaseId, currentReportId, pageCode),
          ),
        )
      : []

    if (!currentF03 || currentF03.status !== 'DRAFT') {
      if (!f03SourceValues?.benchmarkLandId || !f03SourceValues.valuationBaseDate) {
        throw new Error('F03_SOURCE_VALUES_REQUIRED')
      }
      const createdF03 = await valuationApi.createForm(requestedCaseId, {
        form_code: 'F03',
        prepared_date: currentF03?.preparedDate ?? flow.case?.valuationBaseDate ?? null,
        source_document_id: currentF03?.sourceDocumentId ?? null,
      })
      await valuationApi.updateF03(
        requestedCaseId,
        createdF03.form_instance_id,
        mapF03Update(f03SourceValues),
      )
    }

    const reportIsEditable = Boolean(
      currentReportId
        && latestReportForms.value.length === 3
        && latestReportForms.value.every((form) => form.status === 'DRAFT'),
    )
    if (!reportIsEditable) {
      const createdPackage = await valuationApi.createReportPackage(requestedCaseId, {
        report_type: 'REPORT_COMPARISON_COMMERCIAL',
        prepared_date: latestReportForms.value[0]?.preparedDate ?? flow.case?.valuationBaseDate ?? null,
      })
      for (const sourcePage of reportSourcePages) {
        const payload = editableReportPagePayload(sourcePage.page_code, sourcePage.data)
        if (Object.keys(payload).length) {
          await valuationApi.updateReportPage(
            requestedCaseId,
            createdPackage.report_id,
            sourcePage.page_code,
            payload,
          )
        }
      }
    }

    await loadData()
    if (isCurrentCase(activeCaseToken, requestedCaseId)) {
      notice.value = '補正版已建立：比準地地價估計表、地價區段勘查表、影響地價區域因素分析明細表（商業用地）與比較法調查估價表都已建立新的可編輯草稿，可依修正通知逐項修改。'
      activeWizardStep.value = 3
      activeDataSection.value = 'f03'
      void focusElementById('f03-data-section')
    }
  } catch (caught: unknown) {
    if (caught instanceof Error && caught.message === 'F03_SOURCE_VALUES_REQUIRED') {
      error.value = '舊版比準地地價估計表缺少比準地或估價基準日，無法安全複製；請先確認來源資料。'
    } else {
      error.value = safeValuationErrorMessage(caught)
    }
  } finally {
    revisionInitializing.value = false
  }
}

function findingFieldCodes(finding: ValidationFindingModel): string[] {
  if (finding.fieldPath === 'prices') return ['comparison_price', 'income_price']
  if (finding.fieldPath === 'case/form/benchmark/date') return ['valuation_base_date', 'benchmark_land_id']
  if (finding.fieldPath) return finding.fieldPath.split(',').map((item) => item.trim()).filter(Boolean)
  if (finding.ruleCode === 'F03_REQUIRED_FIELDS') return ['benchmark_land_id', 'valuation_base_date']
  if (finding.ruleCode === 'F03_REQUIRED_DOCUMENTS' || finding.ruleCode === 'F03_MINIO_OBJECTS') return ['documents']
  if (finding.ruleCode === 'F03_CALCULATION_MATCH') return ['benchmark_land_price']
  return []
}

function findingLocationLabel(finding: ValidationFindingModel): string {
  const codes = findingFieldCodes(finding)
  if (!codes.length) return '比準地地價估計表檢核資料'
  return codes.map((code) => FIELD_LABELS[code] ?? '比準地地價估計表相關欄位').join('、')
}

function findingCorrectionHint(finding: ValidationFindingModel): string {
  if (finding.ruleCode === 'F03_CALCULATION_MATCH') {
    return '此欄位由系統計算。請先修正相關資料，再重新執行「計算與檢核」。'
  }
  if (finding.ruleCode === 'F03_REQUIRED_DOCUMENTS' || finding.ruleCode === 'F03_MINIO_OBJECTS') {
    return '請到來源文件區補上或重新上傳缺少的文件，完成後再執行檢核。'
  }
  if (finding.ruleCode === 'F03_WEIGHT_SUM') {
    return '請調整比較法與收益法權重，使各自介於 0～1 且合計為 1。'
  }
  if (finding.ruleCode === 'F03_METHOD_INPUTS') {
    return '權重大於 0 的估價方法必須有對應價格；補值後重新計算。'
  }
  if (finding.ruleCode === 'F03_PRICE_RANGE') return '價格不可小於 0，請修正價格欄位。'
  if (finding.ruleCode === 'F03_REQUIRED_FIELDS') return '請補齊比準地與估價基準日。'
  return finding.message
}

async function focusElementById(targetId: string, message?: string): Promise<void> {
  await nextTick()
  const target = document.getElementById(targetId)
  if (!target) return
  target.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  const focusable = target.matches('input, select, textarea, button')
    ? target as HTMLElement
    : target.querySelector<HTMLElement>('input, select, textarea, button')
  focusable?.focus()
  if (message) notice.value = message
}

function goToFinding(finding: ValidationFindingModel): void {
  const fieldCode = findingFieldCodes(finding)[0]
  const targetId = fieldCode ? FIELD_TARGET_IDS[fieldCode] : undefined
  if (!targetId) {
    notice.value = `請依檢核訊息處理：${finding.message}`
    return
  }
  if (fieldCode === 'documents' || fieldCode === 'object_key') {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
  } else {
    activeWizardStep.value = 3
    activeDataSection.value = 'f03'
  }
  void focusElementById(targetId, `${findingLocationLabel(finding)}：${findingCorrectionHint(finding)}`)
}

function goToWorkflowNextAction(): void {
  if (isRevisionRequired.value) {
    if (!revisionDraftReady.value) {
      void ensureRevisionDrafts()
      return
    }
    activeWizardStep.value = 3
    activeDataSection.value = 'f03'
    void focusElementById('f03-data-section', '補正版已建立，請依修正通知逐項調整資料。')
    return
  }
  if (workflowGuidance.value?.pending_candidate_count) {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'ai-review'
    selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? null
    void focusElementById('valuation-candidate-workspace', '目前仍有待確認的辨識結果；請逐筆確認、修正後採用，或標記不採用。')
    return
  }
  if (workflowMissingItems.value.some((item) => item.toLowerCase().includes('document'))) {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    void focusElementById('valuation-document-workspace')
    return
  }
  if (flow.validation && !flow.validation.canGenerateReport) {
    activeWizardStep.value = 4
    void focusElementById('validation-title')
    return
  }
  if (canProceedToSubmit.value) {
    goToSubmit()
    return
  }
  if (!parcels.value.length || !flow.benchmarks.length) {
    activeWizardStep.value = 3
    activeDataSection.value = 'land'
    void focusElementById('valuation-land-context', '請先補齊宗地與比準地資料。')
    return
  }
  if (flow.f03) {
    activeWizardStep.value = 3
    activeDataSection.value = 'f03'
    void focusElementById('f03-data-section')
  } else {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    void focusElementById('valuation-document-workspace')
  }
}

async function goToCorrectionItem(item: CorrectionItem): Promise<void> {
  if (isRevisionRequired.value && !revisionDraftReady.value) {
    await ensureRevisionDrafts()
    if (!revisionDraftReady.value) return
  }
  if (item.document_id) {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    await focusElementById('valuation-document-workspace', `修正要求：${item.requested_correction}`)
    return
  }
  activeWizardStep.value = 3
  activeDataSection.value = 'f03'
  await focusElementById('f03-data-section', `修正要求：${item.requested_correction}`)
}

function goToMissingItem(item: HandoffMissingItem): void {
  if (item.document_type) {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    void focusElementById(
      'valuation-document-workspace',
      `審查要求補件：${item.item_name}${item.reason ? `｜${item.reason}` : ''}`,
    )
    return
  }
  activeWizardStep.value = 3
  activeDataSection.value = 'land'
  void focusElementById(
    'valuation-land-context',
    `審查要求補資料：${item.item_name}${item.reason ? `｜${item.reason}` : ''}`,
  )
}

function focusRequestedRouteTarget(): void {
  const requestedStep = typeof route.query.step === 'string' ? Number(route.query.step) : NaN
  const focus = typeof route.query.focus === 'string' ? route.query.focus : ''
  const field = typeof route.query.field === 'string' ? route.query.field : ''
  if (Number.isInteger(requestedStep) && requestedStep >= 1 && requestedStep <= 4) {
    activeWizardStep.value = requestedStep as WizardStep
  }
  if (focus === 'documents') {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'documents'
    void focusElementById('valuation-document-workspace')
    return
  }
  if (focus === 'candidates') {
    activeWizardStep.value = 2
    activeIntakeStage.value = 'ai-review'
    selectedCandidateId.value = pendingCandidates.value[0]?.extracted_field_id ?? allCandidates.value[0]?.extracted_field_id ?? null
    void focusElementById('valuation-candidate-workspace')
    return
  }
  if (!field) return
  const normalized = field.split(',')[0]?.trim()
  const targetId = normalized ? FIELD_TARGET_IDS[normalized] : undefined
  if (targetId) {
    if (normalized === 'documents' || normalized === 'object_key') {
      activeWizardStep.value = 2
      activeIntakeStage.value = 'documents'
    }
    else {
      activeWizardStep.value = 3
      activeDataSection.value = 'f03'
    }
    void focusElementById(targetId, `請修正 ${FIELD_LABELS[normalized] ?? valuationFieldLabel(normalized)} 後重新執行檢核。`)
  }
}

async function loadData(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = ++activeCaseToken
  resetValuationFlow()
  Object.assign(draft, emptyDraft())
  dirty.value = false
  saving.value = false
  running.value = false
  error.value = ''
  notice.value = ''
  workflowGuidance.value = null
  reviewHandoff.value = null
  reportProgress.value = null
  parcels.value = []
  locations.value = []
  activeLocationId.value = null
  newLocationLabel.value = ''
  extractionCandidates.value = []
  extractionBusyDocumentId.value = null
  confirmingCandidates.value = false
  confirmingCaseInfo.value = false
  workspacePersistenceReady.value = false
  lastPersistedWorkspaceStage.value = null
  clearPreviewUrl()
  previewDocumentId.value = null
  previewPage.value = null
  previewError.value = ''
  selectedCandidateId.value = null
  parcelImportPreview.value = null
  parcelImportLoading.value = false
  parcelImporting.value = false
  clearReactiveRecord(candidateDecision)
  clearReactiveRecord(candidateValue)
  clearReactiveRecord(manualFieldValue)
  clearReactiveRecord(documentCategoryDraft)
  resetParcelDraft()
  resetBenchmarkDraft()

  if (!requestedCaseId) {
    error.value = '找不到案件識別資訊，請從估價案件清單重新進入。'
    loading.value = false
    return
  }

  loading.value = true
  try {
    const [caseDto, parcelDtos, formDtos, benchmarkDtos, documentDtos, reportProgressDto, locationDtos] = await Promise.all([
      valuationApi.getCase(requestedCaseId),
      valuationApi.listParcels(requestedCaseId),
      valuationApi.listForms(requestedCaseId),
      valuationApi.listBenchmarkLands(requestedCaseId),
      valuationApi.listDocuments(requestedCaseId),
      valuationApi.getReportProgress(requestedCaseId),
      valuationApi.listLocations(requestedCaseId).catch(() => [] as ValuationLocationDto[]),
    ])
    if (!isCurrentCase(token, requestedCaseId)) return

    const forms = formDtos.map(mapFormResponse)
    const form = forms
      .filter((item) => item.formCode === 'F03')
      .reduce<ValuationFormModel | null>(
        (latest, item) => (!latest || item.versionNo > latest.versionNo ? item : latest),
        null,
      )
    const documents = documentDtos.map(mapDocumentResponse)
    const authoritative = selectAuthoritativeF02(forms, documents, reportProgressDto)

    flow.case = mapCaseResponse(caseDto)
    parcels.value = parcelDtos
    locations.value = locationDtos
    activeLocationId.value = locationDtos.find((item) => item.is_benchmark_location)?.location_id
      ?? locationDtos[0]?.location_id
      ?? null
    resetParcelDraft()
    resetBenchmarkDraft()
    flow.forms = forms
    flow.benchmarks = benchmarkDtos.map(mapBenchmarkLandResponse)
    flow.documents = documents
    previewDocumentId.value = documents.find((document) => (
      document.isActive
      && (!activeLocationId.value || document.locationId === activeLocationId.value)
    ))?.documentId ?? null
    initializeDocumentCategories()
    flow.authoritativeF02 = authoritative.form
    flow.completeReport = authoritative.completeReport
    flow.reportPackageId = authoritative.reportPackageId
    reportProgress.value = reportProgressDto
    if (form) {
      try {
        await loadF03(form, token, requestedCaseId)
      } catch {
        if (isCurrentCase(token, requestedCaseId)) {
          notice.value = '比準地地價估計表已建立，但正式估價草稿尚未初始化；可先上傳來源文件並補齊宗地／比準地資料。'
        }
      }
    } else {
      notice.value = '目前案件尚未建立比準地地價估計表；可先補齊來源文件，再建立需要的估價表。'
    }
    await Promise.all([
      loadWorkflowGuidance(token, requestedCaseId),
      loadReviewHandoff(token, requestedCaseId),
    ])
    if (isCurrentCase(token, requestedCaseId)) {
      const storedStage = flow.case.lastWorkspaceStage
      let effectiveStage: ValuationWorkspaceStage = 'case'
      const routeStage = canonicalRouteStage()
      if (!flow.case.basicInfoConfirmedAt) {
        applyWorkspaceStage('case')
        if (routeStage && routeStage !== 'case') syncWorkspaceUrl('case')
      } else if (hasExplicitWorkflowTarget()) {
        focusRequestedRouteTarget()
        effectiveStage = workspaceStage.value
      } else if (routeStage && routeStage !== 'report') {
        effectiveStage = applyWorkspaceStage(routeStage)
      } else {
        effectiveStage = applyWorkspaceStage(storedStage)
      }
      lastPersistedWorkspaceStage.value = storedStage
      workspacePersistenceReady.value = true
      if (flow.case.basicInfoConfirmedAt && effectiveStage !== 'case' && effectiveStage !== storedStage) {
        void persistWorkspaceStage(effectiveStage)
      }
      if (effectiveStage === 'report' && canProceedToSubmit.value) goToSubmit()
    }
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) loading.value = false
  }
}

async function addLocation(): Promise<void> {
  if (!flow.case || !newLocationLabel.value.trim()) return
  error.value = ''
  notice.value = ''
  try {
    const created = await valuationApi.createLocation(flow.case.caseId, {
      label: newLocationLabel.value.trim(),
    })
    locations.value = [...locations.value, created]
    newLocationLabel.value = ''
    await changeActiveLocation(created.location_id)
    notice.value = `${created.label} 已建立；後續文件、AI 辨識與宗地資料會歸屬這個地點。`
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  }
}

async function chooseBenchmarkLocation(): Promise<void> {
  if (!flow.case || !activeLocationId.value || activeLocation.value?.is_benchmark_location) return
  error.value = ''
  notice.value = ''
  try {
    const updated = await valuationApi.setBenchmarkLocation(flow.case.caseId, activeLocationId.value)
    locations.value = locations.value.map((item) => ({
      ...item,
      is_benchmark_location: item.location_id === updated.location_id,
    }))
    notice.value = `${updated.label} 已設為比準地來源地點。`
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  }
}

async function changeActiveLocation(locationId: string): Promise<void> {
  activeLocationId.value = locationId
  clearPreviewUrl()
  previewPage.value = null
  selectedCandidateId.value = null
  parcelImportPreview.value = null
  previewDocumentId.value = flow.documents.find(
    (document) => document.isActive && document.locationId === locationId,
  )?.documentId ?? null
  resetParcelDraft()
  resetBenchmarkDraft()
  clearReactiveRecord(manualFieldValue)
  await loadWorkflowGuidance()
}

function handleLocationChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  if (!target.value || target.value === activeLocationId.value) return
  void changeActiveLocation(target.value)
}

function chooseUpload(event: Event | File): void {
  if (event instanceof File) {
    uploadFile.value = event
    return
  }
  const input = event.target as HTMLInputElement
  uploadFile.value = input.files?.[0] ?? null
}

async function uploadSourceDocument(): Promise<void> {
  if (!flow.case || !uploadFile.value || !canUpload.value || uploading.value) return
  const selectedCategory = uploadCategory.value
  uploading.value = true
  error.value = ''
  notice.value = ''
  try {
    const uploaded = await valuationApi.uploadDocument(
      flow.case.caseId,
      selectedCategory,
      uploadFile.value,
      activeLocationId.value,
    )
    flow.documents = [mapDocumentResponse(uploaded), ...flow.documents.filter((item) => item.documentId !== uploaded.document_id)]
    previewDocumentId.value = uploaded.document_id
    initializeDocumentCategories()
    notice.value = `${uploaded.original_filename} 已上傳完成。`
    uploadFile.value = null
    const input = document.querySelector<HTMLInputElement>('#valuation-source-file')
    if (input) input.value = ''
    await loadWorkflowGuidance()
    if (
      selectedCategory === 'parcel-factor-list'
      && [
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      ].includes(uploaded.mime_type.toLowerCase())
    ) {
      await prepareParcelImport(uploaded.document_id)
    }
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    uploading.value = false
  }
}

async function prepareParcelImport(documentId: string): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (parcelImportLoading.value || !isCurrentCase(token, requestedCaseId)) return

  parcelImportLoading.value = true
  error.value = ''
  notice.value = ''
  try {
    const parsed = await valuationApi.previewParcelImport(requestedCaseId, documentId)
    if (!isCurrentCase(token, requestedCaseId)) return
    parcelImportPreview.value = parsed
    previewDocumentId.value = documentId
    notice.value = parsed.candidates.length
      ? `宗地清冊已解析 ${parsed.candidates.length} 筆；可匯入 ${parsed.ready_count} 筆、待確認 ${parsed.needs_confirmation_count} 筆、既有宗地 ${parsed.duplicate_count} 筆。`
      : '宗地清冊已解析，但沒有找到可匯入宗地。'
    await nextTick()
    void focusElementById('parcel-import-panel')
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) {
      parcelImportPreview.value = null
      error.value = safeValuationErrorMessage(caught)
    }
  } finally {
    if (isCurrentCase(token, requestedCaseId)) parcelImportLoading.value = false
  }
}

async function importParcelRows(rows: ParcelImportRowDto[]): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const source = parcelImportPreview.value
  if (
    !source
    || !rows.length
    || parcelImporting.value
    || !canEditLandContext.value
    || !isCurrentCase(token, requestedCaseId)
  ) return

  parcelImporting.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await valuationApi.importParcelsFromDocument(
      requestedCaseId,
      source.document_id,
      { rows },
    )
    if (!isCurrentCase(token, requestedCaseId)) return
    parcels.value = await valuationApi.listParcels(requestedCaseId)
    if (!isCurrentCase(token, requestedCaseId)) return
    resetParcelDraft()
    resetBenchmarkDraft()
    parcelImportPreview.value = await valuationApi.previewParcelImport(
      requestedCaseId,
      source.document_id,
    )
    if (!isCurrentCase(token, requestedCaseId)) return
    await loadWorkflowGuidance(token, requestedCaseId)
    notice.value = result.skipped_duplicate_count
      ? `已建立 ${result.created.length} 筆宗地；另有 ${result.skipped_duplicate_count} 筆與既有宗地重複，未重複建立。`
      : `已由宗地個別因素清冊建立 ${result.created.length} 筆宗地。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) parcelImporting.value = false
  }
}

async function extractDocument(documentId: string): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (
    extractionBusyDocumentId.value
    || !auth.permissions.includes('valuation.update')
    || !isCurrentCase(token, requestedCaseId)
  ) return

  extractionBusyDocumentId.value = documentId
  error.value = ''
  notice.value = ''
  try {
    let result = await valuationApi.startDocumentExtraction(requestedCaseId, documentId)
    if (!isCurrentCase(token, requestedCaseId)) return
    const analysisFailures: string[] = []
    let firstAnalysisError: unknown = null
    if (result.extraction_status === 'COMPLETED') {
      // One click scans all six official form types; the file-type hint never narrows evidence.
      for (const formCode of FIELD_ANALYSIS_FORM_CODES) {
        try {
          result = await valuationApi.analyzeDocumentFields(requestedCaseId, documentId, formCode)
        } catch (analysisError: unknown) {
          analysisFailures.push(formCode)
          firstAnalysisError ??= analysisError
        }
        if (!isCurrentCase(token, requestedCaseId)) return
      }
    }
    extractionCandidates.value = [
      ...extractionCandidates.value.filter((candidate) => candidate.document_id !== documentId),
      ...result.candidates,
    ]
    initializeCandidateInputs(result.candidates)
    await loadWorkflowGuidance(token, requestedCaseId)
    const pending = result.candidates.filter((candidate) => candidate.field_status === 'NEEDS_CONFIRMATION').length
    previewDocumentId.value = documentId
    selectedCandidateId.value = result.candidates.find((candidate) => candidate.field_status === 'NEEDS_CONFIRMATION')?.extracted_field_id
      ?? result.candidates[0]?.extracted_field_id
      ?? null
    const completedCount = FIELD_ANALYSIS_FORM_CODES.length - analysisFailures.length
    notice.value = analysisFailures.length
      ? `文件文字擷取已完成；表單辨識完成 ${completedCount}/${FIELD_ANALYSIS_FORM_CODES.length}，未完成：${analysisFailures.map(formDisplayName).join('、')}。`
      : `六份正式表單辨識完成，找到 ${pending} 筆需要人工確認的欄位；沒有原文證據的欄位已保持空白。`
    if (firstAnalysisError) error.value = safeValuationErrorMessage(firstAnalysisError)
    if (pending) {
      activeIntakeStage.value = 'ai-review'
      void focusElementById('valuation-candidate-workspace')
    }
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) extractionBusyDocumentId.value = null
  }
}

function chooseCandidateDecision(candidateId: string, decision: 'CONFIRM' | 'REJECT'): void {
  candidateDecision[candidateId] = decision
}

function reopenCandidate(candidate: ExtractedFieldResponseDto): void {
  candidateDecision[candidate.extracted_field_id] = 'CONFIRM'
  candidateValue[candidate.extracted_field_id] = displayCandidateValue(
    candidate.confirmed_value ?? candidate.extracted_value,
  )
  void nextTick(() => {
    document.querySelector<HTMLInputElement>(`[data-testid="candidate-value-${candidate.extracted_field_id}"]`)?.focus()
  })
}

function cancelCandidateReopen(candidate: ExtractedFieldResponseDto): void {
  delete candidateDecision[candidate.extracted_field_id]
  candidateValue[candidate.extracted_field_id] = displayCandidateValue(
    candidate.confirmed_value ?? candidate.extracted_value,
  )
  notice.value = '已取消這次重新判定，保留原本已儲存的智能辨識處理結果。'
}

async function submitCandidateDecisions(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (confirmingCandidates.value || !selectedCandidateCount.value || !isCurrentCase(token, requestedCaseId)) return

  const confirmations = candidateDecisionTargets.value.flatMap<AutomatedCandidateConfirmationDto>((candidate) => {
    const decision = candidateDecision[candidate.extracted_field_id]
    if (!decision) return []
    const inputValue = candidateValue[candidate.extracted_field_id] ?? ''
    const originalValue = displayCandidateValue(candidate.extracted_value)
    return [{
      document_id: candidate.document_id,
      extracted_field_id: candidate.extracted_field_id,
      decision,
      ...(decision === 'CONFIRM' && inputValue !== originalValue ? { corrected_value: inputValue } : {}),
    }]
  })
  if (!confirmations.length) return

  confirmingCandidates.value = true
  error.value = ''
  notice.value = ''
  try {
    const response = await valuationApi.confirmWorkflowCandidates(requestedCaseId, {
      confirmations,
      confirm_apply: true,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    workflowGuidance.value = response
    extractionCandidates.value = response.candidates
    for (const confirmation of confirmations) {
      delete candidateDecision[confirmation.extracted_field_id]
      delete candidateValue[confirmation.extracted_field_id]
    }
    initializeCandidateInputs(response.candidates)
    initializeManualFieldInputs(response)
    const form = f03Form.value
    if (form) {
      try {
        await loadF03(form, token, requestedCaseId)
      } catch {
        // Some confirmations are for non-F03 forms or F03 may still lack its
        // two initialization fields. The workflow response remains authoritative.
      }
    }
    notice.value = response.pending_candidate_count
      ? `已儲存本次判定；尚有 ${response.pending_candidate_count} 筆辨識結果需要人工確認。`
      : '辨識結果已全部完成人工判定；可繼續確認正式採用值。'
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) confirmingCandidates.value = false
  }
}

async function saveManualFields(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (manualFieldsSaving.value || !isCurrentCase(token, requestedCaseId)) return

  const values: Record<string, Record<string, unknown>> = {}
  for (const entry of manualEditableEntries.value) {
    const value = (manualFieldValue[entry.key] ?? '').trim()
    if (!value) continue
    ;(values[entry.formCode] ??= {})[entry.fieldName] = value
  }
  if (!Object.keys(values).length) {
    notice.value = '請至少填寫一個人工補充欄位；空白欄位不會儲存。'
    return
  }

  manualFieldsSaving.value = true
  error.value = ''
  notice.value = ''
  try {
    const response = await valuationApi.saveWorkflowManualFields(requestedCaseId, {
      ...(activeLocationId.value ? { location_id: activeLocationId.value } : {}),
      values,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    workflowGuidance.value = response
    extractionCandidates.value = response.candidates
    initializeCandidateInputs(response.candidates)
    initializeManualFieldInputs(response)
    const form = f03Form.value
    if (form) {
      try {
        await loadF03(form, token, requestedCaseId)
      } catch {
        // Manual values may belong only to another form. Keep the workflow
        // response visible even if F03 is not initialized yet.
      }
    }
    const failures = Object.entries(response.manual_field_errors ?? {})
    notice.value = failures.length
      ? `已儲存可套用欄位；另有 ${failures.length} 項無法寫入正式表單，請依下方錯誤修正。`
      : `已儲存 ${response.manual_fields_saved?.length ?? 0} 個人工補充欄位，並重新產生確認資料。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) manualFieldsSaving.value = false
  }
}

async function refreshDocumentsAndWorkflow(token: number, requestedCaseId: string): Promise<void> {
  const documentDtos = await valuationApi.listDocuments(requestedCaseId)
  if (!isCurrentCase(token, requestedCaseId)) return
  flow.documents = documentDtos.map(mapDocumentResponse)
  clearReactiveRecord(documentCategoryDraft)
  initializeDocumentCategories()
  await loadWorkflowGuidance(token, requestedCaseId)
}

async function reclassifyDocument(documentId: string): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const category = documentCategoryDraft[documentId]
  if (!category || documentActionId.value || !isCurrentCase(token, requestedCaseId)) return
  documentActionId.value = documentId
  error.value = ''
  notice.value = ''
  try {
    await valuationApi.reclassifyDocument(requestedCaseId, documentId, category)
    if (!isCurrentCase(token, requestedCaseId)) return
    if (parcelImportPreview.value?.document_id === documentId && category !== 'parcel-factor-list') {
      parcelImportPreview.value = null
    }
    await refreshDocumentsAndWorkflow(token, requestedCaseId)
    notice.value = `文件分類已更新為「${documentCategoryLabel(category)}」。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) documentActionId.value = null
  }
}

async function removeDocument(documentId: string, filename: string): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  if (documentActionId.value || !isCurrentCase(token, requestedCaseId)) return
  if (typeof window !== 'undefined' && !window.confirm(`確定要移除「${filename}」嗎？舊版本仍保留在稽核歷程。`)) return
  documentActionId.value = documentId
  error.value = ''
  notice.value = ''
  try {
    await valuationApi.deleteDocument(requestedCaseId, documentId)
    if (!isCurrentCase(token, requestedCaseId)) return
    if (previewDocumentId.value === documentId) {
      clearPreviewUrl()
      previewDocumentId.value = null
      previewPage.value = null
      selectedCandidateId.value = null
    }
    if (parcelImportPreview.value?.document_id === documentId) {
      parcelImportPreview.value = null
    }
    await refreshDocumentsAndWorkflow(token, requestedCaseId)
    if (!previewDocumentId.value) {
      previewDocumentId.value = flow.documents.find((document) => document.isActive)?.documentId ?? null
    }
    notice.value = `${filename} 已從目前作用中的來源文件移除。`
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) documentActionId.value = null
  }
}

async function downloadConfirmationExport(): Promise<void> {
  const exported = workflowGuidance.value?.confirmation_export
  const requestedCaseId = caseId.value
  if (!exported || !requestedCaseId) return
  error.value = ''
  try {
    const blob = await valuationApi.downloadDocument(requestedCaseId, exported.document_id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = exported.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  }
}

function startParcelEdit(parcel: ParcelResponseDto): void {
  activeWizardStep.value = 3
  activeDataSection.value = 'land'
  editingParcelId.value = parcel.parcel_id
  Object.assign(parcelDraft, {
    districtCode: parcel.district_code,
    sectionName: parcel.section_name,
    subsectionName: parcel.subsection_name,
    landNo: parcel.land_no,
    areaSqm: parcel.area_sqm,
    landUseZone: parcel.land_use_zone ?? '',
    designatedUse: parcel.designated_use ?? '',
    sourceDocumentId: parcel.source_document_id ?? '',
  })
  void focusElementById('parcel-editor')
}

function parcelPayload(): ParcelCreateDto {
  return {
    district_code: parcelDraft.districtCode.trim(),
    section_name: parcelDraft.sectionName.trim(),
    subsection_name: parcelDraft.subsectionName.trim(),
    land_no: parcelDraft.landNo.trim(),
    area_sqm: parcelDraft.areaSqm.trim(),
    land_use_zone: parcelDraft.landUseZone.trim() || null,
    designated_use: parcelDraft.designatedUse.trim() || null,
    source_document_id: parcelDraft.sourceDocumentId || null,
    location_id: activeLocationId.value,
  }
}

async function saveParcel(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const payload = parcelPayload()
  if (
    landContextSaving.value
    || !canEditLandContext.value
    || !payload.district_code
    || !payload.section_name
    || !payload.land_no
    || !payload.area_sqm
    || !isCurrentCase(token, requestedCaseId)
  ) return

  landContextSaving.value = true
  error.value = ''
  notice.value = ''
  try {
    if (editingParcelId.value) {
      await valuationApi.updateParcel(requestedCaseId, editingParcelId.value, payload)
      notice.value = '宗地資料已更新。'
    } else {
      await valuationApi.createParcel(requestedCaseId, payload)
      notice.value = '宗地資料已建立。'
    }
    if (!isCurrentCase(token, requestedCaseId)) return
    parcels.value = await valuationApi.listParcels(requestedCaseId)
    if (!isCurrentCase(token, requestedCaseId)) return
    resetParcelDraft()
    resetBenchmarkDraft()
    await loadWorkflowGuidance(token, requestedCaseId)
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) landContextSaving.value = false
  }
}

function benchmarkPayload(): BenchmarkLandCreateDto {
  return {
    parcel_id: benchmarkDraft.parcelId,
    benchmark_land_no: benchmarkDraft.benchmarkLandNo.trim(),
    price_zone_no: benchmarkDraft.priceZoneNo.trim(),
    land_consolidation_serial: benchmarkDraft.landConsolidationSerial.trim() || null,
    latitude: benchmarkDraft.latitude.trim() || null,
    longitude: benchmarkDraft.longitude.trim() || null,
  }
}

async function saveBenchmarkLand(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const payload = benchmarkPayload()
  if (
    landContextSaving.value
    || !canEditLandContext.value
    || !payload.parcel_id
    || !payload.benchmark_land_no
    || !payload.price_zone_no
    || !isCurrentCase(token, requestedCaseId)
  ) return

  landContextSaving.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await valuationApi.createBenchmarkLand(requestedCaseId, payload)
    if (!isCurrentCase(token, requestedCaseId)) return
    const benchmarkDtos = await valuationApi.listBenchmarkLands(requestedCaseId)
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.benchmarks = benchmarkDtos.map(mapBenchmarkLandResponse)
    resetBenchmarkDraft()

    const form = f03Form.value
    if (form?.status === 'DRAFT' && !flow.f03) {
      await valuationApi.updateF03(requestedCaseId, form.formInstanceId, {
        benchmark_land_id: created.benchmark_land_id,
        valuation_base_date: flow.case?.valuationBaseDate ?? null,
      })
      await loadF03(form, token, requestedCaseId)
      notice.value = '比準地已建立，並以案件基準日初始化比準地地價估計表草稿。'
    } else {
      notice.value = flow.f03
        ? '比準地已建立。既有比準地地價估計表草稿仍保留原比準地，以避免未確認地改寫正式估價來源。'
        : '比準地已建立。'
    }
    await loadWorkflowGuidance(token, requestedCaseId)
  } catch (caught: unknown) {
    if (isCurrentCase(token, requestedCaseId)) error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) landContextSaving.value = false
  }
}

function chooseBenchmarkForF03(benchmarkId: string): void {
  if (!canEditF03.value || !flow.f03) return
  draft.benchmarkLandId = benchmarkId
  dirty.value = true
  activeWizardStep.value = 3
  activeDataSection.value = 'f03'
  notice.value = '已切換比準地地價估計表預計採用的比準地；確認正式資料後請按「儲存確認欄位」。'
  void focusElementById('f03-benchmark-land')
}

async function saveConfirmedFields(
  token = activeCaseToken,
  requestedCaseId = caseId.value,
): Promise<boolean> {
  const form = f03Form.value
  if (!form || !isCurrentCase(token, requestedCaseId)) return false

  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const updated = await valuationApi.updateF03(requestedCaseId, form.formInstanceId, mapF03Update(draft))
    if (!isCurrentCase(token, requestedCaseId)) return false
    flow.f03 = mapF03DraftResponse(updated, form.sourceDocumentId, form.formInstanceId)
    copyDraft()
    await loadWorkflowGuidance(token, requestedCaseId)
    notice.value = '人工確認欄位已儲存。'
    return true
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return false
    error.value = safeValuationErrorMessage(caught)
    return false
  } finally {
    if (isCurrentCase(token, requestedCaseId)) saving.value = false
  }
}

function handleSave(): void {
  void saveConfirmedFields()
}

async function runValuation(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const form = f03Form.value
  if (!form || !flow.f03 || !isCurrentCase(token, requestedCaseId)) return

  if (!canRunValuation.value) {
    notice.value = `計算前還有 ${preCalculationIssueCount.value} 項資料待處理。請先完成必要資料，再執行公式與資料一致性檢核。`
    jumpToFirstDataIssue()
    return
  }

  activeWizardStep.value = 4
  running.value = true
  error.value = ''
  notice.value = ''
  if (form.status === 'DRAFT') flow.calculation = null
  flow.validation = null
  flow.report = null
  try {
    if (dirty.value && !(await saveConfirmedFields(token, requestedCaseId))) return
    if (!isCurrentCase(token, requestedCaseId)) return

    let currentForm = f03Form.value
    if (!currentForm || !flow.f03) return

    if (currentForm.status !== 'DRAFT') {
      notice.value = '目前比準地地價估計表已不是草稿狀態，請重新載入案件後再執行。'
      return
    }

    const calculation = await valuationApi.calculate(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.calculation = mapCalculationResponse(calculation)
    flow.f03 = {
      ...flow.f03,
      benchmarkLandPrice: flow.calculation.result,
      source: sourceForCalculatedValue(),
    }

    const validation = await valuationApi.validate(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.validation = mapValidationResponse(validation)

    if (!flow.validation.canGenerateReport) {
      await loadWorkflowGuidance(token, requestedCaseId)
      notice.value = '檢核發現仍有待修正項目，請修正後重新執行。'
      return
    }

    const submitted = await valuationApi.submitForm(requestedCaseId, currentForm.formInstanceId)
    if (!isCurrentCase(token, requestedCaseId)) return
    const submittedForm = mapFormResponse(submitted)
    flow.forms = flow.forms.map((item) =>
      item.formInstanceId === submittedForm.formInstanceId ? submittedForm : item,
    )
    if (submittedForm.status !== 'READY') {
      notice.value = '比準地地價估計表尚未完成可產生單表輸出的條件，請確認檢核結果。'
      return
    }
    currentForm = f03Form.value
    if (!currentForm || !isCurrentCase(token, requestedCaseId)) return

    const report = await valuationApi.generateReport(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.report = mapReportResponse(report)
    await loadWorkflowGuidance(token, requestedCaseId)
    notice.value = '已完成計算、檢核、比準地地價估計表確認與單表輸出。'
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) running.value = false
  }
}

async function goToSubmit(): Promise<void> {
  if (!canProceedToSubmit.value) {
    notice.value = '目前仍有待修正項目，必須先完成修正並通過檢核，才能進入輸出與送審。'
    return
  }
  await persistWorkspaceStage('report')
  await router.push(valuationStageRoute(caseId.value, 'report'))
}

function openRevisionFields(): void {
  activeWizardStep.value = 3
  activeDataSection.value = 'f03'
  void focusElementById('f03-data-section', '補正版已建立，請依上方修正通知逐項修改。')
}

watch(caseId, () => {
  void loadData()
}, { immediate: true })

watch(workspaceStage, (stage) => {
  syncWorkspaceUrl(stage)
  void persistWorkspaceStage(stage)
})

watch([() => route.name, () => props.stage], () => {
  if (!flow.case || !workspacePersistenceReady.value) return
  if (workspaceUrlSyncInFlight) return
  const routeStage = canonicalRouteStage()
  if (!routeStage || routeStage === 'report') return
  if (!flow.case.basicInfoConfirmedAt && routeStage !== 'case') {
    applyWorkspaceStage('case')
    syncWorkspaceUrl('case')
    return
  }
  if (routeStage === workspaceStage.value) return
  applyWorkspaceStage(routeStage)
})

onBeforeUnmount(clearPreviewUrl)
</script>

<template>
  <div class="valuation-view">
    <LoadingSkeleton v-if="loading" :rows="7" label="案件估價資料載入中" />
    <ErrorState v-else-if="error && !flow.case" :message="error" @retry="loadData" />

    <template v-else-if="flow.case">
      <ValuationCaseWorkspaceHeader
        :case-model="flow.case"
        :district-label="newTaipeiDistrictName(flow.case.districtCode)"
        :status-label="statusLabel(f03Form?.status ?? 'DRAFT')"
        :current-stage="workspaceStage"
        :progress-percent="caseProgressPercent"
        :issue-counts="workspaceIssueCounts"
        :report-available="canProceedToSubmit"
        @back="backToDashboard"
        @navigate="navigateWorkspaceStage"
      />

      <ValuationIssueDrawer
        v-if="flow.case.basicInfoConfirmedAt"
        :items="workflowIssues"
        @select="goToWorkflowIssue"
      />

      <ValuationReviewHandoffPanel
        v-if="reviewHandoff && (reviewHandoff.correction || formalSupplementMissingItems.length)"
        :handoff="reviewHandoff"
        :supplement-missing-items="formalSupplementMissingItems"
        :revision-draft-ready="revisionDraftReady"
        :revision-initializing="revisionInitializing"
        @prepare-revision="ensureRevisionDrafts"
        @open-revision-fields="openRevisionFields"
        @correction-item="goToCorrectionItem"
        @missing-item="goToMissingItem"
      />

      <ValuationWorkflowStatus
        :title="wizardStepTitle"
        :stage-label="workspaceStepLabel"
        :document-count="flow.documents.length"
        :pending-candidate-count="workflowGuidance?.pending_candidate_count"
        :missing-field-count="f03Guidance ? unresolvedF03RequiredFields.length : null"
        :validation-error-count="flow.validation?.failedCount"
        :issue-count="wizardIssueCounts[activeWizardStep] ?? 0"
        @next-action="goToWorkflowNextAction"
      />

      <ValuationCaseOverview
        v-if="activeWizardStep === 1"
        :case-model="flow.case"
        :forms="flow.forms"
        :district-label="newTaipeiDistrictName(flow.case.districtCode)"
      />

      <section
        v-if="activeWizardStep === 2 || activeWizardStep === 3"
        class="location-context"
        aria-label="目前估價地點"
      >
        <div class="location-context__copy">
          <strong>目前估價地點</strong>
          <span>來源文件、AI 辨識、人工補充與宗地資料會依地點分開保存。</span>
        </div>
        <label class="location-context__select">
          <span>切換地點</span>
          <select :value="activeLocationId ?? ''" data-testid="valuation-location-select" @change="handleLocationChange">
            <option v-for="location in locations" :key="location.location_id" :value="location.location_id">
              地點 {{ location.display_order }}｜{{ location.label }}{{ location.is_benchmark_location ? '（比準地）' : '' }}
            </option>
          </select>
        </label>
        <div v-if="canEditLandContext" class="location-context__actions">
          <input
            v-model="newLocationLabel"
            type="text"
            placeholder="新增地點名稱"
            aria-label="新增估價地點名稱"
            @keyup.enter="addLocation"
          >
          <button type="button" :disabled="!newLocationLabel.trim()" @click="addLocation">新增地點</button>
          <button
            type="button"
            :disabled="!activeLocationId || activeLocation?.is_benchmark_location"
            @click="chooseBenchmarkLocation"
          >
            {{ activeLocation?.is_benchmark_location ? '目前為比準地' : '設為比準地' }}
          </button>
        </div>
      </section>

      <ValuationDocumentStage
        v-if="activeWizardStep === 2 && activeIntakeStage === 'documents'"
        :documents="locationDocuments"
        :pending-candidate-count="pendingCandidates.length"
        :preview-document-id="previewDocumentId"
        :preview-document="previewDocument"
        :preview-page="previewPage"
        :preview-loading="previewLoading"
        :preview-error="previewError"
        :preview-source-url="previewSourceUrl"
        :preview-is-pdf="previewIsPdf"
        :preview-is-image="previewIsImage"
        :preview-is-spreadsheet="previewIsSpreadsheet"
        :preview-is-docx="previewIsDocx"
        :spreadsheet-preview="spreadsheetPreview"
        :text-preview="textPreview"
        :selected-candidate="selectedCandidate"
        :can-upload="canUpload"
        :uploading="uploading"
        :upload-file="uploadFile"
        :upload-category="uploadCategory"
        :extraction-busy-document-id="extractionBusyDocumentId"
        :document-action-id="documentActionId"
        :document-category-draft="documentCategoryDraft"
        :document-analysis-form="documentAnalysisForm"
        :analysis-form-codes="FIELD_ANALYSIS_FORM_CODES"
        :source-categories="SOURCE_DOCUMENT_CATEGORIES"
        :parcel-import-preview="parcelImportPreview"
        :parcel-import-loading="parcelImportLoading"
        :parcel-importing="parcelImporting"
        :can-import-parcels="canEditLandContext"
        :case-district-code="flow.case.districtCode"
        :form-display-name="formDisplayName"
        :document-category-label="documentCategoryLabel"
        :format-file-size="formatFileSize"
        :document-pending-count="documentPendingCount"
        :document-candidate-count="documentCandidateCount"
        :document-ai-status="documentAiStatus"
        :can-extract-document="canExtractDocument"
        :can-manage-source-document="canManageSourceDocument"
        @preview="openDocumentPreview"
        @prepare-parcel-import="prepareParcelImport"
        @extract="extractDocument"
        @reclassify="reclassifyDocument"
        @remove="removeDocument"
        @download="downloadSourceDocument"
        @update-analysis-form="setDocumentAnalysisForm"
        @update-category="setDocumentCategory"
        @update-upload-category="uploadCategory = $event"
        @choose-upload="chooseUpload"
        @upload="uploadSourceDocument"
        @import-parcels="importParcelRows"
      />

      <ValuationCandidateWorkspace
        v-if="activeWizardStep === 2 && activeIntakeStage === 'ai-review'"
        :candidates="candidateDecisionTargets"
        :processed-candidates="processedCandidates"
        :pending-count="pendingCandidates.length"
        :selected-candidate-id="selectedCandidateId"
        :selected-candidate-count="selectedCandidateCount"
        :candidate-decision="candidateDecision"
        :candidate-value="candidateValue"
        :confirming-candidates="confirmingCandidates"
        :has-confirmation-export="Boolean(workflowGuidance?.confirmation_export)"
        :field-display-label="fieldDisplayLabel"
        :candidate-document-name="candidateDocumentName"
        :candidate-confidence-label="candidateConfidenceLabel"
        :candidate-provider-label="candidateProviderLabel"
        :candidate-unit="candidateUnit"
        :candidate-editor-type="candidateEditorType"
        :candidate-input-type="candidateInputType"
        :candidate-input-mode="candidateInputMode"
        :candidate-status-label="candidateStatusLabel"
        :display-candidate-value="displayCandidateValue"
        :preview-document-id="previewDocumentId"
        :preview-document="previewDocument"
        :preview-page="previewPage"
        :preview-loading="previewLoading"
        :preview-error="previewError"
        :preview-source-url="previewSourceUrl"
        :preview-is-pdf="previewIsPdf"
        :preview-is-image="previewIsImage"
        :preview-is-spreadsheet="previewIsSpreadsheet"
        :preview-is-docx="previewIsDocx"
        :spreadsheet-preview="spreadsheetPreview"
        :text-preview="textPreview"
        @select="selectCandidate"
        @open-source="openCandidateSource"
        @choose-decision="chooseCandidateDecision"
        @update-value="setCandidateValue"
        @cancel-reopen="cancelCandidateReopen"
        @reopen="reopenCandidate"
        @submit="submitCandidateDecisions"
        @download-export="downloadConfirmationExport"
      />

      <ValuationDataStageNavigator
        v-if="activeWizardStep === 3"
        :active-section="activeDataSection"
        :issue-counts="dataIssueCounts"
        :parcel-count="locationParcels.length"
        :benchmark-count="flow.benchmarks.length"
        :has-f03="Boolean(flow.f03)"
        @select="jumpToDataSection"
      />

      <ValuationManualFieldsSection
        v-if="activeWizardStep === 3 && activeDataSection === 'manual' && workflowGuidance"
        :active-form="activeManualForm"
        :entries="manualFieldEntries"
        :editable-count="manualEditableEntries.length"
        :values="manualFieldValue"
        :errors="workflowGuidance.manual_field_errors ?? {}"
        :saving="manualFieldsSaving"
        :field-metadata="manualFieldMetadata"
        @update-active-form="activeManualForm = $event"
        @update-value="setManualFieldValue"
        @go-land="jumpToDataSection('land')"
        @save="saveManualFields"
      />

      <ValuationLandContext
        v-if="activeWizardStep === 3 && activeDataSection === 'land'"
        :parcels="locationParcels"
        :benchmarks="flow.benchmarks"
        :documents="locationDocuments"
        :parcel-draft="parcelDraft"
        :benchmark-draft="benchmarkDraft"
        :editing-parcel-id="editingParcelId"
        :selected-benchmark-land-id="draft.benchmarkLandId"
        :can-edit-land-context="canEditLandContext"
        :can-edit-f03="canEditF03"
        :has-f03="Boolean(flow.f03)"
        :saving="landContextSaving"
        @edit-parcel="startParcelEdit"
        @reset-parcel="resetParcelDraft"
        @save-parcel="saveParcel"
        @save-benchmark="saveBenchmarkLand"
        @choose-benchmark="chooseBenchmarkForF03"
      />

      <ValuationF03Section
        v-if="activeWizardStep === 3 && activeDataSection === 'f03'"
        :f03="flow.f03"
        :benchmarks="flow.benchmarks"
        :draft="draft"
        :calculated-source="calculatedSource"
        :can-edit-f03="canEditF03"
        :saving="saving"
        @dirty="dirty = true"
        @save="handleSave"
      />

      <ValuationValidationSection
        v-if="activeWizardStep === 4"
        :validation="flow.validation"
        :calculation="flow.calculation"
        :report="flow.report"
        :has-f03="Boolean(flow.f03)"
        :pre-calculation-issue-count="preCalculationIssueCount"
        :dirty="dirty"
        :running="running"
        :saving="saving"
        :can-run-valuation="canRunValuation"
        :can-proceed-to-submit="canProceedToSubmit"
        :finding-location-label="findingLocationLabel"
        :finding-correction-hint="findingCorrectionHint"
        @run="runValuation"
        @fix-finding="goToFinding"
        @go-submit="goToSubmit"
      />

      <p v-if="notice" class="inline-notice" role="status">{{ notice }}</p>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>

      <ValuationWizardFooter
        v-if="activeWizardStep <= 4"
        :title="wizardStepTitle"
        :next-label="wizardNextLabel"
        :is-first-step="activeWizardStep === 1"
        :confirming="confirmingCaseInfo"
        :next-disabled="activeWizardStep === 4 && !canProceedToSubmit"
        @previous="wizardPrevious"
        @next="wizardNext"
      />
    </template>
  </div>
</template>

<style scoped>
.valuation-view {
  display: grid;
  gap: 18px;
  padding: 0 28px 34px;
}

.valuation-view :deep(.case-workspace-header) {
  margin-inline: -28px;
}

.inline-notice, .inline-error { margin: 0; padding: 12px 14px; border-radius: var(--app-radius-sm); font-size: 13px; }
.inline-notice { color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.inline-error { color: #a44334; background: #fff0ed; }

@media (max-width: 760px) {
  .valuation-view { padding: 18px 16px 28px; }
  .valuation-view :deep(.case-workspace-header) { margin: -18px -16px 0; }
}
</style>
