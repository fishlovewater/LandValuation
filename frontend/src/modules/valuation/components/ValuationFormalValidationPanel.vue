<script setup lang="ts">
import {
  PhArrowRight as ArrowRight,
  PhFilePdf as FilePdf,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import type { FormalValidationFindingModel, FormalValidationModel } from '../valuation.types'

const props = defineProps<{
  validation: FormalValidationModel | null
  formalWarningCodes: string[]
  acknowledgedWarningCodes: string[]
  warningsAcknowledged: boolean
  formalValidating: boolean
  formalPdfGenerating: boolean
  submitting: boolean
  reportPackageReady: boolean
  authoritativeF02Status: string | null
}>()

const emit = defineEmits<{
  runValidation: []
  generatePdf: []
  fix: [finding: FormalValidationFindingModel]
  acknowledge: [code: string, checked: boolean]
}>()

function fieldLabel(code: string | null): string {
  if (!code) return ''
  const labels: Readonly<Record<string, string>> = {
    benchmark_land_id: '比準地',
    comparison_analysis_id: '比較分析',
    rule_version_id: '正式計算規則',
    comparison_targets: '比較案例',
    valuation_base_date: '估價基準日',
    comparison_price: '比較法價格',
    comparison_weight: '比較法權重',
    income_price: '收益法價格',
    income_weight: '收益法權重',
  }
  return labels[code] ?? '查估書資料欄位'
}

function isAcknowledged(code: string): boolean {
  return props.acknowledgedWarningCodes.includes(code)
}
</script>

<template>
  <section class="formal-validation-panel" aria-labelledby="formal-validation-title">
    <div class="formal-validation-panel__heading">
      <div>
        <p>正式檢核</p>
        <h2 id="formal-validation-title">完整報告正式檢核</h2>
      </div>
      <span
        v-if="props.validation"
        class="formal-validation-panel__status"
        :data-validation-state="props.validation.canGenerateFormalReport ? 'ready' : 'blocked'"
      >
        {{ props.validation.canGenerateFormalReport ? '可產生正式報告' : '仍有待修正項目' }}
      </span>
      <span v-else class="formal-validation-panel__status" data-validation-state="pending">尚未執行</span>
    </div>

    <div v-if="props.validation" data-testid="formal-validation-result">
      <div class="formal-validation-panel__counts">
        <span data-kind="passed">通過 {{ props.validation.passedCount }}</span>
        <span data-kind="warning">警示 {{ props.validation.warningCount }}</span>
        <span data-kind="error">錯誤 {{ props.validation.failedCount }}</span>
      </div>

      <ul v-if="props.validation.findings.length" class="formal-validation-panel__findings">
        <li
          v-for="finding in props.validation.findings"
          :key="`${finding.code}-${finding.fieldCode ?? ''}`"
          :data-severity="finding.severity"
        >
          <div class="formal-validation-panel__finding-icon" aria-hidden="true">
            <WarningCircle :size="18" weight="duotone" />
          </div>
          <div class="formal-validation-panel__finding-copy">
            <strong>{{ finding.severity === 'ERROR' ? '需要修正' : '請確認' }}</strong>
            <span>{{ finding.message }}</span>
            <small v-if="finding.fieldCode">欄位：{{ fieldLabel(finding.fieldCode) }}</small>

            <button
              v-if="finding.severity === 'ERROR'"
              class="formal-validation-panel__fix"
              type="button"
              :data-testid="`fix-formal-finding-${finding.code}`"
              @click="emit('fix', finding)"
            >
              <span>前往修正</span>
              <ArrowRight :size="13" weight="bold" aria-hidden="true" />
            </button>

            <label v-if="finding.severity === 'WARNING'" class="formal-validation-panel__acknowledgement">
              <input
                type="checkbox"
                :data-testid="`formal-warning-${finding.code}`"
                :checked="isAcknowledged(finding.code)"
                @change="emit('acknowledge', finding.code, ($event.target as HTMLInputElement).checked)"
              />
              <span>我已確認此警示，允許產生正式 PDF</span>
            </label>
          </div>
        </li>
      </ul>
      <p v-else class="formal-validation-panel__empty">正式檢核沒有回傳其他訊息。</p>

      <p
        v-if="props.validation.canGenerateFormalReport && props.formalWarningCodes.length && !props.warningsAcknowledged"
        class="formal-validation-panel__blocker"
      >
        請逐項確認所有警示後，才能產生正式 PDF；系統不會代為確認。
      </p>
    </div>
    <p v-else class="formal-validation-panel__empty">正式 PDF 產出前，必須先完成正式檢核。</p>

    <div class="formal-validation-panel__actions">
      <button
        type="button"
        data-testid="run-formal-validation"
        :disabled="props.formalValidating || props.formalPdfGenerating || props.submitting || !props.reportPackageReady"
        @click="emit('runValidation')"
      >
        <WarningCircle v-if="!props.formalValidating" :size="16" weight="bold" aria-hidden="true" />
        <span>{{ props.formalValidating ? '正式檢核中…' : '執行正式檢核' }}</span>
      </button>
      <button
        v-if="props.validation"
        class="is-primary"
        type="button"
        data-testid="generate-formal-pdf"
        :disabled="props.formalPdfGenerating || props.formalValidating || props.submitting || !props.validation.canGenerateFormalReport || !props.warningsAcknowledged || props.authoritativeF02Status !== 'CHECKED'"
        @click="emit('generatePdf')"
      >
        <FilePdf v-if="!props.formalPdfGenerating" :size="16" weight="bold" aria-hidden="true" />
        <span>{{ props.formalPdfGenerating ? '正式 PDF 產生中…' : '產生完整送審 PDF' }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.formal-validation-panel { display: grid; gap: 16px; padding: 22px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #fff; }
.formal-validation-panel__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.formal-validation-panel__heading p { margin: 0 0 6px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.formal-validation-panel__heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; font-weight: 600; letter-spacing: -.04em; }
.formal-validation-panel__status { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 10px; border: 1px solid var(--app-line); border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f8fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.formal-validation-panel__status[data-validation-state="ready"] { border-color: #cfe0d6; color: var(--app-green); background: #f5faf7; }
.formal-validation-panel__status[data-validation-state="blocked"] { border-color: #edc8c0; color: #a44334; background: #fff5f3; }
.formal-validation-panel__counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.formal-validation-panel__counts span { padding: 8px 11px; border-radius: 8px; color: var(--app-ink-soft); background: #f5f7fb; font-size: 12px; font-weight: 800; }
.formal-validation-panel__counts [data-kind="passed"] { color: var(--app-green); }
.formal-validation-panel__counts [data-kind="warning"] { color: #8a6515; }
.formal-validation-panel__counts [data-kind="error"] { color: #a44334; }
.formal-validation-panel__findings { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.formal-validation-panel__findings li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 10px; padding: 12px 14px; border: 1px solid #ead9b2; border-left: 4px solid #d6a63e; border-radius: 8px; background: #fffaf0; }
.formal-validation-panel__findings li[data-severity="ERROR"] { border-color: #edc8c0; border-left-color: #c85b43; background: #fff3f0; }
.formal-validation-panel__finding-icon { padding-top: 1px; color: #9a741f; }
.formal-validation-panel__findings li[data-severity="ERROR"] .formal-validation-panel__finding-icon { color: #b84d3b; }
.formal-validation-panel__finding-copy { display: grid; gap: 4px; min-width: 0; color: var(--app-ink-soft); font-size: 13px; }
.formal-validation-panel__finding-copy strong { color: var(--app-ink); font-size: 12px; }
.formal-validation-panel__finding-copy small { color: var(--app-muted); font-size: 11px; }
.formal-validation-panel__fix { display: inline-flex; min-height: 34px; width: fit-content; align-items: center; gap: 5px; margin-top: 5px; padding: 6px 10px; border: 1px solid rgba(200,91,67,.26); border-radius: 8px; color: var(--app-accent-deep); background: #fff; cursor: pointer; font-size: 11px; font-weight: 900; }
.formal-validation-panel__acknowledgement { display: flex; align-items: flex-start; gap: 8px; margin-top: 6px; color: var(--app-ink); font-size: 12px; font-weight: 700; }
.formal-validation-panel__acknowledgement input { margin-top: 2px; accent-color: var(--app-accent); }
.formal-validation-panel__empty { margin: 0; color: var(--app-muted); font-size: 13px; }
.formal-validation-panel__blocker { margin: 14px 0 0; color: #a44334; font-size: 13px; font-weight: 700; }
.formal-validation-panel__actions { display: flex; flex-wrap: wrap; gap: 10px; }
.formal-validation-panel__actions button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 7px; padding: 10px 18px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 13px; font-weight: 800; }
.formal-validation-panel__actions button.is-primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.formal-validation-panel__actions button:disabled { cursor: not-allowed; opacity: .55; }

@media (max-width: 760px) {
  .formal-validation-panel { padding: 16px; }
  .formal-validation-panel__heading { flex-direction: column; }
  .formal-validation-panel__actions { width: 100%; }
  .formal-validation-panel__actions button { width: 100%; }
}
</style>