<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EmptyState from '../../../components/common/EmptyState.vue'
import DocumentTextPreview from '../../../components/common/DocumentTextPreview.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import RiskBadge from '../../../components/common/RiskBadge.vue'
import SpreadsheetPreview from '../../../components/common/SpreadsheetPreview.vue'
import StatusBadge from '../../../components/common/StatusBadge.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { statusLabel } from '../../../utils/enumLabels'
import { isTechnicalOnlyField } from '../../../utils/fieldLabels'
import { historyApi, safeHistoryDownloadError, safeHistoryErrorMessage } from '../history.api'
import { historyLocationLabel } from '../history.location'
import {
  formCodeLabel,
  mapHistoryDetail,
  readableDate,
  readableFieldLabel,
  readableValue,
  valuationTypeLabel,
} from '../history.mappers'
import {
  decisionLabel,
  documentTypeLabel,
  findingCodeLabel,
  findingStatusLabel,
  findingTypeLabel,
  fieldPathLabel,
  mimeTypeLabel,
  reviewStatusLabel,
  reviewTypeLabel,
  riskLevelLabel,
  runStatusLabel,
  severityLabel,
  aiStatusLabel,
} from '../../review/review.mappers'
import CaseTimeline from '../components/CaseTimeline.vue'
import DocumentList from '../components/DocumentList.vue'
import type { SpreadsheetPreviewDto } from '../../../types/spreadsheet'
import type { DocumentTextPreviewDto } from '../../../types/documentPreview'
import type {
  HistoryCaseDetailModel,
  HistoryDocumentModel,
  HistoryReviewModel,
  HistoryTimelineEvent,
  HistoryValuationModel,
} from '../history.types'

type DetailTab = 'overview' | 'timeline' | 'valuation' | 'review' | 'versions'
type TimelineFilter = 'all' | HistoryTimelineEvent['module']
interface DisplayValue { value: string; technicalCode?: string }
interface DisplayField extends DisplayValue { label: string }
interface TechnicalField { label: string; code: string }
interface DisplayRecord { key: string; title: string; fields: DisplayField[]; technicalFields: TechnicalField[] }
type EnumLabeler = (value: string | null | undefined) => string

const STRUCTURED_CHANGE_VALUE_KEYS = new Set([
  'before_value',
  'after_value',
  'old_value',
  'new_value',
  'previous_value',
  'current_value',
])

const route = useRoute()
const router = useRouter()
const detail = ref<HistoryCaseDetailModel | null>(null)
const loading = ref(false)
const error = ref('')
const message = ref('')
const activeTab = ref<DetailTab>('overview')
const timelineFilter = ref<TimelineFilter>('all')
const busyDocumentId = ref<string | null>(null)
const errorByDocument = ref<Record<string, string>>({})
const previewDocument = ref<HistoryDocumentModel | null>(null)
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const previewSpreadsheet = ref<SpreadsheetPreviewDto | null>(null)
const previewText = ref<DocumentTextPreviewDto | null>(null)
let activeController: AbortController | null = null
let loadSerial = 0

const caseId = computed(() => (typeof route.params.caseId === 'string' ? route.params.caseId : ''))
const hasValuation = computed(() => Boolean(detail.value?.permissions.canViewValuation))
const hasReview = computed(() => Boolean(detail.value?.permissions.canViewReview))
const hasVersionHistory = computed(() => Boolean(
  detail.value && (detail.value.versions.length || detail.value.changes.length || detail.value.versionDiffs.length),
))
const currentDocumentCount = computed(() => {
  const documents = detail.value?.documents ?? []
  return new Set(documents.map((document) => document.documentGroupId || document.documentId)).size
})
const documentSummary = computed(() => {
  const totalVersions = detail.value?.documents.length ?? 0
  const historyVersions = Math.max(0, totalVersions - currentDocumentCount.value)
  return historyVersions
    ? `${currentDocumentCount.value} 份目前文件 · ${historyVersions} 個歷史版本`
    : `${currentDocumentCount.value} 份目前文件`
})
const districtDisplay = computed(() => {
  if (!detail.value) return '—'
  return historyLocationLabel(detail.value.cityCode, detail.value.districtCode)
})
const timelineFilterOptions = computed<Array<{ value: TimelineFilter; label: string; count: number }>>(() => {
  const events = detail.value?.timeline ?? []
  const labels: Array<{ value: HistoryTimelineEvent['module']; label: string }> = [
    { value: 'case', label: '案件' },
    { value: 'valuation', label: '估價' },
    { value: 'review', label: '審查' },
    { value: 'document', label: '文件' },
  ]
  return [
    { value: 'all', label: '全部', count: events.length },
    ...labels
      .map((option) => ({ ...option, count: events.filter((event) => event.module === option.value).length }))
      .filter((option) => option.count > 0),
  ]
})
const filteredTimelineEvents = computed(() => {
  const events = detail.value?.timeline ?? []
  if (timelineFilter.value === 'all') return events
  return events.filter((event) => event.module === timelineFilter.value)
})

function safeRecordEntries(record: Record<string, unknown>): Array<[string, unknown]> {
  return Object.entries(record).filter(([key, value]) => {
    if (isTechnicalOnlyField(key)) return false
    return value !== null && value !== undefined && value !== ''
  })
}

function displayFields(record: Record<string, unknown>): DisplayField[] {
  return safeRecordEntries(record).map(([key, value]) => ({ label: readableFieldLabel(key), ...displayFieldValue(key, value) }))
}

