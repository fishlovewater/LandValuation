<script setup lang="ts">
import type { ExtractedFieldResponseDto } from '../valuation.types'

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
  candidateStatusLabel: (status: string) => string
  displayCandidateValue: (value: unknown) => string
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

    <p v-if="!candidates.length" class="empty-copy">目前沒有需要人工確認的辨識結果。可在上方來源文件開始辨識。</p>
    <div v-else class="candidate-list">
      <article
        v-for="candidate in candidates"
        :key="candidate.extracted_field_id"
        :class="['candidate-card', { 'is-active': selectedCandidateId === candidate.extracted_field_id }]"
        :data-testid="`candidate-${candidate.extracted_field_id}`"
        @click="emit('select', candidate.extracted_field_id)"
      >
        <div class="candidate-card__heading">
          <div>
            <strong>{{ fieldDisplayLabel(candidate.form_code, candidate.field_name) }}</strong>
            <span>{{ candidateDocumentName(candidate.document_id) }}{{ candidate.source_page ? ` · 第 ${candidate.source_page} 頁` : '' }}</span>
          </div>
          <small>{{ candidate.field_status === 'NEEDS_CONFIRMATION' ? '待確認' : '重新確認中' }} · 信心度 {{ candidateConfidenceLabel(candidate) }} · {{ candidateProviderLabel(candidate.analysis_provider) }}</small>
        </div>
        <div v-if="candidate.source_text" class="candidate-card__source-summary">
          <span>來源原文</span>
          <blockquote class="candidate-card__source">{{ candidate.source_text }}</blockquote>
          <button class="candidate-card__source-link" type="button" @click.stop="emit('openSource', candidate)">在原文件中查看</button>
        </div>
        <label class="candidate-card__value">
          <span>辨識值／人工修正值 <small v-if="candidateUnit(candidate)">({{ candidateUnit(candidate) }})</small></span>
          <input
            :value="candidateValue[candidate.extracted_field_id] ?? ''"
            :data-testid="`candidate-value-${candidate.extracted_field_id}`"
            :type="candidateEditorType(candidate)"
            :step="candidateEditorType(candidate) === 'number' ? 'any' : undefined"
            :disabled="candidateDecision[candidate.extracted_field_id] === 'REJECT'"
            @input="emit('updateValue', candidate.extracted_field_id, ($event.target as HTMLInputElement).value)"
          >
        </label>
        <div class="candidate-card__actions" role="group" :aria-label="`${candidate.field_name} 人工判定`">
          <button type="button" :class="{ 'is-selected': candidateDecision[candidate.extracted_field_id] === 'CONFIRM' }" :data-testid="`candidate-confirm-${candidate.extracted_field_id}`" @click="emit('chooseDecision', candidate.extracted_field_id, 'CONFIRM')">確認採用</button>
          <button type="button" :class="{ 'is-selected is-reject': candidateDecision[candidate.extracted_field_id] === 'REJECT' }" :data-testid="`candidate-reject-${candidate.extracted_field_id}`" @click="emit('chooseDecision', candidate.extracted_field_id, 'REJECT')">標記不採用</button>
          <button v-if="candidate.field_status !== 'NEEDS_CONFIRMATION'" class="candidate-card__restore" type="button" :data-testid="`cancel-reopen-candidate-${candidate.extracted_field_id}`" @click.stop="emit('cancelReopen', candidate)">取消修改／還原</button>
        </div>
      </article>
      <div class="candidate-submit">
        <span>已選擇 {{ selectedCandidateCount }} / {{ candidates.length }} 筆判定。按右側按鈕後才會正式保存並套用。</span>
        <button class="solid-button solid-button--primary" type="button" data-testid="submit-candidate-decisions" :disabled="!selectedCandidateCount || confirmingCandidates" @click="emit('submit')">
          {{ confirmingCandidates ? '保存判定中…' : '保存已選判定並套用' }}
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
            <strong>{{ fieldDisplayLabel(candidate.form_code, candidate.field_name) }}</strong>
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
.surface-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.surface-heading h2{margin:0;color:var(--app-ink);font-family:var(--app-font-display);font-size:24px;font-weight:600;letter-spacing:-.04em}.valuation-eyebrow{margin:0 0 6px;color:var(--app-accent-deep);font-size:11px;font-weight:800;letter-spacing:.12em}.value-kind{display:inline-flex;min-height:30px;align-items:center;padding:5px 10px;border:1px solid var(--app-line);border-radius:var(--app-radius-pill);color:var(--app-ink-soft);background:#f7f8fb;font-size:11px;font-weight:800;white-space:nowrap}
.candidate-workspace{border-color:rgba(46,89,132,.18)}.candidate-workspace__summary{display:flex;align-items:center;flex-wrap:wrap;justify-content:flex-end;gap:8px}.candidate-list{display:grid;gap:10px}.candidate-card{display:grid;gap:12px;padding:15px;border:1px solid var(--app-line);border-radius:11px;background:#fbfcfe;cursor:default;transition:border-color 120ms ease,box-shadow 120ms ease}.candidate-card.is-active{border-color:rgba(46,89,132,.4);box-shadow:0 0 0 3px rgba(46,89,132,.08)}.candidate-card__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.candidate-card__heading>div{display:grid;gap:4px;min-width:0}.candidate-card__heading strong{color:var(--app-ink);font-size:13px}.candidate-card__heading span,.candidate-card__heading small{color:var(--app-muted);font-size:10px}.candidate-card__source{margin:0;padding:10px 12px;border-left:3px solid rgba(46,89,132,.35);color:var(--app-ink-soft);background:#f3f7fb;font-size:12px;line-height:1.65;white-space:pre-wrap}.candidate-card__source-summary{display:grid;gap:6px}.candidate-card__source-summary>span{color:var(--app-muted);font-size:10px;font-weight:850}.candidate-card__source-link{justify-self:start;padding:0;border:0;color:#2e5984;background:transparent;cursor:pointer;font-size:11px;font-weight:850;text-decoration:underline;text-underline-offset:3px}.candidate-card__value{display:grid;gap:5px;color:var(--app-ink-soft);font-size:11px;font-weight:800}.candidate-card__value input{width:100%;min-height:44px;padding:9px 11px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-ink);background:#fff}.candidate-card__actions{display:flex;flex-wrap:wrap;gap:8px}.candidate-card__actions button{min-height:38px;padding:7px 12px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-ink-soft);background:#fff;cursor:pointer;font-size:11px;font-weight:900}.candidate-card__actions button.is-selected{border-color:rgba(59,129,102,.4);color:var(--app-green);background:rgba(59,129,102,.08)}.candidate-card__actions button.is-reject{border-color:rgba(200,91,67,.35);color:var(--app-accent-deep);background:rgba(200,91,67,.07)}.candidate-card__actions button.candidate-card__restore{margin-left:auto;border-style:dashed;color:#52657a;background:#f7f9fb}.candidate-submit{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:4px}.candidate-submit>span{color:var(--app-muted);font-size:11px}.candidate-history{display:grid;gap:9px;margin-top:16px;padding-top:14px;border-top:1px solid var(--app-line)}.candidate-history__heading{display:grid;gap:3px}.candidate-history__heading strong{color:var(--app-ink);font-size:12px}.candidate-history__heading span{color:var(--app-muted);font-size:11px}.candidate-history ul{display:grid;gap:7px;margin:0;padding:0;list-style:none}.candidate-history li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 11px;border-radius:9px;background:rgba(247,249,252,.84)}.candidate-history li>div{display:grid;gap:3px;min-width:0}.candidate-history li strong{color:var(--app-ink);font-size:11px}.candidate-history li span{overflow-wrap:anywhere;color:var(--app-muted);font-size:10px}.finding-action{justify-self:start;min-height:36px;margin-top:5px;padding:6px 11px;border:1px solid rgba(200,91,67,.26);border-radius:8px;color:var(--app-accent-deep);background:#fff;cursor:pointer;font-size:11px;font-weight:900}.solid-button{min-height:44px;padding:10px 16px;border:1px solid var(--app-line);border-radius:9px;color:var(--app-ink-soft);background:var(--app-paper-strong);cursor:pointer;font-size:13px;font-weight:800}.solid-button--primary{border-color:var(--app-accent);color:#fff;background:var(--app-accent)}.solid-button:disabled{cursor:not-allowed;opacity:.55}.empty-copy{margin:0;color:var(--app-muted);font-size:13px}
@media(max-width:760px){.valuation-surface{padding:16px}.surface-heading,.candidate-card__heading,.candidate-submit,.candidate-history li{align-items:stretch;flex-direction:column}.candidate-workspace__summary{justify-content:flex-start}.solid-button{width:100%}}
</style>
