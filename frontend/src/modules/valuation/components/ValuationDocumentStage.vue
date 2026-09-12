<script setup lang="ts">
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
  reviewCandidates: []
  continueData: []
}>()
</script>

<template>
  <section class="document-stage" aria-label="來源資料">
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
      @review-candidates="emit('reviewCandidates')"
      @continue-data="emit('continueData')"
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
  gap: 10px;
  min-width: 0;
}

@media (max-width: 760px) {
  .document-stage { gap: 8px; }
}
</style>