function displayEnumValue(value: unknown, labeler: EnumLabeler): DisplayValue {
  if (value === null || value === undefined || value === '') return { value: '—' }
  const code = typeof value === 'string' ? value.trim() : ''
  const label = labeler(code || undefined)
  return code && label === labeler(undefined) ? { value: label, technicalCode: code } : { value: label }
}

function displayStructuredChangeValue(value: unknown): DisplayValue {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { value: readableValue(value) }

  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([key, item]) => !isTechnicalOnlyField(key) && item !== null && item !== undefined && item !== '')
    .slice(0, 4)
  if (!entries.length) return { value: '—' }

  return {
    value: entries
      .map(([key, item]) => `${readableFieldLabel(key)}：${displayFieldValue(key, item).value}`)
      .join('、'),
  }
}

function displayFieldValue(key: string, value: unknown): DisplayValue {
  if (value === null || value === undefined || value === '') return { value: '—' }
  if (STRUCTURED_CHANGE_VALUE_KEYS.has(key)) return displayStructuredChangeValue(value)
  if (key.endsWith('_at') || key.endsWith('_date')) return { value: readableDate(value) }
  if (key === 'review_type') return displayEnumValue(value, reviewTypeLabel)
  if (key === 'review_status') return displayEnumValue(value, reviewStatusLabel)
  if (key === 'run_status') return displayEnumValue(value, runStatusLabel)
  if (key === 'overall_risk_level' || key === 'current_risk_level' || key === 'risk_level') return displayEnumValue(value, riskLevelLabel)
  if (key === 'finding_status' || key === 'status') return displayEnumValue(value, findingStatusLabel)
  if (key.endsWith('_status') || key === 'case_status') return displayEnumValue(value, statusLabel)
  if (key === 'valuation_type') return displayEnumValue(value, valuationTypeLabel)
  if (key === 'form_code') return { value: formCodeLabel(typeof value === 'string' ? value : undefined) }
  if (key === 'finding_code' || key === 'rule_code') return displayEnumValue(value, findingCodeLabel)
  if (key === 'finding_type') return displayEnumValue(value, findingTypeLabel)
  if (key === 'field_path') return displayEnumValue(value, fieldPathLabel)
  if (key === 'decision') return displayEnumValue(value, decisionLabel)
  if (key === 'severity') return displayEnumValue(value, severityLabel)
  if (key === 'ai_status') return displayEnumValue(value, aiStatusLabel)
  if (key === 'document_type') return displayEnumValue(value, documentTypeLabel)
  if (key === 'mime_type' || key === 'content_type') return displayEnumValue(value, mimeTypeLabel)
  if (key === 'source_module') {
    const source = typeof value === 'string' ? value.trim().toLowerCase() : ''
    return { value: source === 'valuation' ? '估價作業' : source === 'review' ? '智慧審查' : '系統資料' }
  }
  if (key === 'source_type') {
    const source = typeof value === 'string' ? value.trim().toUpperCase() : ''
    const labels: Readonly<Record<string, string>> = {
      OCR: '文件辨識',
      MANUAL: '人工填寫',
      USER: '人工填寫',
      SYSTEM: '系統產生',
      IMPORTED: '文件匯入',
      AI: '智能分析',
      OLLAMA: '智能分析',
    }
    return { value: labels[source] ?? '系統資料' }
  }
  return { value: readableValue(value) }
}

function displayRecords(
  collection: Record<string, unknown>[] | undefined,
  titleKeys: string[],
  fallback: string,
): DisplayRecord[] {
  return (collection ?? []).map((record, index) => {
    const fields = displayFields(record)
    const title = titleKeys.map((key) => displayFieldValue(key, record[key])).find(({ value }) => value !== '—')
    const titleValue = title?.value
    return {
      key: `${fallback}-${index}-${titleValue ?? ''}`,
      title: titleValue && titleValue !== '已提供' ? titleValue : `${fallback} ${index + 1}`,
      fields,
      technicalFields: fields.flatMap(({ label, technicalCode }) => technicalCode ? [{ label, code: technicalCode }] : []),
    }
  })
}

function valuationRecords(valuation: HistoryValuationModel | null): DisplayRecord[] {
  if (!valuation) return []
  return [
    ...displayRecords(valuation.forms, ['form_code'], '查估書表'),
    ...displayRecords(valuation.valuations, ['valuation_type', 'result_status'], '估價結果'),
    ...displayRecords(valuation.comparisonAnalyses, ['analysis_status'], '比較分析'),
    ...displayRecords(valuation.benchmarkValuations, ['valuation_status'], '比準地估價'),
    ...displayRecords(valuation.parcelValuations, ['valuation_status'], '宗地估價'),
    ...displayRecords(valuation.validationRuns, ['run_status'], '估價檢核'),
    ...displayRecords(valuation.validationFindings, ['rule_code', 'severity'], '估價檢核項目'),
  ]
}

function reviewRecords(review: HistoryReviewModel | null): DisplayRecord[] {
  if (!review) return []
  return [
    ...displayRecords(review.reviews, ['review_type', 'review_status'], '審查案件'),
    ...displayRecords(review.riskSummaries, ['overall_risk_level', 'summary'], '風險摘要'),
    ...displayRecords(review.findings, ['title', 'finding_code'], '審查疑點'),
    ...displayRecords(review.decisions, ['decision'], '審查決定'),
  ]
}

const valuationItems = computed(() => valuationRecords(detail.value?.valuation ?? null))
const reviewItems = computed(() => reviewRecords(detail.value?.review ?? null))

