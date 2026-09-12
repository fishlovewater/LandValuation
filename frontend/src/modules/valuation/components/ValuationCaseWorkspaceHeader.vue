<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  PhArrowLeft as ArrowLeft,
  PhCheck as Check,
  PhInfo as Info,
  PhX as X,
} from '@phosphor-icons/vue'
import { valuationCaseTypeLabel, valuationLandUseLabel } from '../valuation.labels'
import type { ValuationCaseModel, ValuationWorkspaceStage } from '../valuation.types'

export type { ValuationWorkspaceStage } from '../valuation.types'

const props = withDefaults(defineProps<{
  caseModel: ValuationCaseModel
  districtLabel: string
  statusLabel: string
  currentStage: ValuationWorkspaceStage
  progressPercent?: number
  issueCounts?: Partial<Record<Exclude<ValuationWorkspaceStage, 'case'>, number>>
  reportAvailable?: boolean
}>(), {
  progressPercent: 0,
  issueCounts: () => ({}),
  reportAvailable: false,
})

const emit = defineEmits<{
  back: []
  navigate: [stage: ValuationWorkspaceStage]
}>()

const detailsOpen = ref(false)

const stages = [
  { key: 'documents', label: '來源資料', description: '文件與辨識', legacyTestId: 'valuation-step-2' },
  { key: 'data', label: '估價資料', description: '宗地、比準地與採用值', legacyTestId: 'valuation-step-3' },
  { key: 'calculation', label: '計算與檢核', description: '估價結果與資料檢核', legacyTestId: 'valuation-step-4' },
  { key: 'report', label: '查估書與送審', description: '正式文件與送審', legacyTestId: 'valuation-step-5' },
] as const
type MainWorkspaceStage = (typeof stages)[number]['key']

const currentIndex = computed(() => {
  if (props.currentStage === 'case') return -1
  if (props.currentStage === 'ai-review') return 0
  return stages.findIndex((stage) => stage.key === props.currentStage)
})

const sourceIssueCount = computed(() =>
  (props.issueCounts.documents ?? 0) + (props.issueCounts['ai-review'] ?? 0),
)

const normalizedProgress = computed(() => Math.max(0, Math.min(100, Math.round(props.progressPercent))))

function stageComplete(index: number): boolean {
  if (props.currentStage === 'case') return false
  return index < currentIndex.value
}

function stageActive(stage: MainWorkspaceStage): boolean {
  if (stage === 'documents') return props.currentStage === 'documents' || props.currentStage === 'ai-review'
  return props.currentStage === stage
}

function stageIssueCount(stage: MainWorkspaceStage): number {
  if (stage === 'documents') return sourceIssueCount.value
  return props.issueCounts[stage] ?? 0
}

function stageDisabled(stage: MainWorkspaceStage): boolean {
  return stage === 'report' && !props.reportAvailable && props.currentStage !== 'report'
}

function navigate(stage: MainWorkspaceStage): void {
  if (stageDisabled(stage)) return
  emit('navigate', stage)
}
</script>

