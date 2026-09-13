<script setup lang="ts">
import {
  PhArrowRight as ArrowRight,
  PhCalculator as Calculator,
  PhCheckCircle as CheckCircle,
  PhDatabase as Database,
  PhDownloadSimple as DownloadSimple,
  PhFileText as FileText,
  PhShieldCheck as ShieldCheck,
  PhWarningCircle as WarningCircle,
  PhWrench as Wrench,
  PhXCircle as XCircle,
} from '@phosphor-icons/vue'
import type {
  CalculationModel,
  FormalValidationModel,
  ReportArtifactModel,
  TemplateExportModel,
  ValidationFindingModel,
  ValidationRunModel,
} from '../valuation.types'

const props = defineProps<{
  validation: ValidationRunModel | null
  formalValidation: FormalValidationModel | null
  templateExports: TemplateExportModel[]
  downloadingTemplateDocumentId: string | null
  calculation: CalculationModel | null
  report: ReportArtifactModel | null
  hasF03: boolean
  preCalculationIssueCount: number
  dirty: boolean
  running: boolean
  saving: boolean
  caseEditable: boolean
  canRunValuation: boolean
  canProceedToSubmit: boolean
  findingLocationLabel: (finding: ValidationFindingModel) => string
  findingCorrectionHint: (finding: ValidationFindingModel) => string
}>()

const emit = defineEmits<{
  run: []
  'fix-finding': [finding: ValidationFindingModel]
  'go-submit': []
  'download-template': [documentId: string, filename: string]
}>()

function isDownloadingTemplate(documentId: string): boolean {
  return props.downloadingTemplateDocumentId === documentId
}
</script>