function versionFieldLabel(fieldCode: string, fieldPath?: string | null): string {
  const pathLabel = fieldPath ? fieldPathLabel(fieldPath) : ''
  if (pathLabel && pathLabel !== '其他檢核欄位') return pathLabel
  const labels: Readonly<Record<string, string>> = {
    valuation_base_date: '估價基準日', comparison_price: '比較法價格', comparison_weight: '比較法權重',
    income_price: '收益法價格', income_weight: '收益法權重', market_condition: '市場條件',
    adjustment_rate: '調整率', land_no: '地號', area_sqm: '土地面積', land_use_zone: '使用分區',
  }
  return labels[fieldCode] ?? '估價資料欄位'
}

function changeEntityLabel(value: string): string {
  const labels: Readonly<Record<string, string>> = {
    case: '案件', document: '文件', valuation: '估價資料', review: '審查資料', form: '查估書表',
  }
  return labels[value.toLowerCase()] ?? '案件資料'
}

function syncTab(): void {
  if (activeTab.value === 'valuation' && !hasValuation.value) activeTab.value = hasReview.value ? 'review' : 'overview'
  if (activeTab.value === 'review' && !hasReview.value) activeTab.value = hasValuation.value ? 'valuation' : 'overview'
  if (activeTab.value === 'versions' && !hasVersionHistory.value) activeTab.value = 'overview'
}

function handleTabKeydown(event: KeyboardEvent): void {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  const tablist = event.currentTarget as HTMLElement | null
  if (!tablist) return
  const tabs = Array.from(tablist.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
  if (!tabs.length) return
  const currentIndex = tabs.findIndex((tab) => tab === document.activeElement)
  if (currentIndex < 0) return

  let nextIndex = currentIndex
  if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length
  if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
  if (event.key === 'Home') nextIndex = 0
  if (event.key === 'End') nextIndex = tabs.length - 1

  const nextTab = tabs[nextIndex]
  const nextValue = nextTab?.dataset.tab as DetailTab | undefined
  if (!nextTab || !nextValue) return
  event.preventDefault()
  activeTab.value = nextValue
  nextTab.focus()
}

async function load(): Promise<void> {
  if (!caseId.value) return
  const serial = ++loadSerial
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const dto = await historyApi.getCase(caseId.value, controller.signal)
    if (serial !== loadSerial) return
    detail.value = mapHistoryDetail(dto)
    syncTab()
  } catch (caught: unknown) {
    if (serial === loadSerial && !controller.signal.aborted) error.value = safeHistoryErrorMessage(caught)
  } finally {
    if (serial === loadSerial) loading.value = false
  }
}

function backToSearch(): void {
  void router.push({ name: 'history-search', query: route.query })
}

function downloadAnchor(url: string, filename: string): HTMLAnchorElement {
  const anchor = window.document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  return anchor
}

function clearDocumentPreview(): void {
  if (previewUrl.value && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewSpreadsheet.value = null
  previewText.value = null
  previewDocument.value = null
  previewError.value = ''
}

function closeDocumentPreview(): void {
  const documentId = previewDocument.value?.documentId ?? ''
  clearDocumentPreview()
  if (!documentId) return
  void nextTick(() => {
    document.querySelector<HTMLButtonElement>(`[data-testid="history-preview-${documentId}"]`)?.focus()
  })
}

function handlePreviewKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.preventDefault()
  closeDocumentPreview()
}

async function previewHistoryDocument(historyDocument: HistoryDocumentModel): Promise<void> {
  if (previewLoading.value || historyDocument.downloadAvailable === false) return
  if (previewDocument.value?.documentId === historyDocument.documentId && previewUrl.value) return
  clearDocumentPreview()
  previewDocument.value = historyDocument
  previewLoading.value = true
  try {
    if (
      historyDocument.contentType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      || historyDocument.contentType === 'application/vnd.ms-excel'
    ) {
      previewSpreadsheet.value = await historyApi.previewSpreadsheet(historyDocument.documentId)
      return
    }
    if (historyDocument.contentType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
      previewText.value = await historyApi.previewTextDocument(historyDocument.documentId)
      return
    }
    const blob = await historyApi.downloadDocument(historyDocument.documentId)
    if (typeof URL.createObjectURL === 'function') previewUrl.value = URL.createObjectURL(blob)
  } catch (caught: unknown) {
    previewError.value = safeHistoryDownloadError(caught)
  } finally {
    previewLoading.value = false
    await nextTick()
    document.getElementById('history-document-preview')?.focus()
  }
}

async function downloadDocument(historyDocument: HistoryDocumentModel): Promise<void> {
  if (busyDocumentId.value || historyDocument.downloadAvailable === false) return
  busyDocumentId.value = historyDocument.documentId
  errorByDocument.value = { ...errorByDocument.value, [historyDocument.documentId]: '' }
  message.value = ''
  try {
    const blob = await historyApi.downloadDocument(historyDocument.documentId)
    if (typeof URL.createObjectURL === 'function') {
      const url = URL.createObjectURL(blob)
      const anchor = downloadAnchor(url, historyDocument.fileName)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    }
    message.value = `已準備下載 ${historyDocument.fileName}。`
  } catch (caught: unknown) {
    errorByDocument.value = {
      ...errorByDocument.value,
      [historyDocument.documentId]: safeHistoryDownloadError(caught),
    }
  } finally {
    busyDocumentId.value = null
  }
}

watch(caseId, () => {
  clearDocumentPreview()
  detail.value = null
  activeTab.value = 'overview'
  timelineFilter.value = 'all'
  void load()
})

watch([hasValuation, hasReview], syncTab)

