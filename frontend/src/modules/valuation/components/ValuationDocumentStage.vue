<script setup lang="ts">
import { PhArrowRight as ArrowRight } from '@phosphor-icons/vue'
import type { DocumentTextPreviewDto } from '../../../types/documentPreview'
import type { SpreadsheetPreviewDto } from '../../../types/spreadsheet'
import type {
  DocumentArtifactModel,
  DocumentCategory,
  ExtractedFieldResponseDto,
  ParcelImportPreviewDto,
  ParcelImportRowDto,
} from '../valuation.types'
import ValuationDocumentWorkspace from './ValuationDocumentWorkspace.vue'
import ValuationParcelImportPanel from './ValuationParcelImportPanel.vue'

type FieldAnalysisFormCode = 'S01' | 'F01' | 'F02' | 'F02-RF' | 'F03' | 'F04'

const props = defineProps<{
  documents: DocumentArtifactModel[]
  pendingCandidateCount: number
  previewDocumentId: string | null
  previewDocument: DocumentArtifactModel | null
  previewPage: number | null
  previewLoading: boolean
  previewError: string
  previewSourceUrl: string
  previewIsPdf: boolean
  previewIsImage: boolean
  previewIsSpreadsheet: boolean
  previewIsDocx: boolean
  spreadsheetPreview: SpreadsheetPreviewDto | null
  textPreview: DocumentTextPreviewDto | null
  selectedCandidate: ExtractedFieldResponseDto | null
  canUpload: boolean
  uploading: boolean
  uploadFile: File | null
  uploadCategory: DocumentCategory
  extractionBusyDocumentId: string | null
  documentActionId: string | null
  documentCategoryDraft: Record<string, DocumentCategory>
  documentAnalysisForm: Record<string, FieldAnalysisFormCode>
  analysisFormCodes: readonly FieldAnalysisFormCode[]
  sourceCategories: readonly DocumentCategory[]
  parcelImportPreview: ParcelImportPreviewDto | null
  parcelImportLoading: boolean
  parcelImporting: boolean
  canImportParcels: boolean
  caseDistrictCode: string
  formDisplayName: (code: string) => string
  documentCategoryLabel: (category: string) => string
  formatFileSize: (bytes: number) => string
  documentPendingCount: (documentId: string) => number
  documentCandidateCount: (documentId: string) => number
  documentAiStatus: (documentId: string) => string
  canExtractDocument: (document: DocumentArtifactModel) => boolean
  canManageSourceDocument: (document: DocumentArtifactModel) => boolean
}>()

const emit = defineEmits<{
  preview: [documentId: string]
  prepareParcelImport: [documentId: string]
  extract: [documentId: string]
  reclassify: [documentId: string]
  remove: [documentId: string, filename: string]
  download: [document: DocumentArtifactModel]
  updateAnalysisForm: [documentId: string, formCode: FieldAnalysisFormCode]
  updateCategory: [documentId: string, category: DocumentCategory]
  updateUploadCategory: [category: DocumentCategory]
  chooseUpload: [event: Event | File]
  upload: []
  importParcels: [rows: ParcelImportRowDto[]]
}>()
</script>