<template>
  <section class="calculation-stage" data-testid="calculation-launch" aria-labelledby="calculation-launch-title">
    <div class="calculation-stage__heading">
      <div class="calculation-stage__title">
        <span class="calculation-stage__icon" aria-hidden="true">
          <Calculator :size="22" weight="duotone" />
        </span>
        <div>
          <p>正式計算</p>
          <h2 id="calculation-launch-title">計算與檢核</h2>
        </div>
      </div>
      <span class="calculation-stage__engine">
        <ShieldCheck :size="16" weight="fill" aria-hidden="true" />
        系統規則引擎
      </span>
    </div>

    <p class="calculation-stage__description">
      系統會使用已確認的比準地地價估計表資料執行公式計算，再依檢核規則檢查缺漏與一致性；若有問題會直接指出修正位置。AI 僅協助說明，不參與正式數值計算。
    </p>

    <div class="calculation-stage__readiness" aria-label="計算前置條件">
      <article :data-state="hasF03 ? 'ready' : 'blocked'">
        <Database :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>比準地地價估計表</span>
          <strong>{{ hasF03 ? '已建立' : '尚未建立' }}</strong>
        </div>
      </article>
      <article :data-state="preCalculationIssueCount ? 'blocked' : 'ready'">
        <WarningCircle v-if="preCalculationIssueCount" :size="18" weight="fill" aria-hidden="true" />
        <CheckCircle v-else :size="18" weight="fill" aria-hidden="true" />
        <div>
          <span>前置資料</span>
          <strong>{{ preCalculationIssueCount ? `尚有 ${preCalculationIssueCount} 項待處理` : '已完成必要資料' }}</strong>
        </div>
      </article>
      <article :data-state="dirty ? 'attention' : 'ready'">
        <WarningCircle v-if="dirty" :size="18" weight="fill" aria-hidden="true" />
        <CheckCircle v-else :size="18" weight="fill" aria-hidden="true" />
        <div>
          <span>資料同步</span>
          <strong>{{ dirty ? '有尚未儲存的修改' : '資料已同步' }}</strong>
        </div>
      </article>
    </div>

    <div class="calculation-stage__action-row">
      <p v-if="!caseEditable">
        <WarningCircle :size="16" weight="fill" aria-hidden="true" />
        此案件已送審並鎖定，不能再修改或重複執行正式計算；如需重算，請先由審查系統退回修正。
      </p>
      <p v-else-if="!canRunValuation">
        <WarningCircle :size="16" weight="fill" aria-hidden="true" />
        請先完成待處理前置資料，再執行正式計算。
      </p>
      <p v-else>
        <CheckCircle :size="16" weight="fill" aria-hidden="true" />
        前置條件已符合，可以執行正式計算與檢核。
      </p>
      <button
        class="calculation-stage__run"
        type="button"
        data-testid="run-valuation"
        :disabled="running || saving || !caseEditable || !canRunValuation"
        :title="!caseEditable ? '案件已送審鎖定' : !canRunValuation ? '請先完成待處理前置資料' : dirty ? '會先儲存尚未儲存的比準地地價估計表修改，再執行計算與檢核' : '執行正式計算與檢核'"
        @click="emit('run')"
      >
        <Calculator v-if="!running" :size="17" weight="bold" aria-hidden="true" />
        <span>{{ running ? '計算與檢核中…' : dirty ? '儲存修改並執行計算與檢核' : '執行計算與檢核' }}</span>
      </button>
    </div>
  </section>

  <section
    v-if="formalValidation"
    class="validation-results"
    data-testid="formal-calculation-results"
    aria-labelledby="formal-calculation-results-title"
  >
    <div class="validation-results__heading">
      <div class="validation-results__title">
        <span class="validation-results__icon" aria-hidden="true">
          <ShieldCheck :size="21" weight="duotone" />
        </span>
        <div>
          <p>正式檢核結果</p>
          <h2 id="formal-calculation-results-title">多宗地計算與檢核</h2>
        </div>
      </div>
      <span
        class="validation-results__state"
        :data-validation-state="formalValidation.canGenerateFormalReport ? 'ready' : 'blocked'"
      >
        <CheckCircle v-if="formalValidation.canGenerateFormalReport" :size="16" weight="fill" aria-hidden="true" />
        <WarningCircle v-else :size="16" weight="fill" aria-hidden="true" />
        {{ formalValidation.canGenerateFormalReport ? '已通過正式檢核' : '仍有待修正項目' }}
      </span>
    </div>

    <div class="validation-results__counts" aria-label="正式檢核統計">
      <span data-state="passed"><CheckCircle :size="16" weight="fill" aria-hidden="true" />通過 {{ formalValidation.passedCount }}</span>
      <span data-state="warning"><WarningCircle :size="16" weight="fill" aria-hidden="true" />警示 {{ formalValidation.warningCount }}</span>
      <span data-state="error"><XCircle :size="16" weight="fill" aria-hidden="true" />錯誤 {{ formalValidation.failedCount }}</span>
    </div>

    <ul v-if="formalValidation.findings.length" class="validation-results__findings">
      <li
        v-for="finding in formalValidation.findings"
        :key="finding.code"
        :data-severity="finding.severity"
      >
        <div class="validation-results__finding-title">
          <XCircle v-if="finding.severity === 'ERROR'" :size="17" weight="fill" aria-hidden="true" />
          <WarningCircle v-else :size="17" weight="fill" aria-hidden="true" />
          <strong>{{ finding.severity === 'ERROR' ? '需要修正' : '請確認' }}</strong>
        </div>
        <span>{{ finding.message }}</span>
      </li>
    </ul>
    <p v-else class="validation-results__empty">
      <CheckCircle :size="17" weight="fill" aria-hidden="true" />
      目前沒有其他需要處理的檢核項目。
    </p>

    <div v-if="templateExports.length" class="validation-results__outputs">
      <article v-for="templateExport in templateExports" :key="templateExport.documentId" class="validation-results__output">
        <FileText :size="20" weight="duotone" aria-hidden="true" />
        <div>
          <span>{{ templateExport.title }}</span>
          <strong>{{ templateExport.filename }}</strong>
          <small>第 {{ templateExport.versionNo }} 版｜檔案大小 {{ Math.max(1, Math.round(templateExport.fileSizeBytes / 1024)) }} KB</small>
        </div>
        <button
          class="validation-results__download"
          type="button"
          :disabled="Boolean(downloadingTemplateDocumentId)"
          @click="emit('download-template', templateExport.documentId, templateExport.filename)"
        >
          <DownloadSimple v-if="!isDownloadingTemplate(templateExport.documentId)" :size="15" weight="bold" aria-hidden="true" />
          <span>{{ isDownloadingTemplate(templateExport.documentId) ? '下載中…' : '下載 Excel' }}</span>
        </button>
      </article>
    </div>

    <div class="validation-results__next">
      <p>{{ canProceedToSubmit ? '已產生 Excel 範本，可進入輸出與送審。' : '請先修正阻擋項目，再重新執行正式檢核。' }}</p>
      <button
        class="validation-results__submit"
        type="button"
        data-testid="go-to-submit"
        :disabled="!canProceedToSubmit"
        @click="emit('go-submit')"
      >
        <span>{{ canProceedToSubmit ? '前往輸出與送審' : '請先完成阻擋項目' }}</span>
        <ArrowRight v-if="canProceedToSubmit" :size="16" weight="bold" aria-hidden="true" />
      </button>
    </div>
  </section>

  <section
    v-if="validation"
    class="validation-results"
    data-testid="validation-results"
    aria-labelledby="validation-title"
  >
    <div class="validation-results__heading">
      <div class="validation-results__title">
        <span class="validation-results__icon" aria-hidden="true">
          <ShieldCheck :size="21" weight="duotone" />
        </span>
        <div>
          <p>檢核結果</p>
          <h2 id="validation-title">計算與資料檢核</h2>
        </div>
      </div>
      <span
        class="validation-results__state"
        :data-validation-state="validation.canGenerateReport ? 'ready' : 'blocked'"
      >
        <CheckCircle v-if="validation.canGenerateReport" :size="16" weight="fill" aria-hidden="true" />
        <WarningCircle v-else :size="16" weight="fill" aria-hidden="true" />
        {{ validation.canGenerateReport ? '可產生比準地地價估計表單表' : '仍有待修正項目' }}
      </span>
    </div>

    <div class="validation-results__counts" aria-label="檢核統計">
      <span data-state="passed"><CheckCircle :size="16" weight="fill" aria-hidden="true" />通過 {{ validation.passedCount }}</span>
      <span data-state="warning"><WarningCircle :size="16" weight="fill" aria-hidden="true" />警示 {{ validation.warningCount }}</span>
      <span data-state="error"><XCircle :size="16" weight="fill" aria-hidden="true" />錯誤 {{ validation.failedCount }}</span>
    </div>

    <ul v-if="validation.findings.length" class="validation-results__findings">
      <li
        v-for="finding in validation.findings"
        :key="finding.findingId"
        :data-severity="finding.severity"
      >
        <div class="validation-results__finding-title">
          <XCircle v-if="finding.severity === 'ERROR'" :size="17" weight="fill" aria-hidden="true" />
          <WarningCircle v-else :size="17" weight="fill" aria-hidden="true" />
          <strong>{{ finding.severity === 'ERROR' ? '需要修正' : '請確認' }}｜{{ findingLocationLabel(finding) }}</strong>
        </div>
        <span>{{ finding.message }}</span>
        <div class="validation-results__values">
          <small>實際值：{{ finding.actualValue ?? '—' }}</small>
          <small>預期值：{{ finding.expectedValue ?? '—' }}</small>
        </div>
        <small class="validation-results__hint"><b>建議修正：</b>{{ findingCorrectionHint(finding) }}</small>
        <button
          class="validation-results__fix"
          type="button"
          :data-testid="`fix-finding-${finding.findingId}`"
          @click="emit('fix-finding', finding)"
        >
          <Wrench :size="15" weight="bold" aria-hidden="true" />
          <span>前往修正</span>
        </button>
      </li>
    </ul>
    <p v-else class="validation-results__empty">
      <CheckCircle :size="17" weight="fill" aria-hidden="true" />
      目前沒有其他需要處理的檢核項目。
    </p>

    <div v-if="validation.correctionHints.length" class="validation-results__correction-hints">
      <strong><Wrench :size="16" weight="bold" aria-hidden="true" />建議修正方式</strong>
      <ul><li v-for="hint in validation.correctionHints" :key="hint">{{ hint }}</li></ul>
    </div>

    <div class="validation-results__outputs">
      <article v-if="calculation" class="validation-results__output" data-testid="calculation-result" data-source-kind="calculated">
        <Calculator :size="20" weight="duotone" aria-hidden="true" />
        <div>
          <span>正式計算結果</span>
          <strong>{{ calculation.result }} {{ calculation.currencyCode }}</strong>
          <small>公式版本：{{ calculation.formulaVersion }}</small>
        </div>
      </article>
      <article v-if="report" class="validation-results__output" data-testid="report-result">
        <FileText :size="20" weight="duotone" aria-hidden="true" />
        <div>
          <span>比準地地價估計表單表輸出</span>
          <strong>{{ report.filename }}</strong>
          <small>第 {{ report.versionNo }} 版｜檔案大小 {{ Math.max(1, Math.round(report.fileSizeBytes / 1024)) }} KB</small>
        </div>
      </article>
    </div>

    <div class="validation-results__next">
      <p>
        {{ canProceedToSubmit ? '檢核已達送審條件，可進入查估書確認。' : '必須先修正阻擋項目並重新執行檢核。' }}
      </p>
      <button
        class="validation-results__submit"
        type="button"
        data-testid="go-to-submit"
        :disabled="!canProceedToSubmit"
        :title="canProceedToSubmit ? '前往輸出預覽與送審' : '必須先修正阻擋項目並通過檢核'"
        @click="emit('go-submit')"
      >
        <span>{{ canProceedToSubmit ? '前往輸出預覽與送審' : '請先完成阻擋項目' }}</span>
        <ArrowRight v-if="canProceedToSubmit" :size="16" weight="bold" aria-hidden="true" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.calculation-stage,