onMounted(load)
onBeforeUnmount(() => {
  activeController?.abort()
  clearDocumentPreview()
})
</script>

<template>
  <section class="history-case" data-testid="history-case">
    <PageHeader
      eyebrow="案件歷史"
      title="案件資料"
      :description="detail ? `${detail.caseNo} · ${detail.caseTitle}` : '查看授權的案件資料與相關文件。'"
    >
      <template #actions>
        <button type="button" class="history-case__back" data-testid="history-back-search" @click="backToSearch">返回案件清單</button>
      </template>
    </PageHeader>

    <ol class="history-case__flow" aria-label="案件歷史操作流程">
      <li class="is-complete"><span>1</span><div><strong>確認權限</strong><small>依登入帳號自動判斷</small></div></li>
      <li class="is-complete"><span>2</span><div><strong>搜尋案件</strong><small>已選取案件</small></div></li>
      <li class="is-current" aria-current="step"><span>3</span><div><strong>查看資料 / 下載文件</strong><small>目前所在步驟</small></div></li>
    </ol>

    <LoadingSkeleton v-if="loading && !detail" :rows="6" label="案件歷程明細載入中" />
    <ErrorState v-else-if="error && !detail" :message="error" @retry="load" />
    <EmptyState v-else-if="!caseId" title="尚未選取案件" description="請先從案件歷程清單開啟一筆案件。" />
    <template v-else-if="detail">
      <p v-if="error || message" class="history-case__message" :class="{ 'is-error': error }" role="status">{{ error || message }}</p>

      <section v-liquid-glass data-lg class="history-case__identity lg" aria-labelledby="history-case-identity-title">
        <div class="history-case__identity-heading">
          <div>
            <p class="history-case__eyebrow">案件資料</p>
            <h2 id="history-case-identity-title">{{ detail.caseTitle }}</h2>
            <p class="history-case__identity-no">{{ detail.caseNo }}</p>
          </div>
          <div class="history-case__identity-status">
            <StatusBadge :status="detail.caseStatusCode" />
            <RiskBadge v-if="detail.riskLevelCode" :risk="detail.riskLevelCode" />
          </div>
        </div>
        <dl class="history-case__identity-grid">
          <div><dt>案件類型</dt><dd>{{ detail.caseType || '—' }}</dd></div>
          <div><dt>案件地區</dt><dd>{{ districtDisplay }}</dd></div>
          <div><dt>估價基準日</dt><dd>{{ readableDate(detail.valuationBaseDate) }}</dd></div>
          <div><dt>案件狀態</dt><dd>{{ detail.caseStatusLabel }}</dd></div>
          <div><dt>最後更新</dt><dd>{{ readableDate(detail.updatedAt) }}</dd></div>
          <div><dt>案件文件</dt><dd>{{ currentDocumentCount }} 份</dd></div>
        </dl>
        <div class="history-case__identity-footer">
          <span>可查看：{{ hasValuation ? '估價資料' : '' }}{{ hasValuation && hasReview ? '、' : '' }}{{ hasReview ? '審查資料' : '' }}</span>
          <span>{{ documentSummary }}</span>
        </div>
      </section>

      <nav class="history-case__tabs" role="tablist" aria-label="案件歷程資料區段" @keydown="handleTabKeydown">
        <button id="history-tab-overview-button" type="button" role="tab" data-tab="overview" aria-controls="history-panel-overview" :aria-selected="activeTab === 'overview'" :tabindex="activeTab === 'overview' ? 0 : -1" :class="{ 'is-active': activeTab === 'overview' }" data-testid="history-tab-overview" @click="activeTab = 'overview'">案件資料</button>
        <button id="history-tab-timeline-button" type="button" role="tab" data-tab="timeline" aria-controls="history-panel-timeline" :aria-selected="activeTab === 'timeline'" :tabindex="activeTab === 'timeline' ? 0 : -1" :class="{ 'is-active': activeTab === 'timeline' }" data-testid="history-tab-timeline" @click="activeTab = 'timeline'">
          <span>案件歷程</span><small class="history-case__tab-count">{{ detail.timeline.length }}</small>
        </button>
        <button v-if="detail.permissions.canViewValuation" id="history-tab-valuation-button" type="button" role="tab" data-tab="valuation" aria-controls="history-panel-valuation" :aria-selected="activeTab === 'valuation'" :tabindex="activeTab === 'valuation' ? 0 : -1" :class="{ 'is-active': activeTab === 'valuation' }" data-testid="history-tab-valuation" @click="activeTab = 'valuation'">
          <span>估價資料</span><small class="history-case__tab-count">{{ valuationItems.length }}</small>
        </button>
        <button v-if="detail.permissions.canViewReview" id="history-tab-review-button" type="button" role="tab" data-tab="review" aria-controls="history-panel-review" :aria-selected="activeTab === 'review'" :tabindex="activeTab === 'review' ? 0 : -1" :class="{ 'is-active': activeTab === 'review' }" data-testid="history-tab-review" @click="activeTab = 'review'">
          <span>審查資料</span><small class="history-case__tab-count">{{ reviewItems.length }}</small>
        </button>
        <button v-if="hasVersionHistory" id="history-tab-versions-button" type="button" role="tab" data-tab="versions" aria-controls="history-panel-versions" :aria-selected="activeTab === 'versions'" :tabindex="activeTab === 'versions' ? 0 : -1" :class="{ 'is-active': activeTab === 'versions' }" data-testid="history-tab-versions" @click="activeTab = 'versions'">
          <span>版本比較</span><small class="history-case__tab-count">{{ detail.versionDiffs.length || detail.versions.length }}</small>
        </button>
      </nav>

      <section v-if="activeTab === 'overview'" id="history-panel-overview" role="tabpanel" aria-labelledby="history-tab-overview-button">
        <div class="history-case__overview-grid">
          <section v-liquid-glass data-lg class="history-case__facts lg" aria-labelledby="history-case-facts-title">
            <p class="history-case__eyebrow">資料概況</p>
            <h2 id="history-case-facts-title">案件內容摘要</h2>
            <dl>
              <div><dt>土地資料</dt><dd>{{ detail.parcels.length }} 筆</dd></div>
              <div><dt>案件文件</dt><dd>{{ currentDocumentCount }} 份</dd></div>
              <div v-if="hasValuation"><dt>估價資料</dt><dd>{{ valuationItems.length }} 筆紀錄</dd></div>
              <div v-if="hasReview"><dt>審查資料</dt><dd>{{ reviewItems.length }} 筆紀錄</dd></div>
            </dl>
          </section>
          <DocumentList
            :documents="detail.documents"
            :busy-document-id="busyDocumentId"
            :error-by-document="errorByDocument"
            @preview="previewHistoryDocument"
            @download="downloadDocument"
          />
        </div>
        <section v-if="previewDocument" id="history-document-preview" class="history-case__document-preview" data-testid="history-document-preview" tabindex="-1" aria-live="polite" aria-labelledby="history-document-preview-title" @keydown="handlePreviewKeydown">
          <header>
            <div>
              <p class="history-case__eyebrow">文件預覽</p>
              <h2 id="history-document-preview-title">{{ previewDocument.fileName }}</h2>
              <span>{{ previewDocument.documentTypeLabel }} · 第 {{ previewDocument.versionNo }} 版 · {{ previewDocument.sourceModuleLabel }}</span>
            </div>
            <button type="button" @click="closeDocumentPreview">關閉預覽</button>
          </header>
          <LoadingSkeleton v-if="previewLoading" :rows="4" label="文件預覽載入中" />
          <ErrorState v-else-if="previewError" :message="previewError" @retry="previewHistoryDocument(previewDocument)" />
          <iframe
            v-else-if="previewUrl && previewDocument.contentType === 'application/pdf'"
            class="history-case__document-frame"
            data-testid="history-document-pdf"
            :src="previewUrl"
            :title="`${previewDocument.fileName} PDF 預覽`"
          />
          <img
            v-else-if="previewUrl && previewDocument.contentType.startsWith('image/')"
            class="history-case__document-image"
            data-testid="history-document-image"
            :src="previewUrl"
            :alt="`${previewDocument.fileName} 預覽`"
          >
          <SpreadsheetPreview v-else-if="previewSpreadsheet" :preview="previewSpreadsheet" />
          <DocumentTextPreview v-else-if="previewText" :preview="previewText" />
          <div v-else class="history-case__document-unsupported">
            <strong>此格式目前不支援直接內嵌預覽</strong>
            <span>仍可使用上方文件清單的「下載」查看完整內容。</span>
          </div>
        </section>
        <section v-if="detail.permissions.canViewValuation && detail.parcels.length" v-liquid-glass data-lg class="history-case__parcel-card lg" aria-labelledby="history-parcels-title">
          <p class="history-case__eyebrow">土地資料</p>
          <h2 id="history-parcels-title">地籍資料</h2>
          <div class="history-case__parcel-list">
            <div v-for="(parcel, index) in detail.parcels" :key="`parcel-${index}`" class="history-case__parcel">
              <strong>{{ readableValue(parcel.land_no) }}</strong>
              <span>{{ readableValue(parcel.section_name) }} · {{ readableValue(parcel.area_sqm) }} 平方公尺</span>
            </div>
          </div>
        </section>
      </section>

      <section v-else-if="activeTab === 'timeline'" id="history-panel-timeline" role="tabpanel" aria-labelledby="history-tab-timeline-button" class="history-case__timeline-section" data-testid="history-timeline-section">
        <nav class="history-case__timeline-filter" aria-label="案件歷程事件篩選">
          <button
            v-for="option in timelineFilterOptions"
            :key="option.value"
            type="button"
            :class="{ 'is-active': timelineFilter === option.value }"
            :aria-pressed="timelineFilter === option.value"
            :data-testid="`history-timeline-filter-${option.value}`"
            @click="timelineFilter = option.value"
          >
            <span>{{ option.label }}</span>
            <small>{{ option.count }}</small>
          </button>
        </nav>
        <CaseTimeline :events="filteredTimelineEvents" />
      </section>

      <section v-else-if="activeTab === 'valuation'" id="history-panel-valuation" role="tabpanel" aria-labelledby="history-tab-valuation-button" v-liquid-glass data-lg class="history-case__data-section lg" data-testid="history-valuation-section">
        <div class="history-case__section-heading">
          <div><p class="history-case__eyebrow">估價紀錄</p><h2 id="history-valuation-title">估價資料</h2></div>
          <span>{{ valuationItems.length }} 筆估價紀錄</span>
        </div>
        <p v-if="!valuationItems.length" class="history-case__empty">目前沒有可顯示的估價紀錄。</p>
        <div v-else class="history-case__record-grid">
          <article v-for="item in valuationItems" :key="item.key" class="history-case__record">
            <h3>{{ item.title }}</h3>
            <dl><div v-for="field in item.fields" :key="`${item.key}-${field.label}`"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl>
          </article>
        </div>
      </section>

      <section v-else-if="activeTab === 'review'" id="history-panel-review" role="tabpanel" aria-labelledby="history-tab-review-button" v-liquid-glass data-lg class="history-case__data-section lg" data-testid="history-review-section">
        <div class="history-case__section-heading">
          <div><p class="history-case__eyebrow">審查紀錄</p><h2 id="history-review-title">審查資料</h2></div>
          <span>{{ reviewItems.length }} 筆審查紀錄</span>
        </div>
        <p v-if="!reviewItems.length" class="history-case__empty">目前沒有可顯示的審查紀錄。</p>
        <div v-else class="history-case__record-grid">
          <article v-for="item in reviewItems" :key="item.key" class="history-case__record">
            <h3>{{ item.title }}</h3>
            <dl><div v-for="field in item.fields" :key="`${item.key}-${field.label}`"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl>
          </article>
        </div>
      </section>

      <section v-else-if="activeTab === 'versions'" id="history-panel-versions" role="tabpanel" aria-labelledby="history-tab-versions-button" class="history-case__version-section" data-testid="history-version-section">
        <div class="history-case__section-heading">
          <div><p class="history-case__eyebrow">版本變更</p><h2 id="history-version-title">版本前後比較</h2></div>
          <span>{{ detail.versionDiffs.length }} 個欄位變更</span>
        </div>

        <div v-if="detail.versions.length" class="history-case__version-meta">
          <article v-for="version in detail.versions" :key="`${version.version_no}-${version.created_at}`">
            <strong>第 {{ version.version_no }} 版</strong>
            <span>{{ version.change_summary || '案件版本更新' }}</span>
            <small>{{ version.created_by || '系統流程' }} · {{ readableDate(version.created_at) }}</small>
          </article>
        </div>

        <div v-if="detail.versionDiffs.length" class="history-case__diff-grid">
          <article v-for="diff in detail.versionDiffs" :key="`${diff.field_code}-${diff.previous.document_version}-${diff.current.document_version}`">
            <h3>{{ versionFieldLabel(diff.field_code, diff.field_path) }}</h3>
            <div class="history-case__diff-values">
              <div>
                <span>修改前 · 第 {{ diff.previous.document_version }} 版</span>
                <strong>{{ displayFieldValue(diff.field_code, diff.previous.value).value }}</strong>
                <small v-if="diff.previous.page_number">來源第 {{ diff.previous.page_number }} 頁</small>
                <p v-if="diff.previous.raw_text">{{ diff.previous.raw_text }}</p>
              </div>
              <span class="history-case__diff-arrow" aria-hidden="true">→</span>
              <div class="is-current">
                <span>修改後 · 第 {{ diff.current.document_version }} 版</span>
                <strong>{{ displayFieldValue(diff.field_code, diff.current.value).value }}</strong>
                <small v-if="diff.current.page_number">來源第 {{ diff.current.page_number }} 頁</small>
                <p v-if="diff.current.raw_text">{{ diff.current.raw_text }}</p>
              </div>
            </div>
          </article>
        </div>
        <p v-else class="history-case__empty">目前沒有可比對的前後欄位差異。</p>

        <section v-if="detail.changes.length" class="history-case__change-log" aria-labelledby="history-change-log-title">
          <h3 id="history-change-log-title">修改紀錄</h3>
          <ol>
            <li v-for="(change, index) in detail.changes" :key="`${change.changed_at}-${index}`">
              <div>
                <strong>{{ changeEntityLabel(change.entity_type) }} · {{ readableFieldLabel(change.field_name) }}</strong>
                <span>{{ displayFieldValue(change.field_name, change.old_value).value }} → {{ displayFieldValue(change.field_name, change.new_value).value }}</span>
                <p v-if="change.change_reason">{{ change.change_reason }}</p>
              </div>
              <small>{{ change.changed_by || '系統流程' }} · {{ readableDate(change.changed_at) }}</small>
            </li>
          </ol>
        </section>
      </section>
    </template>
  </section>
