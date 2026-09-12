<script setup lang="ts">
import { computed } from 'vue'
import {
  PhCheckCircle as CheckCircle,
  PhFileSearch as FileSearch,
  PhXCircle as XCircle,
} from '@phosphor-icons/vue'
import DocumentTextPreview from '../../../components/common/DocumentTextPreview.vue'
import SpreadsheetPreview from '../../../components/common/SpreadsheetPreview.vue'
import type { DocumentTextPreviewDto } from '../../../types/documentPreview'
import type { SpreadsheetPreviewDto } from '../../../types/spreadsheet'
import type { DocumentArtifactModel, ExtractedFieldResponseDto } from '../valuation.types'

const props = defineProps<{
  candidates: ExtractedFieldResponseDto[]
  processedCandidates: ExtractedFieldResponseDto[]
  pendingCount: number
  selectedCandidateId: string | null
  selectedCandidateCount: number
  candidateDecision: Record<string, 'CONFIRM' | 'REJECT' | ''>
  candidateValue: Record<string, string>
  confirmingCandidates: boolean
  hasConfirmationExport: boolean
  fieldDisplayLabel: (formCode: string, fieldName: string) => string
  candidateDocumentName: (documentId: string) => string
  candidateConfidenceLabel: (candidate: ExtractedFieldResponseDto) => string
  candidateProviderLabel: (provider: string) => string
  candidateUnit: (candidate: ExtractedFieldResponseDto) => string
  candidateEditorType: (candidate: ExtractedFieldResponseDto) => string
  candidateInputType: (candidate: ExtractedFieldResponseDto) => 'date' | 'text'
  candidateInputMode: (candidate: ExtractedFieldResponseDto) => 'decimal' | undefined
  candidateStatusLabel: (status: string) => string
  displayCandidateValue: (value: unknown) => string
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
}>()

const emit = defineEmits<{
  select: [candidateId: string]
  openSource: [candidate: ExtractedFieldResponseDto]
  chooseDecision: [candidateId: string, decision: 'CONFIRM' | 'REJECT']
  updateValue: [candidateId: string, value: string]
  cancelReopen: [candidate: ExtractedFieldResponseDto]
  reopen: [candidate: ExtractedFieldResponseDto]
  submit: []
  downloadExport: []
}>()

const activeCandidate = computed(() => (
  props.candidates.find((candidate) => candidate.extracted_field_id === props.selectedCandidateId)
  ?? props.candidates[0]
  ?? null
))
</script>

