<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
import { historyApi, safeHistoryDownloadError, safeHistoryErrorMessage } from '../history.api'
import {
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
  HistoryValuationModel,
} from '../history.types'

type DetailTab = 'overview' | 'valuation' | 'review' | 'versions'
interface DisplayValue { value: string; technicalCode?: string }
interface DisplayField extends DisplayValue { label: string }
interface TechnicalField { label: string; code: string }
interface DisplayRecord { key: string; title: string; fields: DisplayField[]; technicalFields: TechnicalField[] }
type EnumLabeler = (value: string | null | undefined) => string

const route = useRoute()
const router = useRouter()
const detail = ref<HistoryCaseDetailModel | null>(null)
const loading = ref(false)
const error = ref('')
const message = ref('')
const activeTab = ref<DetailTab>('overview')
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

function safeRecordEntries(record: Record<string, unknown>): Array<[string, unknown]> {
  return Object.entries(record).filter(([key, value]) => {
    if (key === 'object_key' || key === 'bucket_name' || key === 'checksum_sha256') return false
    if (key.endsWith('_id') || key === 'id') return false
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

function displayFieldValue(key: string, value: unknown): DisplayValue {
  if (value === null || value === undefined || value === '') return { value: '—' }
  if (key.endsWith('_at') || key.endsWith('_date')) return { value: readableDate(value) }
  if (key === 'review_type') return displayEnumValue(value, reviewTypeLabel)
  if (key === 'review_status') return displayEnumValue(value, reviewStatusLabel)
  if (key === 'run_status') return displayEnumValue(value, runStatusLabel)
  if (key === 'overall_risk_level' || key === 'current_risk_level' || key === 'risk_level') return displayEnumValue(value, riskLevelLabel)
  if (key === 'finding_status' || key === 'status') return displayEnumValue(value, findingStatusLabel)
  if (key.endsWith('_status') || key === 'case_status') return displayEnumValue(value, statusLabel)
  if (key === 'valuation_type') return displayEnumValue(value, valuationTypeLabel)
  if (key === 'finding_code' || key === 'rule_code') return displayEnumValue(value, findingCodeLabel)
  if (key === 'finding_type') return displayEnumValue(value, findingTypeLabel)
  if (key === 'field_path') return displayEnumValue(value, fieldPathLabel)
  if (key === 'decision') return displayEnumValue(value, decisionLabel)
  if (key === 'severity') return displayEnumValue(value, severityLabel)
  if (key === 'ai_status') return displayEnumValue(value, aiStatusLabel)
  if (key === 'document_type') return displayEnumValue(value, documentTypeLabel)
  if (key === 'mime_type' || key === 'content_type') return displayEnumValue(value, mimeTypeLabel)
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
    ...displayRecords(valuation.forms, ['form_code'], '估價表單'),
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
    case: '案件', document: '文件', valuation: '估價資料', review: '審查資料', form: '估價表單',
  }
  return labels[value.toLowerCase()] ?? '案件資料'
}

function syncTab(): void {
  if (activeTab.value === 'valuation' && !hasValuation.value) activeTab.value = hasReview.value ? 'review' : 'overview'
  if (activeTab.value === 'review' && !hasReview.value) activeTab.value = hasValuation.value ? 'valuation' : 'overview'
  if (activeTab.value === 'versions' && !hasVersionHistory.value) activeTab.value = 'overview'
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
      eyebrow="案件歷程"
      :title="detail?.caseNo || '案件歷程明細'"
      :description="detail ? detail.caseTitle : '查看授權的案件資料、文件與歷程。'"
    >
      <template #actions>
        <button type="button" class="history-case__back" data-testid="history-back-search" @click="backToSearch">返回案件清單</button>
      </template>
    </PageHeader>

    <LoadingSkeleton v-if="loading && !detail" :rows="6" label="案件歷程明細載入中" />
    <ErrorState v-else-if="error && !detail" :message="error" @retry="load" />
    <EmptyState v-else-if="!caseId" title="尚未選取案件" description="請先從案件歷程清單開啟一筆案件。" />
    <template v-else-if="detail">
      <p v-if="error || message" class="history-case__message" :class="{ 'is-error': error }" role="status">{{ error || message }}</p>

      <section v-liquid-glass data-lg class="history-case__identity lg" aria-labelledby="history-case-identity-title">
        <div>
          <p class="history-case__eyebrow">案件資訊</p>
          <h2 id="history-case-identity-title">{{ detail.caseTitle }}</h2>
          <p class="history-case__identity-meta">{{ detail.caseNo }} · {{ detail.cityCode }} / {{ detail.districtCode }} · 基準日 {{ readableDate(detail.valuationBaseDate) }}</p>
        </div>
        <div class="history-case__identity-status">
          <StatusBadge :status="detail.caseStatusCode" />
          <RiskBadge v-if="detail.riskLevelCode" :risk="detail.riskLevelCode" />
        </div>
      </section>

      <nav class="history-case__tabs" aria-label="案件歷程資料區段">
        <button type="button" :class="{ 'is-active': activeTab === 'overview' }" data-testid="history-tab-overview" @click="activeTab = 'overview'">案件總覽</button>
        <button v-if="detail.permissions.canViewValuation" type="button" :class="{ 'is-active': activeTab === 'valuation' }" data-testid="history-tab-valuation" @click="activeTab = 'valuation'">
          <span>估價資料</span><small class="history-case__tab-count">{{ valuationItems.length }}</small>
        </button>
        <button v-if="detail.permissions.canViewReview" type="button" :class="{ 'is-active': activeTab === 'review' }" data-testid="history-tab-review" @click="activeTab = 'review'">
          <span>審查資料</span><small class="history-case__tab-count">{{ reviewItems.length }}</small>
        </button>
        <button v-if="hasVersionHistory" type="button" :class="{ 'is-active': activeTab === 'versions' }" data-testid="history-tab-versions" @click="activeTab = 'versions'">
          <span>版本比較</span><small class="history-case__tab-count">{{ detail.versionDiffs.length || detail.versions.length }}</small>
        </button>
      </nav>

      <template v-if="activeTab === 'overview'">
        <div class="history-case__overview-grid">
          <section v-liquid-glass data-lg class="history-case__facts lg" aria-labelledby="history-case-facts-title">
            <p class="history-case__eyebrow">基本資料</p>
            <h2 id="history-case-facts-title">案件基本資料</h2>
            <dl>
              <div><dt>案件編號</dt><dd>{{ detail.caseNo }}</dd></div>
              <div><dt>案件類型</dt><dd>{{ detail.caseType || '—' }}</dd></div>
              <div><dt>案件狀態</dt><dd>{{ detail.caseStatusLabel }}</dd></div>
              <div><dt>最後更新</dt><dd>{{ readableDate(detail.updatedAt) }}</dd></div>
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
        <section v-if="previewDocument" class="history-case__document-preview" data-testid="history-document-preview" aria-labelledby="history-document-preview-title">
          <header>
            <div>
              <p class="history-case__eyebrow">文件預覽</p>
              <h2 id="history-document-preview-title">{{ previewDocument.fileName }}</h2>
              <span>{{ previewDocument.documentTypeLabel }} · 第 {{ previewDocument.versionNo }} 版 · {{ previewDocument.sourceModuleLabel }}</span>
            </div>
            <button type="button" @click="clearDocumentPreview">關閉預覽</button>
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
        <CaseTimeline :events="detail.timeline" />
      </template>

      <section v-else-if="activeTab === 'valuation'" v-liquid-glass data-lg class="history-case__data-section lg" data-testid="history-valuation-section" aria-labelledby="history-valuation-title">
        <div class="history-case__section-heading">
          <div><p class="history-case__eyebrow">估價紀錄</p><h2 id="history-valuation-title">估價資料</h2></div>
          <span>{{ valuationItems.length }} 筆估價紀錄</span>
        </div>
        <p v-if="!valuationItems.length" class="history-case__empty">目前沒有可顯示的估價結構化資料。</p>
        <div v-else class="history-case__record-grid">
          <article v-for="item in valuationItems" :key="item.key" class="history-case__record">
            <h3>{{ item.title }}</h3>
            <dl><div v-for="field in item.fields" :key="`${item.key}-${field.label}`"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl>
          </article>
        </div>
      </section>

      <section v-else-if="activeTab === 'review'" v-liquid-glass data-lg class="history-case__data-section lg" data-testid="history-review-section" aria-labelledby="history-review-title">
        <div class="history-case__section-heading">
          <div><p class="history-case__eyebrow">審查紀錄</p><h2 id="history-review-title">審查資料</h2></div>
          <span>{{ reviewItems.length }} 筆審查紀錄</span>
        </div>
        <p v-if="!reviewItems.length" class="history-case__empty">目前沒有可顯示的審查結構化資料。</p>
        <div v-else class="history-case__record-grid">
          <article v-for="item in reviewItems" :key="item.key" class="history-case__record">
            <h3>{{ item.title }}</h3>
            <dl><div v-for="field in item.fields" :key="`${item.key}-${field.label}`"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl>
          </article>
        </div>
      </section>

      <section v-else-if="activeTab === 'versions'" class="history-case__version-section" data-testid="history-version-section" aria-labelledby="history-version-title">
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
                <strong>{{ readableValue(diff.previous.value) }}</strong>
                <small v-if="diff.previous.page_number">來源第 {{ diff.previous.page_number }} 頁</small>
                <p v-if="diff.previous.raw_text">{{ diff.previous.raw_text }}</p>
              </div>
              <span class="history-case__diff-arrow" aria-hidden="true">→</span>
              <div class="is-current">
                <span>修改後 · 第 {{ diff.current.document_version }} 版</span>
                <strong>{{ readableValue(diff.current.value) }}</strong>
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
                <span>{{ readableValue(change.old_value) }} → {{ readableValue(change.new_value) }}</span>
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
.history-case__identity { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-top: 12px; padding: 20px; border: 1px solid rgba(255,255,255,.72); border-radius: var(--app-radius-md); background: rgba(248,250,252,.74); box-shadow: var(--app-shadow-soft); }
.history-case__eyebrow { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 10px; font-weight: 900; letter-spacing: .15em; }
.history-case__identity h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 25px; }
.history-case__identity-meta { margin: 8px 0 0; color: var(--app-ink-soft); font-size: 12px; }
.history-case__identity-status { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.history-case__tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; border-bottom: 1px solid var(--app-line); }
.history-case__tabs button { display: inline-flex; min-height: 44px; align-items: center; gap: 7px; margin-bottom: -1px; padding: 8px 14px; border: 1px solid transparent; border-bottom: 2px solid transparent; border-radius: 8px 8px 0 0; color: var(--app-ink-soft); background: transparent; cursor: pointer; font-size: 13px; font-weight: 800; }
.history-case__tabs button:hover,
.history-case__tabs button.is-active { border-color: var(--app-line); border-bottom-color: var(--app-accent); color: var(--app-accent-deep); background: var(--app-paper-strong); }
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
.history-case__overview-grid + .case-timeline { margin-top: 15px; }
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
  .history-case__overview-grid { grid-template-columns: 1fr; }
  .history-case__record-grid { grid-template-columns: 1fr; }
  .history-case__diff-grid { grid-template-columns:1fr; }
}

@media (max-width: 640px) {
  .history-case { padding-inline: 14px; }
  .history-case__identity { flex-direction: column; }
  .history-case__identity-status { justify-content: flex-start; }
  .history-case__document-preview > header { flex-direction:column; }
  .history-case__document-frame { min-height:420px; }
  .history-case__parcel-list { grid-template-columns: 1fr; }
  .history-case__record dl { grid-template-columns: 1fr; }
  .history-case__diff-values { grid-template-columns:1fr; }
  .history-case__diff-arrow { justify-self:center; transform:rotate(90deg); }
  .history-case__change-log li { flex-direction:column; }
}
</style>