</template>

<style scoped>
.history-case { padding: 0 28px 34px; }
.history-case__back { min-height: 42px; padding: 8px 15px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-case__back:hover { border-color: var(--app-accent); color: var(--app-accent-deep); }
.history-case__message { margin: 10px 0 0; color: var(--app-green); font-size: 13px; font-weight: 700; }
.history-case__message.is-error { color: #ac3c37; }
.history-case__flow { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0; margin:0 0 15px; padding:0; border:1px solid var(--app-line); border-radius:12px; overflow:hidden; background:rgba(255,255,255,.68); list-style:none; }
.history-case__flow li { display:flex; align-items:center; gap:10px; min-width:0; padding:11px 15px; }
.history-case__flow li + li { border-left:1px solid var(--app-line); }
.history-case__flow li > span { display:grid; width:26px; height:26px; flex:0 0 26px; place-items:center; border:1px solid var(--app-line); border-radius:999px; color:var(--app-muted); background:#fff; font-size:10px; font-weight:900; }
.history-case__flow li div { display:grid; min-width:0; gap:2px; }
.history-case__flow strong { color:var(--app-ink-soft); font-size:11px; }
.history-case__flow small { overflow:hidden; color:var(--app-muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.history-case__flow .is-complete > span { border-color:#b8d8c6; color:#276345; background:#eef7f2; }
.history-case__flow .is-current { background:color-mix(in srgb, var(--app-primary-soft) 72%, white); }
.history-case__flow .is-current > span { border-color:var(--app-primary); color:#fff; background:var(--app-primary); }
.history-case__flow .is-current strong { color:var(--app-primary-deep); }
.history-case__identity { display:grid; gap:17px; margin-top:12px; padding:20px; border:1px solid rgba(255,255,255,.72); border-radius:var(--app-radius-md); background:rgba(248,250,252,.74); box-shadow:var(--app-shadow-soft); }
.history-case__identity-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }
.history-case__eyebrow { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 10px; font-weight: 900; letter-spacing: .15em; }
.history-case__identity h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 25px; }
.history-case__identity-no { margin:6px 0 0; color:var(--app-muted); font-size:11px; font-weight:800; letter-spacing:.06em; }
.history-case__identity-status { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.history-case__identity-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; margin:0; overflow:hidden; border:1px solid var(--app-line); border-radius:10px; background:var(--app-line); }
.history-case__identity-grid div { display:grid; gap:4px; min-width:0; padding:11px 12px; background:rgba(255,255,255,.88); }
.history-case__identity-grid dt { color:var(--app-muted); font-size:9px; font-weight:800; }
.history-case__identity-grid dd { margin:0; overflow-wrap:anywhere; color:var(--app-ink); font-size:12px; font-weight:800; }
.history-case__identity-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; color:var(--app-muted); font-size:10px; }
.history-case__tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; border-bottom: 1px solid var(--app-line); }
.history-case__tabs button { display: inline-flex; min-height: 44px; align-items: center; gap: 7px; margin-bottom: -1px; padding: 8px 14px; border: 1px solid transparent; border-bottom: 2px solid transparent; border-radius: 8px 8px 0 0; color: var(--app-ink-soft); background: transparent; cursor: pointer; font-size: 13px; font-weight: 800; }
.history-case__tabs button:hover,
.history-case__tabs button.is-active { border-color: var(--app-line); border-bottom-color: var(--app-accent); color: var(--app-accent-deep); background: var(--app-paper-strong); }
.history-case__back:focus-visible,
.history-case__tabs button:focus-visible,
.history-case__timeline-filter button:focus-visible,
.history-case__document-preview header button:focus-visible { outline:3px solid color-mix(in srgb, var(--app-accent) 30%, white); outline-offset:2px; }
.history-case__document-preview:focus-visible { outline:3px solid color-mix(in srgb, var(--app-primary) 25%, white); outline-offset:3px; }
.history-case__tab-count { display: grid; min-width: 22px; height: 22px; place-items: center; padding: 0 6px; border-radius: 999px; color: #607286; background: #edf1f5; font-size: 9px; font-weight: 900; line-height: 1; }
.history-case__tabs button.is-active .history-case__tab-count { color: #244d73; background: #e6eff8; }
.history-case__overview-grid { display: grid; grid-template-columns: minmax(230px, .7fr) minmax(0, 1.3fr); gap: 15px; margin-top: 15px; }
.history-case__document-preview { display:grid; gap:12px; margin-top:15px; padding:18px; border:1px solid var(--app-line); border-radius:var(--app-radius-sm); background:var(--app-paper-strong); }
.history-case__document-preview > header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.history-case__document-preview h2 { margin:0; color:var(--app-ink); font-size:19px; }
.history-case__document-preview header span { display:block; margin-top:5px; color:var(--app-muted); font-size:11px; }
.history-case__document-preview header button { min-height:40px; padding:7px 11px; border:1px solid var(--app-line); border-radius:8px; color:var(--app-ink-soft); background:#fff; cursor:pointer; font-weight:800; }
.history-case__document-frame { width:100%; min-height:620px; border:1px solid #d6dee8; border-radius:8px; background:#eef2f6; }
.history-case__document-image { display:block; max-width:100%; max-height:720px; margin:auto; border-radius:8px; object-fit:contain; }
.history-case__document-preview :deep(.spreadsheet-preview) { min-width:0; }
.history-case__document-unsupported { display:grid; gap:5px; padding:28px; border:1px dashed var(--app-line); border-radius:8px; color:var(--app-muted); text-align:center; }
.history-case__document-unsupported strong { color:var(--app-ink-soft); }
.history-case__facts,
.history-case__parcel-card,
.history-case__data-section { padding: 20px; border: 1px solid rgba(255,255,255,.72); border-radius: var(--app-radius-sm); background: rgba(255,255,255,.72); box-shadow: var(--app-shadow-soft); }
.history-case__facts h2,
.history-case__parcel-card h2 { margin: 0 0 14px; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; }
.history-case__facts dl { display: grid; gap: 10px; margin: 0; }
.history-case__facts dl div { display: grid; gap: 3px; }
.history-case__facts dt,
.history-case__record dt { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.history-case__facts dd { margin: 0; color: var(--app-ink); font-size: 13px; font-weight: 800; }
.history-case__parcel-card { margin-top: 15px; }
.history-case__parcel-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.history-case__parcel { display: grid; gap: 4px; padding: 11px; border: 1px solid #e5e9f0; border-radius: 9px; background: #fbfcfe; }
.history-case__parcel strong { color: var(--app-ink); font-size: 13px; }
.history-case__parcel span { color: var(--app-ink-soft); font-size: 11px; }
.history-case__timeline-section { margin-top:15px; }
.history-case__timeline-filter { display:flex; flex-wrap:wrap; gap:7px; margin-bottom:10px; padding:10px; border:1px solid var(--app-line); border-radius:10px; background:rgba(255,255,255,.66); }
.history-case__timeline-filter button { display:inline-flex; min-height:36px; align-items:center; gap:7px; padding:6px 10px; border:1px solid var(--app-line); border-radius:999px; color:var(--app-ink-soft); background:#fff; cursor:pointer; font-size:11px; font-weight:800; }
.history-case__timeline-filter button:hover { border-color:var(--app-primary); color:var(--app-primary-deep); }
.history-case__timeline-filter button.is-active { border-color:var(--app-primary); color:#fff; background:var(--app-primary); }
.history-case__timeline-filter small { display:grid; min-width:18px; height:18px; place-items:center; padding:0 5px; border-radius:999px; color:var(--app-muted); background:#edf1f5; font-size:8px; }
.history-case__timeline-filter button.is-active small { color:var(--app-primary-deep); background:#fff; }
.history-case__data-section { margin-top: 15px; }
.history-case__section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 15px; }
.history-case__section-heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 25px; }
.history-case__section-heading > span { color: var(--app-muted); font-size: 12px; }
.history-case__record-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.history-case__record { padding: 14px; border: 1px solid #e5e9f0; border-radius: 9px; background: #fbfcfe; }
.history-case__record h3 { margin: 0 0 10px; color: var(--app-ink); font-size: 14px; }
.history-case__record dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 12px; margin: 0; }
.history-case__record dl div { display: grid; gap: 3px; min-width: 0; }
.history-case__record dd { margin: 0; overflow-wrap: anywhere; color: var(--app-ink-soft); font-size: 12px; line-height: 1.5; }
.history-case__technical { margin-top: 12px; padding-top: 10px; border-top: 1px solid #e5e9f0; }
.history-case__technical summary { color: var(--app-muted); cursor: pointer; font-size: 11px; font-weight: 800; }
.history-case__technical dl { margin: 10px 0 0; }
.history-case__technical code { color: var(--app-ink-soft); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
.history-case__empty { margin: 0; color: var(--app-muted); font-size: 13px; }
.history-case__version-section { display:grid; gap:16px; margin-top:15px; padding:20px; border:1px solid var(--app-line); border-radius:var(--app-radius-sm); background:#fff; box-shadow:var(--app-shadow-soft); }
.history-case__version-meta { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:8px; }
.history-case__version-meta article { display:grid; gap:4px; padding:12px; border:1px solid var(--app-line); border-radius:9px; background:var(--app-surface-muted); }
.history-case__version-meta strong { color:var(--app-ink); font-size:12px; }
.history-case__version-meta span { color:var(--app-ink-soft); font-size:11px; }
.history-case__version-meta small { color:var(--app-muted); font-size:9px; }
.history-case__diff-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
.history-case__diff-grid > article { display:grid; gap:10px; padding:14px; border:1px solid var(--app-line); border-radius:10px; background:#fbfcfe; }
.history-case__diff-grid h3 { margin:0; color:var(--app-ink); font-size:13px; }
.history-case__diff-values { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); gap:8px; align-items:stretch; }
.history-case__diff-values > div { display:grid; align-content:start; gap:4px; padding:10px; border:1px solid #e3e9f0; border-radius:8px; background:#fff; }
.history-case__diff-values > div.is-current { border-color:#bfd8ca; background:#f3f9f6; }
.history-case__diff-values span { color:var(--app-muted); font-size:9px; font-weight:800; }
.history-case__diff-values strong { overflow-wrap:anywhere; color:var(--app-ink); font-size:13px; }
.history-case__diff-values small { color:var(--app-muted); font-size:9px; }
.history-case__diff-values p { margin:4px 0 0; color:var(--app-ink-soft); font-size:10px; line-height:1.55; white-space:pre-wrap; }
.history-case__diff-arrow { align-self:center; color:var(--app-primary) !important; font-size:16px !important; }
.history-case__change-log { display:grid; gap:10px; padding-top:4px; }
.history-case__change-log > h3 { margin:0; color:var(--app-ink); font-size:14px; }
.history-case__change-log ol { display:grid; gap:7px; margin:0; padding:0; list-style:none; }
.history-case__change-log li { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; padding:11px 12px; border-left:3px solid var(--app-primary); background:var(--app-surface-muted); }
.history-case__change-log li > div { display:grid; gap:3px; }
.history-case__change-log strong { color:var(--app-ink); font-size:11px; }
.history-case__change-log span { color:var(--app-ink-soft); font-size:11px; }
.history-case__change-log p { margin:2px 0 0; color:var(--app-muted); font-size:10px; }
.history-case__change-log small { color:var(--app-muted); font-size:9px; white-space:nowrap; }

@media (max-width: 900px) {
  .history-case { padding-inline: 18px; }
  .history-case__identity-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .history-case__overview-grid { grid-template-columns: 1fr; }
  .history-case__record-grid { grid-template-columns: 1fr; }
  .history-case__diff-grid { grid-template-columns:1fr; }
}

@media (max-width: 640px) {
  .history-case { padding-inline: 14px; }
  .history-case__flow { grid-template-columns:1fr; }
  .history-case__flow li + li { border-top:1px solid var(--app-line); border-left:0; }
  .history-case__flow small { white-space:normal; }
  .history-case__identity-heading { flex-direction:column; }
  .history-case__identity-status { justify-content: flex-start; }
  .history-case__identity-grid { grid-template-columns:1fr; }
  .history-case__identity-footer { align-items:flex-start; flex-direction:column; }
  .history-case__document-preview > header { flex-direction:column; }
  .history-case__document-frame { min-height:420px; }
  .history-case__parcel-list { grid-template-columns: 1fr; }
  .history-case__record dl { grid-template-columns: 1fr; }
  .history-case__diff-values { grid-template-columns:1fr; }
  .history-case__diff-arrow { justify-self:center; transform:rotate(90deg); }
  .history-case__change-log li { flex-direction:column; }
}
</style>
