<script setup lang="ts">
import { statusLabel } from '../../../utils/enumLabels'
import type { ValuationCaseModel, ValuationFormModel } from '../valuation.types'

const props = defineProps<{
  caseModel: ValuationCaseModel
  forms: readonly ValuationFormModel[]
  districtLabel: string
}>()

const formNames: Readonly<Record<string, string>> = {
  S01: '地價區段勘查表',
  F01: '買賣實例調查估價表',
  F02: '比較法調查估價表',
  'F02-RF': '影響地價區域因素分析明細表',
  F03: '比準地地價估計表',
  F04: '徵收土地宗地市價估計表',
}

function formDisplayName(code: string): string {
  return formNames[code] ?? '查估書表'
}
</script>

<template>
  <section class="case-overview" data-testid="valuation-case-overview" aria-labelledby="case-summary-title">
    <div class="case-overview__heading">
      <div>
        <p>案件資料</p>
        <h2 id="case-summary-title">{{ props.caseModel.caseNo }}｜{{ props.caseModel.name }}</h2>
      </div>
      <span class="case-overview__source">{{ props.caseModel.source.label }}</span>
    </div>

    <div class="case-overview__summary">
      <div><span>案件類型</span><strong>{{ props.caseModel.caseType }}</strong></div>
      <div><span>申請機關</span><strong>{{ props.caseModel.requestingAgency || '未提供' }}</strong></div>
      <div><span>估價基準日</span><strong>{{ props.caseModel.valuationBaseDate }}</strong></div>
      <div><span>估價作業期限</span><strong>{{ props.caseModel.valuationDueDate || '未設定' }}</strong></div>
      <div><span>行政區</span><strong>{{ props.districtLabel }}</strong></div>
    </div>

    <div v-if="props.forms.length" class="case-overview__forms" aria-label="已建立估價表">
      <article v-for="form in props.forms" :key="form.formInstanceId">
        <strong>{{ formDisplayName(form.formCode) }}</strong>
        <span class="case-overview__form-code">{{ form.formCode }}</span>
        <span>第 {{ form.versionNo }} 版｜{{ statusLabel(form.status) }}</span>
        <small>{{ form.source.label }}</small>
      </article>
    </div>
    <p v-else class="case-overview__empty">目前尚未建立估價表；確認案件資料後可從文件與辨識開始作業。</p>
  </section>
</template>

<style scoped>
.case-overview {
  display: grid;
  gap: 18px;
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: 12px;
  background: var(--app-paper-strong);
}
.case-overview__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.case-overview__heading p {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}
.case-overview__heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -.04em;
}
.case-overview__source {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid rgba(59, 129, 102, .24);
  border-radius: 999px;
  color: var(--app-green);
  background: rgba(59, 129, 102, .08);
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}
.case-overview__summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}
.case-overview__summary > div {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 13px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  background: #fbfcfe;
}
.case-overview__summary span {
  color: var(--app-muted);
  font-size: 11px;
  font-weight: 800;
}
.case-overview__summary strong {
  overflow-wrap: anywhere;
  color: var(--app-ink);
  font-size: 13px;
}
.case-overview__forms {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.case-overview__forms article {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  color: var(--app-ink-soft);
  background: #fff;
  font-size: 11px;
}
.case-overview__forms strong {
  color: var(--app-ink);
  font-size: 12px;
}
.case-overview__form-code {
  color: #2e5984;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .06em;
}
.case-overview__forms small,
.case-overview__empty {
  color: var(--app-muted);
  font-size: 11px;
}
.case-overview__empty { margin: 0; }

@media (max-width: 960px) {
  .case-overview__summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .case-overview__forms { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 640px) {
  .case-overview { padding: 16px; }
  .case-overview__heading { flex-direction: column; }
  .case-overview__summary,
  .case-overview__forms { grid-template-columns: 1fr; }
}
</style>
