<script setup lang="ts">
import type {
  CalculationModel,
  ReportArtifactModel,
  ValidationFindingModel,
  ValidationRunModel,
} from '../valuation.types'

const props = defineProps<{
  validation: ValidationRunModel | null
  calculation: CalculationModel | null
  report: ReportArtifactModel | null
  hasF03: boolean
  preCalculationIssueCount: number
  dirty: boolean
  running: boolean
  saving: boolean
  canRunValuation: boolean
  canProceedToSubmit: boolean
  findingLocationLabel: (finding: ValidationFindingModel) => string
  findingCorrectionHint: (finding: ValidationFindingModel) => string
}>()

const emit = defineEmits<{
  run: []
  fixFinding: [finding: ValidationFindingModel]
  goSubmit: []
}>()
</script>

<template>
  <section class="valuation-surface calculation-launch" data-testid="calculation-launch" aria-labelledby="calculation-launch-title">
    <div class="calculation-launch__copy">
      <div>
        <p class="valuation-eyebrow">正式計算</p>
        <h2 id="calculation-launch-title">計算與檢核</h2>
        <p>系統會使用已確認的比準地地價估計表資料執行公式計算，再依檢核規則檢查缺漏與一致性；若有問題會直接指出修正位置。</p>
      </div>
      <div class="calculation-launch__readiness">
        <span :data-state="hasF03 ? 'ready' : 'blocked'">{{ hasF03 ? '比準地地價估計表已建立' : '尚未建立比準地地價估計表' }}</span>
        <span v-if="preCalculationIssueCount" data-state="blocked">前置資料尚有 {{ preCalculationIssueCount }} 項</span>
        <span :data-state="dirty ? 'attention' : 'ready'">{{ dirty ? '有尚未儲存的修改' : '資料已同步' }}</span>
      </div>
    </div>
    <button
      class="solid-button solid-button--primary calculation-launch__button"
      type="button"
      data-testid="run-valuation"
      :disabled="running || saving || !canRunValuation"
      :title="!canRunValuation ? '請先完成待處理前置資料' : dirty ? '會先儲存尚未儲存的比準地地價估計表修改，再執行計算與檢核' : '執行正式計算與檢核'"
      @click="emit('run')"
    >
      {{ running ? '計算與檢核中…' : dirty ? '儲存修改並執行計算與檢核' : '執行計算與檢核' }}
    </button>
  </section>

  <section v-if="validation" class="valuation-surface validation-results" data-testid="validation-results" aria-labelledby="validation-title">
    <div class="surface-heading">
      <div>
        <p class="valuation-eyebrow">檢核結果</p>
        <h2 id="validation-title">計算與資料檢核</h2>
      </div>
      <span class="value-kind" :data-validation-state="validation.canGenerateReport ? 'ready' : 'blocked'">{{ validation.canGenerateReport ? '可產生比準地地價估計表單表' : '仍有待修正項目' }}</span>
    </div>
    <div class="validation-counts">
      <span>通過 {{ validation.passedCount }}</span>
      <span>警示 {{ validation.warningCount }}</span>
      <span>錯誤 {{ validation.failedCount }}</span>
    </div>
    <ul v-if="validation.findings.length" class="finding-list">
      <li v-for="finding in validation.findings" :key="finding.findingId" :data-severity="finding.severity">
        <strong>{{ finding.severity === 'ERROR' ? '需要修正' : '請確認' }}｜{{ findingLocationLabel(finding) }}</strong>
        <span>{{ finding.message }}</span>
        <small>實際值：{{ finding.actualValue ?? '—' }}</small>
        <small>預期值：{{ finding.expectedValue ?? '—' }}</small>
        <small><b>建議修正：</b>{{ findingCorrectionHint(finding) }}</small>
        <button class="finding-action" type="button" :data-testid="`fix-finding-${finding.findingId}`" @click="emit('fixFinding', finding)">前往修正</button>
      </li>
    </ul>
    <p v-else class="empty-copy">目前沒有其他需要處理的檢核項目。</p>
    <div v-if="validation.correctionHints.length" class="correction-hints">
      <strong>建議修正方式</strong>
      <ul><li v-for="hint in validation.correctionHints" :key="hint">{{ hint }}</li></ul>
    </div>

    <div v-if="calculation" class="calculation-result" data-testid="calculation-result" data-source-kind="calculated">
      <span>正式計算結果</span>
      <strong>{{ calculation.result }} {{ calculation.currencyCode }}</strong>
      <small>公式版本：{{ calculation.formulaVersion }}</small>
    </div>
    <div v-if="report" class="report-result" data-testid="report-result">
      <span>比準地地價估計表單表輸出</span>
      <strong>{{ report.filename }}</strong>
      <small>第 {{ report.versionNo }} 版｜檔案大小 {{ Math.max(1, Math.round(report.fileSizeBytes / 1024)) }} KB</small>
    </div>
    <button class="solid-button solid-button--primary" type="button" data-testid="go-to-submit" :disabled="!canProceedToSubmit" :title="canProceedToSubmit ? '前往輸出預覽與送審' : '必須先修正阻擋項目並通過檢核'" @click="emit('goSubmit')">{{ canProceedToSubmit ? '前往輸出預覽與送審' : '請先完成阻擋項目' }}</button>
  </section>