.validation-results {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: #fff;
}
.calculation-stage { border-color: rgba(46, 89, 132, .22); }
.calculation-stage__heading,
.validation-results__heading,
.calculation-stage__title,
.validation-results__title,
.calculation-stage__action-row,
.validation-results__finding-title,
.validation-results__counts span,
.validation-results__empty,
.validation-results__correction-hints strong,
.validation-results__next,
.validation-results__output {
  display: flex;
  align-items: center;
}
.calculation-stage__heading,
.validation-results__heading,
.validation-results__next {
  justify-content: space-between;
  gap: 16px;
}
.calculation-stage__title,
.validation-results__title { gap: 11px; }
.calculation-stage__icon,
.validation-results__icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 9px;
  color: var(--app-accent-deep);
  background: #edf4fb;
}
.calculation-stage__title p,
.validation-results__title p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.calculation-stage__title h2,
.validation-results__title h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; font-weight: 650; letter-spacing: -.035em; }
.calculation-stage__engine,
.validation-results__state {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid rgba(46, 89, 132, .22);
  border-radius: var(--app-radius-pill);
  color: var(--app-accent-deep);
  background: #edf4fb;
  font-size: 11px;
  font-weight: 850;
  white-space: nowrap;
}
.calculation-stage__description { max-width: 830px; margin: 13px 0 16px; color: var(--app-ink-soft); font-size: 12px; line-height: 1.75; }
.calculation-stage__readiness { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.calculation-stage__readiness article { display: flex; min-width: 0; align-items: center; gap: 9px; padding: 12px 13px; border: 1px solid var(--app-line); border-radius: 9px; color: #2f7456; background: #fbfcfe; }
.calculation-stage__readiness article[data-state="blocked"] { border-color: rgba(193, 92, 65, .20); color: #a44334; background: #fff6f3; }
.calculation-stage__readiness article[data-state="attention"] { border-color: rgba(188, 133, 37, .22); color: #946d16; background: #fff9ec; }
.calculation-stage__readiness article > div { display: grid; min-width: 0; gap: 3px; }
.calculation-stage__readiness span { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.calculation-stage__readiness strong { color: currentColor; font-size: 12px; line-height: 1.4; }
.calculation-stage__action-row { justify-content: space-between; gap: 16px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--app-line); }
.calculation-stage__action-row p { display: inline-flex; align-items: center; gap: 6px; margin: 0; color: var(--app-ink-soft); font-size: 12px; }
.calculation-stage__run,
.validation-results__submit,
.validation-results__fix {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 850;
}
.calculation-stage__run,
.validation-results__submit { padding: 9px 15px; border: 1px solid var(--app-accent); color: #fff; background: var(--app-accent); }
.calculation-stage__run:disabled,
.validation-results__submit:disabled { cursor: not-allowed; opacity: .5; }

.validation-results__heading { align-items: flex-start; margin-bottom: 14px; }
.validation-results__state { border-color: rgba(57, 123, 92, .22); color: #2f7456; background: #edf8f2; }
.validation-results__state[data-validation-state="blocked"] { border-color: rgba(193, 92, 65, .22); color: #a44334; background: #fff3f0; }
.validation-results__counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.validation-results__counts span { gap: 6px; padding: 8px 11px; border-radius: 8px; font-size: 12px; font-weight: 800; }
.validation-results__counts [data-state="passed"] { color: #2f7456; background: #edf8f2; }
.validation-results__counts [data-state="warning"] { color: #946d16; background: #fff8e8; }
.validation-results__counts [data-state="error"] { color: #a44334; background: #fff3f0; }
.validation-results__findings { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.validation-results__findings li { display: grid; gap: 7px; padding: 13px 14px; border-left: 4px solid #d6a63e; border-radius: 0 8px 8px 0; color: var(--app-ink-soft); background: #fffaf0; font-size: 13px; }
.validation-results__findings li[data-severity="ERROR"] { border-left-color: #c85b43; background: #fff3f0; }
.validation-results__finding-title { gap: 6px; color: #946d16; }
.validation-results__findings li[data-severity="ERROR"] .validation-results__finding-title { color: #a44334; }
.validation-results__finding-title strong { color: currentColor; font-size: 12px; }
.validation-results__values { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--app-muted); }
.validation-results__hint b { color: var(--app-ink); }
.validation-results__fix { justify-self: start; min-height: 36px; padding: 6px 11px; border: 1px solid rgba(46, 89, 132, .24); color: var(--app-accent-deep); background: #fff; }
.validation-results__empty { gap: 7px; margin: 0; color: #2f7456; font-size: 13px; }
.validation-results__correction-hints { display: grid; gap: 7px; margin-top: 14px; padding: 12px 14px; border: 1px solid rgba(214, 166, 62, .26); border-radius: 9px; background: #fffaf0; }
.validation-results__correction-hints strong { gap: 6px; color: var(--app-ink); font-size: 12px; }
.validation-results__correction-hints ul { display: grid; gap: 4px; margin: 0; padding-left: 20px; color: var(--app-ink-soft); font-size: 12px; }
.validation-results__outputs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 15px; }
.validation-results__output { min-width: 0; gap: 10px; padding: 13px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-accent-deep); background: #fbfcfe; }
.validation-results__output > div { display: grid; min-width: 0; gap: 3px; }
.validation-results__output span { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.validation-results__output strong { color: var(--app-ink); font-size: 14px; overflow-wrap: anywhere; }
.validation-results__output small { color: var(--app-muted); font-size: 11px; }
.validation-results__download { justify-self: start; min-height: 34px; margin-top: 4px; padding: 6px 10px; border: 1px solid rgba(46, 89, 132, .24); border-radius: 8px; color: var(--app-accent-deep); background: #fff; cursor: pointer; font-size: 11px; font-weight: 850; }
.validation-results__download:disabled { cursor: not-allowed; opacity: .55; }
.validation-results__next { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--app-line); }
.validation-results__next p { margin: 0; color: var(--app-ink-soft); font-size: 12px; }

@media (max-width: 820px) {
  .calculation-stage__readiness { grid-template-columns: 1fr; }
  .validation-results__outputs { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .calculation-stage,
  .validation-results { padding: 16px; }
  .calculation-stage__heading,
  .validation-results__heading,
  .calculation-stage__action-row,
  .validation-results__next { align-items: stretch; flex-direction: column; }
  .calculation-stage__run,
  .validation-results__submit { width: 100%; }
}
</style>
