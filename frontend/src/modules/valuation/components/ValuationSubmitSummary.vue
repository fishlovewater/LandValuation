<script setup lang="ts">
import {
  PhBriefcase as Briefcase,
  PhCheckCircle as CheckCircle,
  PhFileText as FileText,
  PhShieldCheck as ShieldCheck,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import type {
  DocumentArtifactModel,
  FormalReportModel,
  ValidationRunModel,
  ValuationCaseModel,
  ValuationFormModel,
} from '../valuation.types'

defineProps<{
  caseModel: ValuationCaseModel
  authoritativeF02: ValuationFormModel | null
  formalReport: FormalReportModel | null
  completeReport: DocumentArtifactModel | null
  validation: ValidationRunModel | null
  readinessMessage: string
  displayedCaseStatus: string
  statusValue: string
}>()
</script>

<template>
  <section class="submit-summary" data-testid="submit-summary" aria-labelledby="submit-summary-title">
    <div class="submit-summary__heading">
      <div class="submit-summary__title">
        <span class="submit-summary__icon" aria-hidden="true">
          <Briefcase :size="21" weight="duotone" />
        </span>
        <div>
          <p>案件與輸出</p>
          <h2 id="submit-summary-title">{{ caseModel.caseNo }}｜{{ caseModel.name }}</h2>
        </div>
      </div>
      <span class="submit-summary__status" :data-status="statusValue">案件狀態：{{ displayedCaseStatus }}</span>
    </div>

    <div class="submit-summary__grid">
      <article>
        <Briefcase :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>案件資料</span>
          <strong>已載入目前案件</strong>
        </div>
      </article>
      <article :data-state="authoritativeF02 ? 'ready' : 'pending'">
        <CheckCircle v-if="authoritativeF02" :size="18" weight="duotone" aria-hidden="true" />
        <WarningCircle v-else :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>比較法調查估價表（F02）</span>
          <strong>{{ authoritativeF02 ? `第 ${authoritativeF02.versionNo} 版正式資料` : '尚未取得正式版本' }}</strong>
        </div>
      </article>
      <article :data-state="formalReport || completeReport ? 'ready' : 'pending'">
        <FileText :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>完整送審 PDF</span>
          <strong>{{ formalReport?.filename || completeReport?.filename || '尚未產生完整送審 PDF' }}</strong>
        </div>
      </article>
      <article :data-state="validation ? validation.canGenerateReport ? 'ready' : 'blocked' : 'pending'">
        <ShieldCheck v-if="validation?.canGenerateReport" :size="18" weight="duotone" aria-hidden="true" />
        <WarningCircle v-else :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>檢核狀態</span>
          <strong>
            {{ !validation ? '尚未執行' : validation.canGenerateReport ? '已通過一般檢核' : `仍有 ${validation.failedCount} 項錯誤待修正` }}
          </strong>
        </div>
      </article>
      <article class="submit-summary__readiness">
        <CheckCircle :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>送審準備</span>
          <strong>{{ readinessMessage }}</strong>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.submit-summary {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: #fff;
}

.submit-summary__heading,
.submit-summary__title,
.submit-summary__grid article {
  display: flex;
  align-items: center;
}

.submit-summary__heading {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.submit-summary__title { gap: 11px; }
.submit-summary__icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 9px;
  color: var(--app-accent-deep);
  background: #edf4fb;
}
.submit-summary__title p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.submit-summary__title h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; font-weight: 650; letter-spacing: -.035em; }
.submit-summary__status {
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

.submit-summary__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.submit-summary__grid article {
  min-width: 0;
  gap: 10px;
  padding: 13px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  color: var(--app-accent-deep);
  background: #fbfcfe;
}
.submit-summary__grid article[data-state="ready"] { border-color: #cfe4da; color: #2f7456; background: #f5faf7; }
.submit-summary__grid article[data-state="pending"] { border-color: #e4dfcf; color: #8a6515; background: #fffaf0; }
.submit-summary__grid article[data-state="blocked"] { border-color: #edc8c0; color: #a44334; background: #fff5f3; }
.submit-summary__grid article > div { min-width: 0; display: grid; gap: 4px; }
.submit-summary__grid span { color: var(--app-muted); font-size: 11px; font-weight: 800; }
.submit-summary__grid strong { color: var(--app-ink); font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }
.submit-summary__readiness { grid-column: span 2; }

@media (max-width: 980px) {
  .submit-summary__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .submit-summary__readiness { grid-column: span 2; }
}

@media (max-width: 640px) {
  .submit-summary { padding: 16px; }
  .submit-summary__heading { align-items: flex-start; flex-direction: column; }
  .submit-summary__grid { grid-template-columns: 1fr; }
  .submit-summary__readiness { grid-column: auto; }
}
</style>
