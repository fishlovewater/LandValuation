<script setup lang="ts">
import {
  PhBuildings as Buildings,
  PhCalendarBlank as CalendarBlank,
  PhCheckCircle as CheckCircle,
  PhClockCountdown as ClockCountdown,
  PhFileText as FileText,
  PhFolderOpen as FolderOpen,
  PhMapPin as MapPin,
  PhTag as Tag,
} from '@phosphor-icons/vue'
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

function caseTypeDisplayLabel(value: string): string {
  const normalized = value.trim().toUpperCase()
  const labels: Readonly<Record<string, string>> = {
    LAND: '土地徵收補償市價查估',
    LAND_ACQUISITION: '土地徵收補償市價查估',
    VALUATION: '土地估價案件',
    EXTERNAL_REVIEW: '外部送審案件',
  }
  if (labels[normalized]) return labels[normalized]
  if (/[^\x00-\x7F]/.test(value)) return value
  return '其他估價案件'
}
</script>

<template>
  <section class="case-overview" data-testid="valuation-case-overview" aria-labelledby="case-summary-title">
    <div class="case-overview__heading">
      <div class="case-overview__title">
        <span class="case-overview__title-icon" aria-hidden="true">
          <FolderOpen :size="22" weight="duotone" />
        </span>
        <div>
          <p>案件資料</p>
          <h2 id="case-summary-title">{{ props.caseModel.caseNo }}｜{{ props.caseModel.name }}</h2>
          <span>確認案件基本資料與目前已建立的查估書表版本。</span>
        </div>
      </div>
      <span class="case-overview__source">
        <CheckCircle :size="14" weight="fill" aria-hidden="true" />
        {{ props.caseModel.source.label }}
      </span>
    </div>

    <div class="case-overview__summary">
      <div>
        <span class="case-overview__summary-icon" aria-hidden="true"><Tag :size="16" weight="duotone" /></span>
        <span>案件類型</span>
        <strong>{{ caseTypeDisplayLabel(props.caseModel.caseType) }}</strong>
      </div>
      <div>
        <span class="case-overview__summary-icon" aria-hidden="true"><Buildings :size="16" weight="duotone" /></span>
        <span>申請機關</span>
        <strong>{{ props.caseModel.requestingAgency || '未提供' }}</strong>
      </div>
      <div>
        <span class="case-overview__summary-icon" aria-hidden="true"><CalendarBlank :size="16" weight="duotone" /></span>
        <span>估價基準日</span>
        <strong>{{ props.caseModel.valuationBaseDate }}</strong>
      </div>
      <div>
        <span class="case-overview__summary-icon" aria-hidden="true"><ClockCountdown :size="16" weight="duotone" /></span>
        <span>估價作業期限</span>
        <strong>{{ props.caseModel.valuationDueDate || '未設定' }}</strong>
      </div>
      <div>
        <span class="case-overview__summary-icon" aria-hidden="true"><MapPin :size="16" weight="duotone" /></span>
        <span>行政區</span>
        <strong>{{ props.districtLabel }}</strong>
      </div>
    </div>

    <section class="case-overview__forms-section" aria-labelledby="case-forms-title">
      <div class="case-overview__forms-heading">
        <div>
          <FileText :size="17" weight="duotone" aria-hidden="true" />
          <strong id="case-forms-title">已建立查估書表</strong>
        </div>
        <span>{{ props.forms.length }} 份</span>
      </div>
      <div v-if="props.forms.length" class="case-overview__forms" aria-label="已建立估價表">
        <article v-for="form in props.forms" :key="form.formInstanceId">
          <div class="case-overview__form-title">
            <strong>{{ formDisplayName(form.formCode) }}</strong>
            <span class="case-overview__form-code">{{ form.formCode }}</span>
          </div>
          <span>第 {{ form.versionNo }} 版｜{{ statusLabel(form.status) }}</span>
          <small>{{ form.source.label }}</small>
        </article>
      </div>
      <div v-else class="case-overview__empty">
        <FileText :size="20" weight="duotone" aria-hidden="true" />
        <span>目前尚未建立估價表；確認案件資料後可從文件與辨識開始作業。</span>
      </div>
    </section>
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
.case-overview__title { display: flex; align-items: flex-start; gap: 10px; min-width: 0; }
.case-overview__title-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 10px;
  color: var(--app-accent-deep);
  background: #edf4fb;
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
.case-overview__title > div > span {
  display: block;
  margin-top: 5px;
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.55;
}
.case-overview__source {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  gap: 5px;
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
  grid-template-columns: auto minmax(0, 1fr);
  gap: 5px;
  min-width: 0;
  padding: 13px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  background: #fbfcfe;
}
.case-overview__summary-icon {
  display: grid;
  grid-row: 1 / span 2;
  width: 30px;
  height: 30px;
  align-self: center;
  place-items: center;
  border-radius: 8px;
  color: var(--app-accent-deep) !important;
  background: #edf4fb;
}
.case-overview__summary span {
  color: var(--app-muted);
  font-size: 11px;
  font-weight: 800;
}
.case-overview__summary strong {
  grid-column: 2;
  overflow-wrap: anywhere;
  color: var(--app-ink);
  font-size: 13px;
}
.case-overview__forms-section {
  display: grid;
  gap: 9px;
  padding-top: 14px;
  border-top: 1px solid var(--app-line);
}
.case-overview__forms-heading,
.case-overview__forms-heading > div,
.case-overview__form-title,
.case-overview__empty {
  display: flex;
  align-items: center;
}
.case-overview__forms-heading { justify-content: space-between; gap: 12px; }
.case-overview__forms-heading > div { gap: 6px; color: var(--app-accent-deep); }
.case-overview__forms-heading strong { color: var(--app-ink); font-size: 12px; }
.case-overview__forms-heading > span { color: var(--app-muted); font-size: 10px; font-weight: 850; }
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
.case-overview__form-title { justify-content: space-between; gap: 8px; }
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
.case-overview__empty {
  min-height: 64px;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  border: 1px dashed #d4dee8;
  border-radius: 9px;
  background: #fafcfe;
  line-height: 1.55;
  text-align: center;
}

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