<template>
  <section
    id="valuation-candidate-workspace"
    class="valuation-surface candidate-workspace"
    data-testid="valuation-candidate-workspace"
    tabindex="-1"
    aria-labelledby="candidate-workspace-title"
  >
    <div class="surface-heading">
      <div>
        <p class="valuation-eyebrow">文件辨識</p>
        <h2 id="candidate-workspace-title">待確認的辨識結果</h2>
      </div>
      <div class="candidate-workspace__summary">
        <span class="value-kind">待確認 {{ pendingCount }} 筆</span>
        <button v-if="hasConfirmationExport" class="finding-action" type="button" data-testid="download-confirmation-export" @click="emit('downloadExport')">下載確認 Excel</button>
      </div>
    </div>
    <p class="candidate-workspace__policy">本次掃描只採用原文件中可直接核對的證據；沒有資料或沒有對應表單區段的欄位會保持空白，不會由 AI 推測。</p>

    <div v-if="!candidates.length" class="candidate-empty">
      <CheckCircle :size="30" weight="duotone" aria-hidden="true" />
      <strong>目前沒有待確認的辨識結果</strong>
      <span>可回到「文件與辨識」繼續處理其他來源文件，或前往下一階段補齊資料。</span>
    </div>
    <div v-else class="candidate-review-layout">
      <aside class="candidate-queue" aria-label="待確認欄位">
        <div class="candidate-queue__heading">
          <strong>待確認欄位</strong>
          <span>{{ candidates.length }} 筆</span>
        </div>
        <div class="candidate-queue__list">
          <button
            v-for="candidate in candidates"
            :key="candidate.extracted_field_id"
            type="button"
            :class="['candidate-queue__item', { 'is-active': activeCandidate?.extracted_field_id === candidate.extracted_field_id }]"
            :data-testid="`candidate-queue-${candidate.extracted_field_id}`"
            @click="emit('select', candidate.extracted_field_id)"
          >
            <span class="candidate-queue__status" :data-state="candidateDecision[candidate.extracted_field_id] || 'PENDING'">
              <CheckCircle v-if="candidateDecision[candidate.extracted_field_id] === 'CONFIRM'" :size="15" weight="fill" aria-hidden="true" />
              <XCircle v-else-if="candidateDecision[candidate.extracted_field_id] === 'REJECT'" :size="15" weight="fill" aria-hidden="true" />
              <FileSearch v-else :size="15" weight="regular" aria-hidden="true" />
            </span>
            <span class="candidate-queue__copy">
              <strong>{{ candidate.field_label || fieldDisplayLabel(candidate.form_code, candidate.field_name) }}</strong>
              <small>{{ candidate.form_code }} · {{ candidateConfidenceLabel(candidate) }}</small>
            </span>
          </button>
        </div>
      </aside>

      <article
        v-if="activeCandidate"
        class="candidate-detail"
        :data-testid="`candidate-${activeCandidate.extracted_field_id}`"
      >
        <header class="candidate-detail__heading">
          <div>
            <span>{{ activeCandidate.form_code }} · {{ candidateProviderLabel(activeCandidate.analysis_provider) }}</span>
            <h3>{{ activeCandidate.field_label || fieldDisplayLabel(activeCandidate.form_code, activeCandidate.field_name) }}</h3>
            <small>{{ candidateDocumentName(activeCandidate.document_id) }}{{ activeCandidate.source_page ? ` · 第 ${activeCandidate.source_page} 頁` : '' }}</small>
          </div>
          <span class="candidate-detail__confidence">信心度 {{ candidateConfidenceLabel(activeCandidate) }}</span>
        </header>

        <section class="candidate-detail__evidence" aria-label="原文件證據">
          <div class="candidate-detail__section-heading">
            <strong>原文件證據</strong>
            <button type="button" :data-testid="`candidate-source-${activeCandidate.extracted_field_id}`" @click="emit('openSource', activeCandidate)">在原文件中查看</button>
          </div>
          <div
            v-if="previewDocumentId === activeCandidate.document_id"
            class="candidate-source-preview"
            data-testid="candidate-source-preview"
          >
            <div class="candidate-source-preview__meta">
              <strong>{{ previewDocument?.filename || candidateDocumentName(activeCandidate.document_id) }}</strong>
              <span>{{ previewPage ? `第 ${previewPage} 頁` : '來源文件' }}</span>
            </div>
            <div class="candidate-source-preview__body">
              <p v-if="previewLoading">正在載入原文件…</p>
              <p v-else-if="previewError">{{ previewError }}</p>
              <iframe v-else-if="previewIsPdf && previewSourceUrl" :src="previewSourceUrl" title="AI 辨識來源 PDF 預覽" />
              <img v-else-if="previewIsImage && previewSourceUrl" :src="previewSourceUrl" :alt="previewDocument?.filename || 'AI 辨識來源文件'">
              <SpreadsheetPreview v-else-if="previewIsSpreadsheet && spreadsheetPreview" :preview="spreadsheetPreview" />
              <DocumentTextPreview v-else-if="previewIsDocx && textPreview" :preview="textPreview" />
              <blockquote v-else-if="activeCandidate.source_text">{{ activeCandidate.source_text }}</blockquote>
              <p v-else>這筆辨識結果沒有可直接顯示的來源原文，請開啟原文件確認。</p>
            </div>
          </div>
          <blockquote v-else-if="activeCandidate.source_text">{{ activeCandidate.source_text }}</blockquote>
          <p v-else>這筆辨識結果沒有可直接顯示的來源原文，請開啟原文件確認。</p>
        </section>

        <section class="candidate-detail__decision">
          <div class="candidate-detail__section-heading">
            <strong>人工確認</strong>
            <span>{{ activeCandidate.field_status === 'NEEDS_CONFIRMATION' ? '待確認' : '重新確認中' }}</span>
          </div>
          <label class="candidate-detail__value">
            <span>採用值 <small v-if="candidateUnit(activeCandidate)">({{ candidateUnit(activeCandidate) }})</small></span>
            <input
              :value="candidateValue[activeCandidate.extracted_field_id] ?? ''"
              :data-testid="`candidate-value-${activeCandidate.extracted_field_id}`"
              :type="candidateInputType(activeCandidate)"
              :inputmode="candidateInputMode(activeCandidate)"
              :placeholder="`請填寫：${activeCandidate.field_label || fieldDisplayLabel(activeCandidate.form_code, activeCandidate.field_name)}`"
              :disabled="candidateDecision[activeCandidate.extracted_field_id] === 'REJECT'"
              @input="emit('updateValue', activeCandidate.extracted_field_id, ($event.target as HTMLInputElement).value)"
            >
            <small v-if="activeCandidate.field_guidance" class="candidate-detail__guidance">{{ activeCandidate.field_guidance }}</small>
          </label>
          <div class="candidate-detail__actions" role="group" :aria-label="`${fieldDisplayLabel(activeCandidate.form_code, activeCandidate.field_name)} 人工判定`">
            <button type="button" class="candidate-detail__confirm" :class="{ 'is-selected': candidateDecision[activeCandidate.extracted_field_id] === 'CONFIRM' }" :data-testid="`candidate-confirm-${activeCandidate.extracted_field_id}`" @click="emit('chooseDecision', activeCandidate.extracted_field_id, 'CONFIRM')">
              <CheckCircle :size="16" weight="bold" aria-hidden="true" />確認採用
            </button>
            <button type="button" class="candidate-detail__reject" :class="{ 'is-selected': candidateDecision[activeCandidate.extracted_field_id] === 'REJECT' }" :data-testid="`candidate-reject-${activeCandidate.extracted_field_id}`" @click="emit('chooseDecision', activeCandidate.extracted_field_id, 'REJECT')">
              <XCircle :size="16" weight="bold" aria-hidden="true" />不採用
            </button>
            <button v-if="activeCandidate.field_status !== 'NEEDS_CONFIRMATION'" class="candidate-detail__restore" type="button" :data-testid="`cancel-reopen-candidate-${activeCandidate.extracted_field_id}`" @click="emit('cancelReopen', activeCandidate)">取消修改／還原</button>
          </div>
        </section>
      </article>

      <div class="candidate-submit">
        <span>已選擇 {{ selectedCandidateCount }} / {{ candidates.length }} 筆判定。按右側按鈕後才會正式儲存並套用。</span>
        <button class="solid-button solid-button--primary" type="button" data-testid="submit-candidate-decisions" :disabled="!selectedCandidateCount || confirmingCandidates" @click="emit('submit')">
          {{ confirmingCandidates ? '儲存判定中…' : '儲存已選判定並套用' }}
        </button>
      </div>
    </div>

    <div v-if="processedCandidates.length" class="candidate-history" data-testid="processed-candidates">
      <div class="candidate-history__heading">
        <strong>已處理的辨識結果</strong>
        <span>已採用或已略過的資料都可以重新判定；若不想變更，使用「取消修改／還原」即可回到原本已儲存狀態。</span>
      </div>
      <ul>
        <li v-for="candidate in processedCandidates" :key="`processed-${candidate.extracted_field_id}`">
          <div>
            <strong>{{ candidate.field_label || fieldDisplayLabel(candidate.form_code, candidate.field_name) }}</strong>
            <span>{{ candidateStatusLabel(candidate.field_status) }} · {{ displayCandidateValue(candidate.confirmed_value ?? candidate.extracted_value) || '未採用值' }}</span>
          </div>
          <button v-if="!candidateDecision[candidate.extracted_field_id]" class="finding-action" type="button" :data-testid="`reopen-candidate-${candidate.extracted_field_id}`" @click="emit('reopen', candidate)">{{ candidate.field_status === 'REJECTED' ? '重新判定' : '重新修改' }}</button>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.valuation-surface{padding:22px;border:1px solid var(--app-line);border-radius:var(--app-radius-md);background:var(--app-paper-strong);box-shadow:var(--app-shadow-soft)}