<template>
  <section class="case-workspace-header" data-testid="valuation-case-workspace-header" aria-label="目前估價案件與流程進度">
    <div class="case-workspace-header__case-row" data-testid="case-context">
      <button class="case-workspace-header__back" type="button" aria-label="返回估價案件列表" title="返回案件列表" @click="emit('back')">
        <ArrowLeft :size="19" weight="bold" aria-hidden="true" />
      </button>

      <div class="case-workspace-header__identity">
        <div class="case-workspace-header__title-line">
          <strong>{{ caseModel.caseNo }}</strong>
          <span aria-hidden="true">｜</span>
          <h1>{{ caseModel.name }}</h1>
        </div>
        <div class="case-workspace-header__meta">
          <span>{{ districtLabel }}</span>
          <span>估價基準日 {{ caseModel.valuationBaseDate }}</span>
          <span class="case-workspace-header__status">{{ statusLabel }}</span>
        </div>
      </div>

      <div class="case-workspace-header__details-wrap">
        <button
          class="case-workspace-header__info"
          type="button"
          title="案件基本資料"
          aria-label="查看案件基本資料"
          aria-controls="valuation-case-details"
          :aria-expanded="detailsOpen ? 'true' : 'false'"
          @click="detailsOpen = !detailsOpen"
        >
          <Info :size="20" weight="bold" aria-hidden="true" />
        </button>

        <div v-if="detailsOpen" id="valuation-case-details" class="case-workspace-header__details" role="dialog" aria-label="案件基本資料">
          <div class="case-workspace-header__details-heading">
            <div>
              <strong>案件基本資料</strong>
              <span>{{ caseModel.caseNo }}</span>
            </div>
            <button type="button" title="關閉" aria-label="關閉案件基本資料" @click="detailsOpen = false">
              <X :size="15" weight="bold" aria-hidden="true" />
            </button>
          </div>
          <dl>
            <div><dt>案件名稱</dt><dd>{{ caseModel.name }}</dd></div>
            <div><dt>案件類型</dt><dd>{{ valuationCaseTypeLabel(caseModel.caseType) }}</dd></div>
            <div><dt>申請機關</dt><dd>{{ caseModel.requestingAgency || '未提供' }}</dd></div>
            <div><dt>行政區</dt><dd>{{ districtLabel }}</dd></div>
            <div><dt>估價基準日</dt><dd>{{ caseModel.valuationBaseDate }}</dd></div>
            <div><dt>估價作業期限</dt><dd>{{ caseModel.valuationDueDate || '未設定' }}</dd></div>
            <div><dt>土地用途</dt><dd>{{ valuationLandUseLabel(caseModel.landUseType) }}</dd></div>
            <div><dt>案件狀態</dt><dd>{{ statusLabel }}</dd></div>
          </dl>
        </div>
      </div>
    </div>

    <div class="case-workspace-header__workflow">
      <ol class="case-workspace-header__stages">
        <li
          v-for="(stage, index) in stages"
          :key="stage.key"
          :class="{
            'is-active': stageActive(stage.key),
            'is-complete': stageComplete(index),
          }"
        >
          <button
            type="button"
            :data-testid="stage.legacyTestId"
            :data-workspace-stage="stage.key"
            :disabled="stageDisabled(stage.key)"
            :aria-current="stageActive(stage.key) ? 'step' : undefined"
            @click="navigate(stage.key)"
          >
            <span class="case-workspace-header__stage-number" aria-hidden="true">
              <Check v-if="stageComplete(index)" :size="12" weight="bold" />
              <template v-else>{{ index + 1 }}</template>
            </span>
            <span class="case-workspace-header__stage-copy">
              <strong>{{ stage.label }}</strong>
              <small>{{ stage.description }}</small>
            </span>
            <span v-if="stageIssueCount(stage.key)" class="case-workspace-header__issue" aria-label="待處理項目">
              {{ stageIssueCount(stage.key) }}
            </span>
          </button>
        </li>
      </ol>
    </div>

    <div class="case-workspace-header__progress" aria-label="案件完成進度" :aria-valuenow="normalizedProgress" aria-valuemin="0" aria-valuemax="100" role="progressbar">
      <span :style="{ width: `${normalizedProgress}%` }"></span>
    </div>
  </section>
</template>

<style scoped>
.case-workspace-header {
  position: sticky;
  z-index: 20;
  top: 82px;
  display: grid;
  border-bottom: 1px solid #dce4ed;
  background: #fff;
  box-shadow: 0 8px 24px rgba(36, 64, 94, .07);
}

.case-workspace-header__case-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 11px 18px 8px;
}

.case-workspace-header__back,
.case-workspace-header__info {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  padding: 0;
  border: 1px solid #d9e2ec;
  border-radius: 9px;
  color: #52657a;
  background: #fff;
  cursor: pointer;
}

.case-workspace-header__back:hover,
.case-workspace-header__info:hover,
.case-workspace-header__back:focus-visible,
.case-workspace-header__info:focus-visible {
  border-color: #8aa5c0;
  outline: 0;
  color: #244d73;
  background: #f3f7fb;
}

.case-workspace-header__identity {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.case-workspace-header__title-line {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 5px;
}

.case-workspace-header__title-line strong {
  flex: 0 0 auto;
  color: #244d73;
  font-size: 13px;
}

.case-workspace-header__title-line > span {
  color: #a2adba;
}

.case-workspace-header__title-line h1 {
  overflow: hidden;
  margin: 0;
  color: var(--app-ink);
  font-size: 15px;
  font-weight: 800;
  letter-spacing: -.01em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-workspace-header__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  color: #6d7e90;
  font-size: 10px;
  font-weight: 700;
}

.case-workspace-header__status {
  color: #2f745b;
}

.case-workspace-header__details-wrap {
  position: relative;
}

.case-workspace-header__details {
  position: absolute;
  z-index: 40;
  top: calc(100% + 8px);
  right: 0;
  width: min(390px, calc(100vw - 32px));
  padding: 14px;
  border: 1px solid #d8e1eb;
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(29, 49, 73, .18);
}

.case-workspace-header__details-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8ef;
}

.case-workspace-header__details-heading > div {
  display: grid;
  gap: 2px;
}

