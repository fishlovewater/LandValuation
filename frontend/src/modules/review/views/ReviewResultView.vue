<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  PhDownloadSimple as DownloadSimple,
  PhFileDoc as FileDoc,
  PhFilePdf as FilePdf,
  PhFileXls as FileXls,
} from '@phosphor-icons/vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import { reviewApi, safeReviewErrorMessage } from '../review.api'
import { latestGeneratedReport, latestRunId, mapWorkbenchDetail, mimeTypeLabel, reviewStatusLabel } from '../review.mappers'
import type { GeneratedReportDto, ReviewDetailModel, ReviewReportDto } from '../review.types'

const route = useRoute()
const router = useRouter()
const detail = ref<ReviewDetailModel | null>(null)
const report = ref<ReviewReportDto | null>(null)
const generated = ref<GeneratedReportDto | null>(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const message = ref('')

const reviewId = computed(() => (typeof route.params.reviewId === 'string' ? route.params.reviewId : ''))
const runId = computed(() => (typeof route.query.runId === 'string' ? route.query.runId : '') || latestRunId(detail.value) || '')
const latestRun = computed(() => {
  const currentDetail = detail.value
  if (!currentDetail) return null
  return currentDetail.runs.find((run) => run.validationRunId === currentDetail.latestValidationRunId)
    ?? currentDetail.runs.reduce<typeof currentDetail.runs[number] | null>(
      (latest, run) => (!latest || (run.runNo ?? 0) > (latest.runNo ?? 0) ? run : latest),
      null,
    )
})
const canUseReport = computed(() => Boolean(
  detail.value?.reviewStatusCode === 'REVIEW_COMPLETED'
    && latestRun.value?.runStatusCode === 'COMPLETED'
    && runId.value === latestRun.value?.validationRunId,
))
const reportActionReason = computed(() => canUseReport.value
  ? ''
  : '案件完成且最新檢核完成後，才可產生或下載審查報告。')
const reportDocument = computed(() => generated.value ?? detail.value?.reportDocument ?? (detail.value ? latestGeneratedReport(detail.value.generatedReports) : null))
const reportInputLabel = computed(() => {
  const provenance = report.value?.input_provenance
  if (!provenance) return '尚未載入'
  const source = {
    PLATFORM: '平台送審',
    EXTERNAL: '外部案件',
    LEGACY: '舊版相容資料',
  }[provenance.source] ?? '審查輸入'
  return provenance.version_no === null ? source : `${source} v${provenance.version_no}`
})

function textField(value: unknown, fallback = '—'): string {
  return typeof value === 'string' && value.trim() ? value : fallback
}

async function load(): Promise<void> {
  if (!reviewId.value) return
  loading.value = true
  error.value = ''
  try {
    const detailDto = await reviewApi.getCase(reviewId.value)
    detail.value = mapWorkbenchDetail(detailDto)
    if (canUseReport.value) report.value = await reviewApi.getReport(runId.value)
    else report.value = null
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    loading.value = false
  }
}

async function generatePdf(): Promise<void> {
  if (!canUseReport.value || busy.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    generated.value = await reviewApi.generateReportPdf(runId.value)
    message.value = `已產生 ${generated.value.original_filename}。`
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    busy.value = false
  }
}

async function generateFormat(format: 'xlsx' | 'docx'): Promise<void> {
  if (!canUseReport.value || busy.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    generated.value = await reviewApi.generateReport(runId.value, { format })
    message.value = `已產生 ${generated.value.original_filename}。`
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    busy.value = false
  }
}

async function downloadReport(): Promise<void> {
  const document = reportDocument.value
  if (!document || !canUseReport.value || busy.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const blob = await reviewApi.downloadReport(document.document_id)
    if (typeof URL.createObjectURL === 'function') {
      const url = URL.createObjectURL(blob)
      const anchor = documentForDownload(url, document.original_filename)
      anchor.click()
      anchor.remove()
      if (typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url)
    }
    message.value = `已準備下載 ${document.original_filename}。`
  } catch (caught: unknown) {
    error.value = safeReviewErrorMessage(caught)
  } finally {
    busy.value = false
  }
}

function documentForDownload(url: string, filename: string): HTMLAnchorElement {
  const anchor = window.document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  return anchor
}

function backToWorkbench(): void {
  if (!reviewId.value) return
  void router.push({ name: 'review-workbench', params: { reviewId: reviewId.value }, query: { runId: runId.value } })
}

onMounted(load)
</script>

<template>
  <section class="review-result" data-testid="review-result">
    <PageHeader
      eyebrow="審查結果"
      title="審查結果"
      :description="detail ? `${detail.caseNo} · ${detail.caseTitle}` : '查看授權的審查報告與輸出。'"
    >
      <template #actions><button type="button" class="review-result__back" data-testid="result-back-to-workbench" @click="backToWorkbench">返回案件審查</button></template>
    </PageHeader>

    <LoadingSkeleton v-if="loading" :rows="6" label="審查結果載入中" />
    <ErrorState v-else-if="error && !detail" :message="error" @retry="load" />
    <EmptyState v-else-if="!reviewId" title="尚未選取審查案件" description="請先從案件審查頁面開啟審查結果。" />
    <template v-else-if="detail">
      <div class="review-result__toolbar">
        <div>
          <span>案件狀態</span>
          <strong>{{ reviewStatusLabel(detail.reviewStatusCode) }}</strong>
        </div>
        <div>
          <span>最新執行</span>
          <strong>{{ runId ? '已連結' : '尚無執行' }}</strong>
        </div>
        <div>
          <span>疑點</span>
          <strong>{{ report?.findings.length ?? detail.findings.length }} 筆</strong>
        </div>
      </div>
      <p v-if="error || message" class="review-result__message" :class="{ 'is-error': error }" role="status">{{ error || message }}</p>

      <section class="review-result__report" aria-labelledby="review-report-title">
        <div class="review-result__heading">
          <div>
            <p class="review-result__eyebrow">審查報告</p>
            <h2 id="review-report-title">結構化審查報告</h2>
          </div>
          <div class="review-result__actions">
            <button type="button" data-testid="generate-review-pdf" :disabled="!canUseReport || busy" :title="reportActionReason" @click="generatePdf">
              <FilePdf :size="16" weight="bold" aria-hidden="true" />
              <span>產生 PDF</span>
            </button>
            <button type="button" data-testid="generate-review-xlsx" :disabled="!canUseReport || busy" :title="reportActionReason" @click="generateFormat('xlsx')">
              <FileXls :size="16" weight="bold" aria-hidden="true" />
              <span>產生 Excel</span>
            </button>
            <button type="button" data-testid="generate-review-docx" :disabled="!canUseReport || busy" :title="reportActionReason" @click="generateFormat('docx')">
              <FileDoc :size="16" weight="bold" aria-hidden="true" />
              <span>產生 Word</span>
            </button>
            <button type="button" class="review-result__download" data-testid="download-review-report" :disabled="!reportDocument || !canUseReport || busy" :title="reportActionReason" @click="downloadReport">
              <DownloadSimple :size="16" weight="bold" aria-hidden="true" />
              <span>下載報告</span>
            </button>
          </div>
        </div>
        <p v-if="!canUseReport" class="review-result__disabled-reason" data-testid="review-report-disabled-reason">
          {{ reportActionReason }}
        </p>
        <div class="review-result__grid">
          <article class="review-result__card">
            <span>案件</span>
            <strong>{{ textField(report?.case?.case_no, detail.caseNo) }}</strong>
            <small>{{ textField(report?.case?.case_title, detail.caseTitle) }}</small>
          </article>
          <article class="review-result__card">
            <span>報告狀態</span>
            <strong>{{ report ? reviewStatusLabel(report.review_status) : '尚未載入' }}</strong>
            <small>未處理項目 {{ report?.missing_item_count ?? detail.missingItems.length }} 件</small>
          </article>
          <article class="review-result__card" data-testid="review-report-provenance">
            <span>審查依據</span>
            <strong>{{ reportInputLabel }}</strong>
            <small v-if="report?.input_provenance?.frozen_at">凍結於 {{ new Date(report.input_provenance.frozen_at).toLocaleString('zh-TW') }}</small>
            <small v-if="report?.input_provenance?.fingerprint" class="review-result__fingerprint">指紋 {{ report.input_provenance.fingerprint }}</small>
          </article>
          <article v-if="reportDocument" class="review-result__card review-result__card--file">
            <span>可下載文件</span>
            <strong>{{ reportDocument.original_filename }}</strong>
            <small>{{ mimeTypeLabel(reportDocument.mime_type) }} · 第 {{ reportDocument.version_no }} 版</small>
          </article>
          <article v-else class="review-result__card">
            <span>可下載文件</span>
            <strong>尚未產生</strong>
            <small>先產生一份報告，再使用授權下載。</small>
          </article>
        </div>
      </section>

      <section class="review-result__findings" aria-labelledby="result-findings-title">
        <div class="review-result__heading"><h2 id="result-findings-title">疑點摘要</h2><span>{{ detail.findings.length }} 筆</span></div>
        <ul>
          <li v-for="finding in detail.findings" :key="finding.findingId">
            <div><strong>{{ finding.title }}</strong><small>{{ finding.severityLabel }} · {{ finding.statusLabel }}</small></div>
            <p>{{ finding.description }}</p>
          </li>
          <li v-if="!detail.findings.length" class="review-result__none">目前沒有疑點。</li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.review-result { padding: 0 28px 34px; }
.review-result__back { min-height: 42px; padding: 8px 15px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.review-result__toolbar { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.review-result__toolbar > div { display: grid; gap: 4px; min-height: 78px; padding: 14px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: var(--app-paper-strong); }
.review-result__toolbar span,
.review-result__card span { color: var(--app-muted); font-size: 11px; font-weight: 800; }
.review-result__toolbar strong { color: var(--app-ink); font-size: 17px; }
.review-result__message { margin: 14px 0 0; color: var(--app-green); font-size: 13px; }
.review-result__message.is-error { color: #ac3c37; }
.review-result__report,
.review-result__findings { margin-top: 26px; padding: 20px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #fff; }
.review-result__heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.review-result__eyebrow { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 10px; font-weight: 900; letter-spacing: .14em; }
.review-result h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; }
.review-result__heading > span { color: var(--app-muted); font-size: 12px; }
.review-result__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.review-result__actions button { display: inline-flex; min-height: 42px; align-items: center; justify-content: center; gap: 7px; padding: 8px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font: inherit; font-size: 12px; font-weight: 800; }
.review-result__actions button:hover:not(:disabled) { border-color: rgba(46, 89, 132, .38); color: var(--app-accent-deep); background: #f8fafc; }
.review-result__actions button:disabled { cursor: not-allowed; opacity: .5; }
.review-result__actions .review-result__download { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.review-result__actions .review-result__download:hover:not(:disabled) { color: #fff; background: var(--app-accent-deep); }
.review-result__disabled-reason { margin: 14px 0 0; color: var(--app-muted); font-size: 12px; line-height: 1.6; }
.review-result__grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }
.review-result__card { display: grid; min-height: 104px; align-content: start; gap: 6px; padding: 14px; border: 1px solid var(--app-line); border-radius: 8px; background: #fbfcfe; }
.review-result__card strong { color: var(--app-ink); font-size: 15px; overflow-wrap: anywhere; }
.review-result__card small { color: var(--app-ink-soft); line-height: 1.5; }
.review-result__fingerprint { overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 9px; }
.review-result__card--file { border-color: #b8d0c0; background: #f4faf6; }
.review-result__findings ul { display: grid; gap: 8px; margin: 18px 0 0; padding: 0; list-style: none; }
.review-result__findings li { display: grid; gap: 6px; padding: 14px; border: 1px solid var(--app-line); border-radius: 8px; background: #fbfcfe; }
.review-result__findings li > div { display: flex; justify-content: space-between; gap: 12px; }
.review-result__findings strong { color: var(--app-ink); font-size: 14px; }
.review-result__findings small { color: var(--app-muted); font-size: 11px; }
.review-result__findings p { margin: 0; color: var(--app-ink-soft); font-size: 13px; line-height: 1.6; }
.review-result__none { color: var(--app-muted); }

@media (max-width: 980px) {
  .review-result { padding-inline: 18px; }
  .review-result__heading { align-items: flex-start; flex-direction: column; }
  .review-result__actions { justify-content: flex-start; }
  .review-result__grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 640px) {
  .review-result { padding-inline: 14px; }
  .review-result__toolbar, .review-result__grid { grid-template-columns: 1fr; }
  .review-result__report, .review-result__findings { padding: 14px; }
  .review-result__findings li > div { align-items: flex-start; flex-direction: column; }
}
</style>