.candidate-workspace__policy{margin:-8px 0 16px;color:var(--app-muted);font-size:11px;line-height:1.6}
.surface-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.surface-heading h2{margin:0;color:var(--app-ink);font-family:var(--app-font-display);font-size:24px;font-weight:600;letter-spacing:-.04em}.valuation-eyebrow{margin:0 0 6px;color:var(--app-accent-deep);font-size:11px;font-weight:800;letter-spacing:.12em}.value-kind{display:inline-flex;min-height:30px;align-items:center;padding:5px 10px;border:1px solid var(--app-line);border-radius:var(--app-radius-pill);color:var(--app-ink-soft);background:#f7f8fb;font-size:11px;font-weight:800;white-space:nowrap}
.candidate-workspace{border-color:rgba(46,89,132,.18)}
.candidate-workspace__summary{display:flex;align-items:center;flex-wrap:wrap;justify-content:flex-end;gap:8px}
.candidate-empty{display:grid;min-height:260px;place-items:center;align-content:center;gap:7px;padding:28px;border:1px dashed #d3dee8;border-radius:10px;color:#4b8a70;background:#fbfefd;text-align:center}
.candidate-empty strong{color:var(--app-ink);font-size:13px}.candidate-empty span{max-width:480px;color:var(--app-muted);font-size:11px;line-height:1.6}
.candidate-review-layout{display:grid;grid-template-columns:minmax(240px,.72fr) minmax(0,1.65fr);gap:12px}
.candidate-queue{min-width:0;overflow:hidden;border:1px solid #dbe4ec;border-radius:10px;background:#fff}
.candidate-queue__heading{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 12px;border-bottom:1px solid #e7ecf1;background:#fafbfd}
.candidate-queue__heading strong{color:var(--app-ink);font-size:11px}.candidate-queue__heading span{color:var(--app-muted);font-size:9px;font-weight:850}
.candidate-queue__list{display:grid;max-height:560px;overflow:auto}
.candidate-queue__item{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:start;gap:8px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #edf1f4;color:inherit;background:#fff;cursor:pointer;text-align:left}
.candidate-queue__item:last-child{border-bottom:0}.candidate-queue__item.is-active{background:#f2f7fc;box-shadow:inset 3px 0 0 #2e5984}
.candidate-queue__status{display:grid;width:24px;height:24px;place-items:center;border-radius:7px;color:#75889b;background:#eef3f7}.candidate-queue__status[data-state="CONFIRM"]{color:#3b8166;background:#edf8f3}.candidate-queue__status[data-state="REJECT"]{color:#a14a3b;background:#fff0ed}
.candidate-queue__copy{display:grid;gap:3px;min-width:0}.candidate-queue__copy strong{overflow:hidden;color:var(--app-ink);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.candidate-queue__copy small{color:var(--app-muted);font-size:8px}
.candidate-detail{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.8fr);align-content:start;gap:14px;min-width:0;padding:16px;border:1px solid #dbe4ec;border-radius:10px;background:#fff}
.candidate-detail__heading{grid-column:1/-1;display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding-bottom:13px;border-bottom:1px solid #e8edf2}.candidate-detail__heading>div{display:grid;gap:4px;min-width:0}.candidate-detail__heading>div>span,.candidate-detail__heading small{color:var(--app-muted);font-size:9px}.candidate-detail__heading h3{margin:0;color:var(--app-ink);font-size:16px}.candidate-detail__confidence{flex:0 0 auto;padding:5px 8px;border-radius:999px;color:#2e5984;background:#edf4fb;font-size:9px;font-weight:850}
.candidate-detail__evidence,.candidate-detail__decision{display:grid;gap:9px}.candidate-detail__section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.candidate-detail__section-heading strong{color:var(--app-ink);font-size:11px}.candidate-detail__section-heading span{color:#925421;font-size:9px;font-weight:850}.candidate-detail__section-heading button{padding:0;border:0;color:#2e5984;background:transparent;cursor:pointer;font-size:9px;font-weight:850;text-decoration:underline;text-underline-offset:3px}
.candidate-detail__evidence blockquote{min-height:92px;margin:0;padding:12px 13px;border-left:3px solid #9cb5cc;border-radius:0 8px 8px 0;color:#405367;background:#f5f8fb;font-size:11px;line-height:1.7;white-space:pre-wrap}.candidate-detail__evidence p{margin:0;padding:12px;border-radius:8px;color:var(--app-muted);background:#f7f9fb;font-size:10px;line-height:1.6}
.candidate-source-preview{display:grid;gap:7px;overflow:hidden;border:1px solid #dbe4ec;border-radius:8px;background:#f7f9fb}.candidate-source-preview__meta{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 10px;border-bottom:1px solid #e2e8ee;background:#fff}.candidate-source-preview__meta strong{overflow:hidden;color:#405367;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.candidate-source-preview__meta span{flex:0 0 auto;color:var(--app-muted);font-size:8px}.candidate-source-preview__body{display:grid;min-height:280px;max-height:440px;place-items:center;overflow:auto;background:#edf1f4}.candidate-source-preview__body iframe{width:100%;height:430px;border:0;background:#fff}.candidate-source-preview__body img{display:block;max-width:100%;max-height:420px;object-fit:contain}.candidate-source-preview__body>p{margin:0;background:transparent;text-align:center}.candidate-source-preview__body>blockquote{align-self:stretch;margin:12px!important}
.candidate-detail__decision{padding-top:2px}.candidate-detail__value{display:grid;gap:6px;color:var(--app-ink-soft);font-size:10px;font-weight:850}.candidate-detail__value input{width:100%;min-height:44px;padding:9px 10px;border:1px solid #cad6e1;border-radius:8px;color:var(--app-ink);background:#fff;font:inherit}.candidate-detail__value input:focus{outline:3px solid rgba(46,89,132,.1);border-color:#2e5984}.candidate-detail__guidance{color:var(--app-muted);font-size:9px;font-weight:500;line-height:1.55}
.candidate-detail__actions{display:flex;flex-wrap:wrap;gap:7px}.candidate-detail__actions button{display:inline-flex;min-height:38px;align-items:center;justify-content:center;gap:5px;padding:7px 11px;border:1px solid #d2dce5;border-radius:8px;background:#fff;cursor:pointer;font-size:10px;font-weight:900}.candidate-detail__confirm{color:#35775f}.candidate-detail__confirm.is-selected{border-color:#9bc8b4;background:#edf8f3}.candidate-detail__reject{color:#9a4638}.candidate-detail__reject.is-selected{border-color:#e4b9b1;background:#fff0ed}.candidate-detail__restore{margin-left:auto;color:#607286;border-style:dashed!important;background:#f8fafc!important}
.candidate-submit{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 0 0;border-top:1px solid #e8edf2}.candidate-submit>span{color:var(--app-muted);font-size:10px}
.candidate-history{display:grid;gap:9px;margin-top:16px;padding-top:14px;border-top:1px solid var(--app-line)}.candidate-history__heading{display:grid;gap:3px}.candidate-history__heading strong{color:var(--app-ink);font-size:12px}.candidate-history__heading span{color:var(--app-muted);font-size:11px}.candidate-history ul{display:grid;gap:7px;margin:0;padding:0;list-style:none}.candidate-history li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 11px;border-radius:9px;background:rgba(247,249,252,.84)}.candidate-history li>div{display:grid;gap:3px;min-width:0}.candidate-history li strong{color:var(--app-ink);font-size:11px}.candidate-history li span{overflow-wrap:anywhere;color:var(--app-muted);font-size:10px}.finding-action{justify-self:start;min-height:36px;margin-top:5px;padding:6px 11px;border:1px solid rgba(200,91,67,.26);border-radius:8px;color:var(--app-accent-deep);background:#fff;cursor:pointer;font-size:11px;font-weight:900}.solid-button{min-height:44px;padding:10px 16px;border:1px solid var(--app-line);border-radius:9px;color:var(--app-ink-soft);background:var(--app-paper-strong);cursor:pointer;font-size:13px;font-weight:800}.solid-button--primary{border-color:var(--app-accent);color:#fff;background:var(--app-accent)}.solid-button:disabled{cursor:not-allowed;opacity:.55}
@media(max-width:1200px){.candidate-detail{grid-template-columns:1fr}.candidate-detail__heading{grid-column:auto}}
@media(max-width:900px){.candidate-review-layout{grid-template-columns:1fr}.candidate-queue__list{max-height:260px}.candidate-submit{grid-column:auto}}
@media(max-width:760px){.valuation-surface{padding:16px}.surface-heading,.candidate-submit,.candidate-history li,.candidate-detail__heading{align-items:stretch;flex-direction:column}.candidate-workspace__summary{justify-content:flex-start}.candidate-detail__confidence{width:fit-content}.candidate-detail__restore{margin-left:0}.solid-button{width:100%}}
</style>