<template>
  <section class="document-stage" aria-labelledby="documents-stage-title">
    <div class="document-stage__heading">
      <div>
        <p class="document-stage__eyebrow">文件與辨識</p>
        <h2 id="documents-stage-title">來源文件與智能辨識</h2>
      </div>
      <span class="document-stage__count">{{ props.documents.length }} 份來源文件</span>
    </div>

    <section
      class="document-ai-process"
      data-testid="document-ai-process-guide"
      aria-label="文件辨識處理順序"
    >
      <article>
        <span class="document-ai-process__step">1</span>
        <div>
          <strong>先確認來源文件並執行辨識</strong>
          <small>目前有 {{ props.documents.length }} 份來源文件；可先預覽，再選擇目標表單進行文件文字辨識與智能欄位分析。</small>
        </div>
      </article>
      <ArrowRight class="document-ai-process__arrow" :size="18" weight="bold" aria-hidden="true" />
      <article :data-state="props.pendingCandidateCount ? 'attention' : 'ready'">
        <span class="document-ai-process__step">2</span>
        <div>
          <strong>再人工確認辨識結果</strong>
          <small>{{ props.pendingCandidateCount ? `還有 ${props.pendingCandidateCount} 筆待確認；確認後才會寫入正式資料。` : '目前沒有待確認的辨識結果。' }}</small>
        </div>
      </article>
    </section>

    <ValuationDocumentWorkspace
      :documents="props.documents"
      :preview-document-id="props.previewDocumentId"
      :preview-document="props.previewDocument"
      :preview-page="props.previewPage"
      :preview-loading="props.previewLoading"
      :preview-error="props.previewError"
      :preview-source-url="props.previewSourceUrl"
      :preview-is-pdf="props.previewIsPdf"
      :preview-is-image="props.previewIsImage"
      :preview-is-spreadsheet="props.previewIsSpreadsheet"
      :preview-is-docx="props.previewIsDocx"
      :spreadsheet-preview="props.spreadsheetPreview"
      :text-preview="props.textPreview"
      :selected-candidate="props.selectedCandidate"
      :can-upload="props.canUpload"
      :uploading="props.uploading"
      :upload-file="props.uploadFile"
      :upload-category="props.uploadCategory"
      :extraction-busy-document-id="props.extractionBusyDocumentId"
      :document-action-id="props.documentActionId"
      :document-category-draft="props.documentCategoryDraft"
      :document-analysis-form="props.documentAnalysisForm"
      :analysis-form-codes="props.analysisFormCodes"
      :source-categories="props.sourceCategories"
      :form-display-name="props.formDisplayName"
      :document-category-label="props.documentCategoryLabel"
      :format-file-size="props.formatFileSize"
      :document-pending-count="props.documentPendingCount"
      :document-candidate-count="props.documentCandidateCount"
      :document-ai-status="props.documentAiStatus"
      :can-extract-document="props.canExtractDocument"
      :can-manage-source-document="props.canManageSourceDocument"
      @preview="emit('preview', $event)"
      @prepare-parcel-import="emit('prepareParcelImport', $event)"
      @extract="emit('extract', $event)"
      @reclassify="emit('reclassify', $event)"
      @remove="(documentId, filename) => emit('remove', documentId, filename)"
      @download="emit('download', $event)"
      @update-analysis-form="(documentId, formCode) => emit('updateAnalysisForm', documentId, formCode)"
      @update-category="(documentId, category) => emit('updateCategory', documentId, category)"
      @update-upload-category="emit('updateUploadCategory', $event)"
      @choose-upload="emit('chooseUpload', $event)"
      @upload="emit('upload')"
    />

    <ValuationParcelImportPanel
      v-if="props.parcelImportLoading || props.parcelImportPreview"
      :preview="props.parcelImportPreview"
      :case-district-code="props.caseDistrictCode"
      :loading="props.parcelImportLoading"
      :importing="props.parcelImporting"
      :can-import="props.canImportParcels"
      @import="emit('importParcels', $event)"
    />
  </section>
</template>

<style scoped>
.document-stage {
  display: grid;
  gap: 16px;
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-paper-strong);
}

.document-stage__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.document-stage__heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -.04em;
}

.document-stage__eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}

.document-stage__count {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-pill);
  color: var(--app-ink-soft);
  background: #f7f8fb;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.document-ai-process {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: stretch;
  gap: 10px;
  padding: 12px;
  border: 1px solid #d9e4ef;
  border-radius: 12px;
  background: #f8fbfe;
}

.document-ai-process article {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid #e1e8ef;
  border-radius: 10px;
  background: #fff;
}

.document-ai-process article[data-state="attention"] {
  border-color: #ead7b0;
  background: #fffaf0;
}

.document-ai-process article[data-state="ready"] {
  border-color: #cfe0d6;
  background: #f5faf7;
}

.document-ai-process article > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.document-ai-process strong {
  color: var(--app-ink);
  font-size: 12px;
}

.document-ai-process small {
  color: var(--app-muted);
  font-size: 10px;
  line-height: 1.55;
}

.document-ai-process__step {
  display: grid;
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  place-items: center;
  border-radius: 999px;
  color: #fff;
  background: #2e5984;
  font-size: 11px;
  font-weight: 900;
}

.document-ai-process__arrow {
  align-self: center;
  color: #708399;
}

@media (max-width: 760px) {
  .document-stage {
    padding: 16px;
  }

  .document-stage__heading {
    align-items: stretch;
    flex-direction: column;
  }

  .document-stage__count {
    width: fit-content;
  }

  .document-ai-process {
    grid-template-columns: 1fr;
  }

  .document-ai-process__arrow {
    justify-self: center;
    transform: rotate(90deg);
  }
}
</style>
