<script setup lang="ts">
import {
  PhCheckCircle as CheckCircle,
  PhFileText as FileText,
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
          <FileText :size="21" weight="duotone" />
        </span>
        <div>
          <p>查估書與送審</p>
          <h2 id="submit-summary-title">{{ caseModel.caseNo }}｜{{ caseModel.name }}</h2>
          <span>{{ readinessMessage }}</span>
        </div>
      </div>
      <span class="submit-summary__status" :data-status="statusValue">案件狀態：{{ displayedCaseStatus }}</span>
    </div>

    <div class="submit-summary__facts" aria-label="目前送審資料摘要">
      <span :data-state="authoritativeF02 ? 'ready' : 'pending'">
        <CheckCircle v-if="authoritativeF02" :size="18" weight="duotone" aria-hidden="true" />
        <WarningCircle v-else :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>比較法調查估價表（F02）</span>
          <strong>{{ authoritativeF02 ? `第 ${authoritativeF02.versionNo} 版正式資料` : '尚未取得正式版本' }}</strong>
        </div>
      </span>
      <span :data-state="formalReport || completeReport ? 'ready' : 'pending'">
        <FileText :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>完整送審 PDF</span>
          <strong>{{ formalReport?.filename || completeReport?.filename || '尚未產生' }}</strong>
        </div>
      </span>
      <span :data-state="validation ? validation.canGenerateReport ? 'ready' : 'blocked' : 'pending'">
        <CheckCircle v-if="validation?.canGenerateReport" :size="18" weight="duotone" aria-hidden="true" />
        <WarningCircle v-else :size="18" weight="duotone" aria-hidden="true" />
        <div>
          <span>估價資料檢核</span>
          <strong>{{ !validation ? '尚未執行' : validation.canGenerateReport ? '已通過' : `${validation.failedCount} 項待修正` }}</strong>
        </div>
      </span>
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
.submit-summary__facts > span {
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
.submit-summary__title > div > span { display: block; margin-top: 5px; color: var(--app-muted); font-size: 11px; line-height: 1.5; }
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

.submit-summary__facts { display: flex; flex-wrap: wrap; gap: 8px; }
.submit-summary__facts > span {
  min-width: 0;
  flex: 1 1 220px;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-accent-deep);
  background: #fbfcfe;
}
.submit-summary__facts > span[data-state="ready"] { border-color: #cfe4da; color: #2f7456; background: #f5faf7; }
.submit-summary__facts > span[data-state="pending"] { border-color: #e4dfcf; color: #8a6515; background: #fffaf0; }
.submit-summary__facts > span[data-state="blocked"] { border-color: #edc8c0; color: #a44334; background: #fff5f3; }
.submit-summary__facts > span > div { min-width: 0; display: grid; gap: 3px; }
.submit-summary__facts > span > div > span { color: var(--app-muted); font-size: 10px; font-weight: 800; }
.submit-summary__facts strong { color: var(--app-ink); font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }

@media (max-width: 980px) {
  .submit-summary__facts > span { flex-basis: 280px; }
}

@media (max-width: 640px) {
  .submit-summary { padding: 16px; }
  .submit-summary__heading { align-items: flex-start; flex-direction: column; }
  .submit-summary__facts { display: grid; grid-template-columns: 1fr; }
}
</style>