.case-workspace-header__details-heading strong {
  color: var(--app-ink);
  font-size: 13px;
}

.case-workspace-header__details-heading span {
  color: #708196;
  font-size: 10px;
}

.case-workspace-header__details-heading button {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 7px;
  color: #617386;
  background: #f1f4f7;
  cursor: pointer;
  font-size: 10px;
  font-weight: 800;
}

.case-workspace-header__details dl {
  display: grid;
  gap: 0;
  margin: 0;
}

.case-workspace-header__details dl > div {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  gap: 12px;
  padding: 8px 2px;
  border-bottom: 1px solid #edf1f5;
}

.case-workspace-header__details dl > div:last-child {
  border-bottom: 0;
}

.case-workspace-header__details dt {
  color: #7b8a9b;
  font-size: 10px;
  font-weight: 800;
}

.case-workspace-header__details dd {
  margin: 0;
  color: #354a60;
  font-size: 11px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.case-workspace-header__workflow {
  display: flex;
  align-items: stretch;
  gap: 10px;
  padding: 3px 18px 8px;
}

.case-workspace-header__prerequisite {
  display: flex;
  flex: 0 0 auto;
  min-height: 40px;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  color: #506276;
  background: transparent;
  cursor: pointer;
  font-size: 10px;
  font-weight: 850;
}

.case-workspace-header__prerequisite:hover,
.case-workspace-header__prerequisite.is-active {
  color: #244d73;
  background: #edf4fb;
}

.case-workspace-header__check {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 50%;
  color: #2f745b;
  background: #eaf5ef;
}

.case-workspace-header__divider {
  width: 1px;
  align-self: stretch;
  background: #e0e6ed;
}

.case-workspace-header__stages {
  display: grid;
  min-width: 0;
  flex: 1 1 auto;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 5px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.case-workspace-header__stages li {
  min-width: 0;
}

.case-workspace-header__stages button {
  display: flex;
  width: 100%;
  min-height: 40px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 5px 7px;
  border: 0;
  border-radius: 8px;
  color: #718094;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 10px;
  font-weight: 800;
}

.case-workspace-header__stages button:hover:not(:disabled) {
  color: #355978;
  background: #f3f7fb;
}

.case-workspace-header__stages button:disabled {
  cursor: not-allowed;
  opacity: .44;
}

.case-workspace-header__stages li.is-active button {
  color: #244d73;
  background: #edf4fb;
}

.case-workspace-header__stages li.is-complete button {
  color: #3d6f5b;
}

.case-workspace-header__stage-number {
  display: grid;
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  place-items: center;
  border: 1px solid #cfd8e2;
  border-radius: 50%;
  color: #748498;
  background: #fff;
  font-size: 9px;
}

.is-active .case-workspace-header__stage-number {
  border-color: #2e5984;
  color: #fff;
  background: #2e5984;
}

.is-complete .case-workspace-header__stage-number {
  border-color: #a8cdbd;
  color: #2f745b;
  background: #eaf5ef;
}

.case-workspace-header__stage-copy { display:grid; min-width:0; gap:1px; text-align:left; }
.case-workspace-header__stage-copy strong { overflow:hidden; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.case-workspace-header__stage-copy small { overflow:hidden; color:#8391a0; font-size:8px; font-weight:700; text-overflow:ellipsis; white-space:nowrap; }
.is-active .case-workspace-header__stage-copy small { color:#5f7892; }
.is-complete .case-workspace-header__stage-copy small { color:#708d80; }

.case-workspace-header__issue {
  display: inline-grid;
  min-width: 18px;
  height: 18px;
  place-items: center;
  padding-inline: 4px;
  border-radius: 999px;
  color: #925421;
  background: #fff0df;
  font-size: 8px;
  font-weight: 900;
}

.case-workspace-header__progress {
  height: 3px;
  overflow: hidden;
  background: #edf1f5;
}

.case-workspace-header__progress span {
  display: block;
  height: 100%;
  background: #2e5984;
  transition: width 180ms ease;
}

@media (max-width: 900px) {
  .case-workspace-header {
    top: 74px;
  }

  .case-workspace-header__case-row {
    padding-inline: 12px;
  }

  .case-workspace-header__workflow {
    overflow-x: auto;
    padding-inline: 12px;
  }

  .case-workspace-header__stages {
    min-width: 620px;
  }
}

@media (max-width: 640px) {
  .case-workspace-header__meta {
    display: none;
  }

  .case-workspace-header__title-line h1 {
    max-width: 52vw;
    font-size: 13px;
  }

  .case-workspace-header__title-line > span {
    display: none;
  }
}
</style>