</template>

<style scoped>
.valuation-surface{padding:22px;border:1px solid var(--app-line);border-radius:var(--app-radius-md);background:var(--app-paper-strong);box-shadow:var(--app-shadow-soft)}.surface-heading,.calculation-result,.report-result{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.surface-heading{margin-bottom:18px}.surface-heading h2{margin:0;color:var(--app-ink);font-family:var(--app-font-display);font-size:24px;font-weight:600;letter-spacing:-.04em}.valuation-eyebrow{margin:0 0 6px;color:var(--app-accent-deep);font-size:11px;font-weight:800;letter-spacing:.12em}.value-kind{display:inline-flex;min-height:30px;align-items:center;padding:5px 10px;border:1px solid var(--app-line);border-radius:var(--app-radius-pill);color:var(--app-ink-soft);background:#f7f8fb;font-size:11px;font-weight:800;white-space:nowrap}.calculation-launch{display:grid;gap:14px;border-color:rgba(46,89,132,.24);background:#f8fbff}.calculation-launch__copy{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.calculation-launch__copy h2{margin:0;color:var(--app-ink);font-family:var(--app-font-display);font-size:24px}.calculation-launch__copy p:last-child{max-width:720px;margin:7px 0 0;color:var(--app-ink-soft);font-size:12px;line-height:1.7}.calculation-launch__readiness{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.calculation-launch__readiness span{padding:6px 9px;border-radius:999px;font-size:10px;font-weight:850}.calculation-launch__readiness [data-state="ready"]{color:#2f745b;background:#edf8f3}.calculation-launch__readiness [data-state="attention"]{color:#925421;background:#fff0df}.calculation-launch__readiness [data-state="blocked"]{color:#9a4435;background:#fff0ed}.calculation-launch__button{justify-self:start;min-width:200px}.solid-button{min-height:44px;padding:10px 16px;border:1px solid var(--app-line);border-radius:9px;color:var(--app-ink-soft);background:var(--app-paper-strong);cursor:pointer;font-size:13px;font-weight:800}.solid-button--primary{border-color:var(--app-accent);color:#fff;background:var(--app-accent)}.solid-button:disabled{cursor:not-allowed;opacity:.55}.validation-counts{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}.validation-counts span{padding:8px 11px;border-radius:8px;color:var(--app-ink-soft);background:#f5f7fb;font-size:12px;font-weight:800}.finding-list{display:grid;gap:8px;margin:0;padding:0;list-style:none}.finding-list li{display:grid;gap:4px;padding:12px 14px;border-left:4px solid #d6a63e;background:#fffaf0;color:var(--app-ink-soft);font-size:13px}.finding-list li[data-severity="ERROR"]{border-left-color:#c85b43;background:#fff3f0}.finding-list strong{color:var(--app-ink);font-size:12px}.finding-list b{color:var(--app-ink)}.finding-action{justify-self:start;min-height:36px;margin-top:5px;padding:6px 11px;border:1px solid rgba(200,91,67,.26);border-radius:8px;color:var(--app-accent-deep);background:#fff;cursor:pointer;font-size:11px;font-weight:900}.correction-hints{display:grid;gap:7px;margin-top:14px;padding:12px 14px;border:1px solid rgba(214,166,62,.26);border-radius:var(--app-radius-sm);background:#fffaf0}.correction-hints>strong{color:var(--app-ink);font-size:12px}.correction-hints ul{display:grid;gap:4px;margin:0;padding-left:20px;color:var(--app-ink-soft);font-size:12px}.empty-copy{margin:0;color:var(--app-muted);font-size:13px}.calculation-result,.report-result{align-items:center;margin-top:14px;padding:14px;border:1px solid var(--app-line);border-radius:var(--app-radius-sm);background:#fbfcfe}.calculation-result span,.report-result span{color:var(--app-muted);font-size:11px;font-weight:800}.calculation-result strong,.report-result strong{margin-left:auto;color:var(--app-ink);font-size:14px}.calculation-result small,.report-result small{color:var(--app-muted);font-size:11px}.validation-results>.solid-button{margin-top:18px}@media(max-width:760px){.valuation-surface{padding:16px}.surface-heading,.calculation-result,.report-result,.calculation-launch__copy{align-items:stretch;flex-direction:column}.solid-button{width:100%}.calculation-result strong,.report-result strong{margin-left:0}}
</style>
