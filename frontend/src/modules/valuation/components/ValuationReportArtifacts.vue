<script setup lang="ts">
import {
  PhDownloadSimple as DownloadSimple,
  PhFilePdf as FilePdf,
  PhFileText as FileText,
} from '@phosphor-icons/vue'
import type { FormalReportModel, ReportArtifactModel } from '../valuation.types'

const props = defineProps<{
  formalReport: FormalReportModel | null
  report: ReportArtifactModel | null
  downloadingDocumentId: string | null
}>()

const emit = defineEmits<{
  download: [documentId: string, filename: string]
}>()

function fileSizeKb(bytes: number): number {
  return Math.max(1, Math.round(bytes / 1024))
}

function isDownloading(documentId: string): boolean {
  return props.downloadingDocumentId === documentId
}
</script>

<template>
  <section
    v-if="props.formalReport"
    class="report-artifact"
    data-testid="formal-pdf-result"
    aria-labelledby="formal-pdf-title"
  >
    <div class="report-artifact__heading">
      <div class="report-artifact__title">
        <span class="report-artifact__icon" aria-hidden="true">
          <FilePdf :size="21" weight="duotone" />
        </span>
        <div>
          <p>正式文件</p>
          <h2 id="formal-pdf-title">完整送審 PDF</h2>
        </div>
      </div>
      <span class="report-artifact__marker">正式版本</span>
    </div>

    <div class="report-artifact__file">
      <strong>{{ props.formalReport.filename }}</strong>
      <span>第 {{ props.formalReport.versionNo }} 版｜檔案大小 {{ fileSizeKb(props.formalReport.fileSizeBytes) }} KB</span>
      <small>這是主要送審產物。頁數依本案實際查估書表與附圖內容產生，不以固定頁數作為流程條件。</small>
      <button
        class="is-primary"
        type="button"
        data-testid="download-formal-report"
        :disabled="Boolean(props.downloadingDocumentId)"
        @click="emit('download', props.formalReport.documentId, props.formalReport.filename)"
      >
        <DownloadSimple v-if="!isDownloading(props.formalReport.documentId)" :size="16" weight="bold" aria-hidden="true" />
        <span>{{ isDownloading(props.formalReport.documentId) ? '下載中…' : '下載完整送審 PDF' }}</span>
      </button>
    </div>
  </section>

  <section v-if="props.report" class="report-artifact" aria-labelledby="f03-artifact-title">
    <div class="report-artifact__heading">
      <div class="report-artifact__title">
        <span class="report-artifact__icon" aria-hidden="true">
          <FileText :size="21" weight="duotone" />
        </span>
        <div>
          <p>流程附件</p>
          <h2 id="f03-artifact-title">比準地地價估計表單表輸出</h2>
        </div>
      </div>
      <span class="report-artifact__marker">系統產生</span>
    </div>

    <div class="report-artifact__file">
      <strong>{{ props.report.filename }}</strong>
      <span>第 {{ props.report.versionNo }} 版｜檔案大小 {{ fileSizeKb(props.report.fileSizeBytes) }} KB</span>
      <small>這是前段比準地地價估計表計算產生的單表輸出，保留作流程追溯；正式送審仍以完整送審 PDF 為主。</small>
      <button
        type="button"
        data-testid="download-f03-report"
        :disabled="Boolean(props.downloadingDocumentId)"
        @click="emit('download', props.report.documentId, props.report.filename)"
      >
        <DownloadSimple v-if="!isDownloading(props.report.documentId)" :size="16" weight="bold" aria-hidden="true" />
        <span>{{ isDownloading(props.report.documentId) ? '下載中…' : '下載比準地地價估計表單表' }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.report-artifact { display: grid; gap: 16px; padding: 22px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #fff; }
.report-artifact__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.report-artifact__title { display: flex; align-items: flex-start; gap: 11px; min-width: 0; }
.report-artifact__icon { display: grid; width: 38px; height: 38px; flex: 0 0 auto; place-items: center; border-radius: 9px; color: #2e5984; background: #edf4fb; }
.report-artifact__title p { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.report-artifact__title h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; font-weight: 600; letter-spacing: -.035em; }
.report-artifact__marker { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 10px; border: 1px solid rgba(46,89,132,.22); border-radius: var(--app-radius-pill); color: #2e5984; background: #edf4fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.report-artifact__file { display: grid; gap: 5px; padding: 16px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.report-artifact__file strong { color: var(--app-ink); font-size: 15px; overflow-wrap: anywhere; }
.report-artifact__file > span,
.report-artifact__file small { color: var(--app-ink-soft); font-size: 12px; }
.report-artifact__file small { color: var(--app-muted); line-height: 1.55; }
.report-artifact__file button { display: inline-flex; min-height: 42px; width: fit-content; align-items: center; justify-content: center; gap: 7px; margin-top: 8px; padding: 9px 15px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 12px; font-weight: 800; }
.report-artifact__file button.is-primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.report-artifact__file button:disabled { cursor: not-allowed; opacity: .55; }

@media (max-width: 760px) {
  .report-artifact { padding: 16px; }
  .report-artifact__heading { flex-direction: column; }
  .report-artifact__file button { width: 100%; }
}
</style>