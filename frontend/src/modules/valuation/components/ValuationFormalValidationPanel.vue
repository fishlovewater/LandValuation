<script setup lang="ts">
import {
  PhArrowRight as ArrowRight,
  PhCheckCircle as CheckCircle,
  PhFilePdf as FilePdf,
  PhInfo as Info,
  PhShieldCheck as ShieldCheck,
  PhWarningCircle as WarningCircle,
  PhXCircle as XCircle,
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
      <div class="formal-validation-panel__title">
        <span class="formal-validation-panel__title-icon" aria-hidden="true">
          <ShieldCheck :size="22" weight="duotone" />
        </span>
        <div>
          <p>送審文件檢核</p>
          <h2 id="formal-validation-title">確認送審文件是否完整</h2>
          <span>檢查送審文件的必要條件、阻擋錯誤與需人工確認的警示，通過後即可產生正式送審 PDF。</span>
        </div>
      </div>
      <span
        v-if="props.validation"
        class="formal-validation-panel__status"
        :data-validation-state="props.validation.canGenerateFormalReport ? 'ready' : 'blocked'"
      >
        {{ props.validation.canGenerateFormalReport ? '送審文件檢核已通過' : '仍有待修正項目' }}
      </span>
      <span v-else class="formal-validation-panel__status" data-validation-state="pending">尚未執行</span>
    </div>

    <div v-if="props.validation" data-testid="formal-validation-result">
      <div class="formal-validation-panel__counts">
        <span data-kind="passed">
          <CheckCircle :size="15" weight="fill" aria-hidden="true" />
          <strong>通過 {{ props.validation.passedCount }}</strong>
          <small>檢核項目</small>
        </span>
        <span data-kind="warning">
          <WarningCircle :size="15" weight="fill" aria-hidden="true" />
          <strong>警示 {{ props.validation.warningCount }}</strong>
          <small>需人工確認</small>
        </span>
        <span data-kind="error">
          <XCircle :size="15" weight="fill" aria-hidden="true" />
          <strong>錯誤 {{ props.validation.failedCount }}</strong>
          <small>阻擋項目</small>
        </span>
      </div>

      <div class="formal-validation-panel__gate-summary">
        <div :data-state="props.validation.failedCount ? 'blocked' : 'ready'">
          <CheckCircle v-if="!props.validation.failedCount" :size="16" weight="fill" aria-hidden="true" />
          <XCircle v-else :size="16" weight="fill" aria-hidden="true" />
          <span>{{ props.validation.failedCount ? '仍有阻擋錯誤' : '無阻擋錯誤' }}</span>
        </div>
        <div :data-state="props.formalWarningCodes.length && !props.warningsAcknowledged ? 'attention' : 'ready'">
          <WarningCircle v-if="props.formalWarningCodes.length && !props.warningsAcknowledged" :size="16" weight="fill" aria-hidden="true" />
          <CheckCircle v-else :size="16" weight="fill" aria-hidden="true" />
          <span>
            {{ props.formalWarningCodes.length
              ? `警示確認 ${props.acknowledgedWarningCodes.length} / ${props.formalWarningCodes.length}`
              : '無需額外警示確認' }}
          </span>
        </div>
        <div :data-state="props.authoritativeF02Status === 'CHECKED' ? 'ready' : 'pending'">
          <CheckCircle v-if="props.authoritativeF02Status === 'CHECKED'" :size="16" weight="fill" aria-hidden="true" />
          <Info v-else :size="16" weight="duotone" aria-hidden="true" />
          <span>{{ props.authoritativeF02Status === 'CHECKED' ? 'F02 已完成正式確認' : '等待 F02 正式確認' }}</span>
        </div>
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
      <p v-else class="formal-validation-panel__empty">送審文件檢核沒有其他需要處理的項目。</p>

      <p
        v-if="props.validation.canGenerateFormalReport && props.formalWarningCodes.length && !props.warningsAcknowledged"
        class="formal-validation-panel__blocker"
      >
        <WarningCircle :size="15" weight="fill" aria-hidden="true" />
        <span>請逐項確認所有警示後，才能產生正式 PDF；系統不會代為確認。</span>
      </p>
    </div>
    <div v-else class="formal-validation-panel__empty">
      <Info :size="18" weight="duotone" aria-hidden="true" />
      <span>正式送審 PDF 產出前，必須先完成送審文件檢核。</span>
    </div>

    <div v-if="!props.reportPackageReady" class="formal-validation-panel__prerequisite">
      <WarningCircle :size="16" weight="duotone" aria-hidden="true" />
      <span>請先完成查估書內容確認與正式計算，才能執行送審文件檢核。</span>
    </div>

    <div class="formal-validation-panel__actions">
      <button
        type="button"
        data-testid="run-formal-validation"
        :disabled="props.formalValidating || props.formalPdfGenerating || props.submitting || !props.reportPackageReady"
        @click="emit('runValidation')"
      >
        <ShieldCheck v-if="!props.formalValidating" :size="16" weight="bold" aria-hidden="true" />
        <span>{{ props.formalValidating ? '送審文件檢核中…' : '執行送審文件檢核' }}</span>
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
        <span>{{ props.formalPdfGenerating ? '正式 PDF 產生中…' : '產生正式送審 PDF' }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.formal-validation-panel { display: grid; gap: 16px; padding: 22px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #fff; }
.formal-validation-panel__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.formal-validation-panel__title { display: flex; align-items: flex-start; gap: 11px; min-width: 0; }
.formal-validation-panel__title-icon { display: grid; width: 40px; height: 40px; flex: 0 0 auto; place-items: center; border-radius: 10px; color: var(--app-accent-deep); background: #edf4fb; }
.formal-validation-panel__heading p { margin: 0 0 6px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.formal-validation-panel__heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; font-weight: 600; letter-spacing: -.04em; }
.formal-validation-panel__title > div > span { display: block; margin-top: 5px; color: var(--app-muted); font-size: 11px; line-height: 1.5; }
.formal-validation-panel__status { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 10px; border: 1px solid var(--app-line); border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f8fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.formal-validation-panel__status[data-validation-state="ready"] { border-color: #cfe0d6; color: var(--app-green); background: #f5faf7; }
.formal-validation-panel__status[data-validation-state="blocked"] { border-color: #edc8c0; color: #a44334; background: #fff5f3; }
.formal-validation-panel__counts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
.formal-validation-panel__counts span { display: grid; grid-template-columns: auto minmax(0,1fr); align-items: center; gap: 2px 7px; padding: 10px 11px; border-radius: 8px; color: var(--app-ink-soft); background: #f5f7fb; font-size: 12px; font-weight: 800; }
.formal-validation-panel__counts span > svg { grid-row: 1 / 3; }
.formal-validation-panel__counts strong { font-size: 12px; }
.formal-validation-panel__counts small { color: currentColor; font-size: 9px; font-weight: 700; opacity: .78; }
.formal-validation-panel__counts [data-kind="passed"] { color: var(--app-green); }
.formal-validation-panel__counts [data-kind="warning"] { color: #8a6515; }
.formal-validation-panel__counts [data-kind="error"] { color: #a44334; }
.formal-validation-panel__gate-summary { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; margin-bottom: 14px; }
.formal-validation-panel__gate-summary > div { display: flex; min-height: 40px; align-items: center; gap: 7px; padding: 8px 10px; border: 1px solid #e1e7ee; border-radius: 8px; color: var(--app-ink-soft); background: #fafbfd; font-size: 10px; font-weight: 800; }
.formal-validation-panel__gate-summary > div[data-state="ready"] { border-color: #cfe4da; color: #2f7456; background: #f3f9f6; }
.formal-validation-panel__gate-summary > div[data-state="attention"] { border-color: #ead9b2; color: #8a6515; background: #fffaf0; }
.formal-validation-panel__gate-summary > div[data-state="blocked"] { border-color: #edc8c0; color: #a44334; background: #fff5f3; }
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
.formal-validation-panel__empty { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 11px 12px; border: 1px solid #e1e7ee; border-radius: 8px; color: var(--app-muted); background: #fafbfd; font-size: 11px; line-height: 1.55; }
.formal-validation-panel__empty > svg { flex: 0 0 auto; margin-top: 1px; color: var(--app-accent-deep); }
.formal-validation-panel__blocker,
.formal-validation-panel__prerequisite { display: flex; align-items: flex-start; gap: 7px; padding: 10px 12px; border-radius: 8px; font-size: 11px; font-weight: 700; line-height: 1.55; }
.formal-validation-panel__blocker { margin: 14px 0 0; border: 1px solid #edc8c0; color: #a44334; background: #fff5f3; }
.formal-validation-panel__prerequisite { border: 1px solid #ead9b2; color: #805e18; background: #fffaf0; }
.formal-validation-panel__blocker > svg,
.formal-validation-panel__prerequisite > svg { flex: 0 0 auto; margin-top: 1px; }
.formal-validation-panel__actions { display: flex; flex-wrap: wrap; gap: 10px; }
.formal-validation-panel__actions button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 7px; padding: 10px 18px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 13px; font-weight: 800; }
.formal-validation-panel__actions button.is-primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.formal-validation-panel__actions button:disabled { cursor: not-allowed; opacity: .55; }

@media (max-width: 760px) {
  .formal-validation-panel { padding: 16px; }
  .formal-validation-panel__heading { flex-direction: column; }
  .formal-validation-panel__counts,
  .formal-validation-panel__gate-summary { grid-template-columns: 1fr; }
  .formal-validation-panel__actions { width: 100%; }
  .formal-validation-panel__actions button { width: 100%; }
}
</style>