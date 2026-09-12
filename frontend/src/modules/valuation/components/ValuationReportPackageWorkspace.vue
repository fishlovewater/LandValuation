<script setup lang="ts">
import { computed } from 'vue'
import {
  PhCalculator as Calculator,
  PhCheckCircle as CheckCircle,
  PhFileText as FileText,
  PhPencilSimple as PencilSimple,
  PhShieldCheck as ShieldCheck,
} from '@phosphor-icons/vue'
import type {
  ReportPageCode,
  ReportPageResponseDto,
  ValuationFormModel,
} from '../valuation.types'
import ComparisonSetupPanel from './ComparisonSetupPanel.vue'
import ReportPageEditor from './ReportPageEditor.vue'

interface ReportPageConfirmations {
  s01: boolean
  f02Rf: boolean
  f02: boolean
}

const props = defineProps<{
  caseId: string
  reportId: string
  authoritativeF02: ValuationFormModel | null
  editors: Partial<Record<ReportPageCode, ReportPageResponseDto>>
  activePageCode: ReportPageCode
  editorsLoading: boolean
  editorSaving: ReportPageCode | null
  editorNotice: string
  confirmations: ReportPageConfirmations
  pagesConfirmed: boolean
  pageSaving: boolean
  pageCalculating: boolean
  pageValidating: boolean
  pageSaved: boolean
  pageCalculated: boolean
}>()

const emit = defineEmits<{
  loadEditors: []
  'update:activePageCode': [pageCode: ReportPageCode]
  comparisonChanged: []
  saveEditor: [value: { pageCode: ReportPageCode; payload: Record<string, unknown> }]
  updateConfirmation: [key: keyof ReportPageConfirmations, checked: boolean]
  savePages: []
  calculate: []
  validate: []
}>()

const pageCodes: readonly ReportPageCode[] = ['S01', 'F02-RF', 'F02']

const activePage = computed(() => props.editors[props.activePageCode] ?? null)
const hasEditors = computed(() => Object.keys(props.editors).length > 0)

function pageLabel(code: ReportPageCode): string {
  return ({
    S01: '勘查資料（S01）',
    'F02-RF': '影響因素（F02-RF）',
    F02: '比較法資料（F02）',
  } as const)[code]
}

function updateConfirmation(key: keyof ReportPageConfirmations, event: Event): void {
  emit('updateConfirmation', key, (event.target as HTMLInputElement).checked)
}
</script>

<template>
  <section
    class="report-package-workspace"
    data-testid="report-package-draft-flow"
    aria-labelledby="report-package-title"
  >
    <div class="report-package-workspace__heading">
      <div class="report-package-workspace__title">
        <span class="report-package-workspace__icon" aria-hidden="true">
          <FileText :size="22" weight="duotone" />
        </span>
        <div>
          <p>查估書確認</p>
          <h2 id="report-package-title">完整查估書三頁確認</h2>
        </div>
      </div>
      <span class="report-package-workspace__marker">三頁草稿</span>
    </div>

    <div
      v-if="props.authoritativeF02"
      class="report-package-workspace__authoritative"
      data-testid="report-package-authoritative"
    >
      <CheckCircle :size="20" weight="fill" aria-hidden="true" />
      <div>
        <strong>三頁已完成正式檢核</strong>
        <span>F02 第 {{ props.authoritativeF02.versionNo }} 版</span>
      </div>
    </div>

    <template v-else>
      <p class="report-package-workspace__description">
        先檢視或修改 S01、F02-RF、F02，再逐頁確認。修改後必須重新儲存確認、正式計算與檢核。
      </p>

      <div class="report-package-workspace__editor-shell">
        <button
          v-if="!hasEditors"
          class="report-package-workspace__button"
          type="button"
          data-testid="open-report-page-editors"
          :disabled="props.editorsLoading"
          @click="emit('loadEditors')"
        >
          <PencilSimple v-if="!props.editorsLoading" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.editorsLoading ? '三頁載入中…' : '檢視／修改三頁資料' }}</span>
        </button>

        <template v-else>
          <nav class="report-package-workspace__tabs" aria-label="三頁表單切換">
            <button
              v-for="pageCode in pageCodes"
              :key="pageCode"
              type="button"
              :class="{ 'is-active': props.activePageCode === pageCode }"
              :aria-current="props.activePageCode === pageCode ? 'page' : undefined"
              @click="emit('update:activePageCode', pageCode)"
            >
              {{ pageLabel(pageCode) }}
            </button>
          </nav>

          <ComparisonSetupPanel
            v-if="props.activePageCode === 'F02' && props.editors.F02"
            :case-id="props.caseId"
            :report-id="props.reportId"
            :page="props.editors.F02"
            @changed="emit('comparisonChanged')"
          />

          <ReportPageEditor
            v-if="activePage"
            :page="activePage"
            :saving="props.editorSaving === props.activePageCode"
            @save="emit('saveEditor', $event)"
          />
        </template>

        <p v-if="props.editorNotice" class="report-package-workspace__notice" role="status">
          {{ props.editorNotice }}
        </p>
      </div>

      <div class="report-package-workspace__confirmations" aria-label="三頁人工確認">
        <label>
          <input
            data-testid="report-page-s01-confirm"
            type="checkbox"
            :checked="props.confirmations.s01"
            @change="updateConfirmation('s01', $event)"
          />
          <span>我已確認 S01 勘查資料與來源</span>
        </label>
        <label>
          <input
            data-testid="report-page-f02-rf-confirm"
            type="checkbox"
            :checked="props.confirmations.f02Rf"
            @change="updateConfirmation('f02Rf', $event)"
          />
          <span>我已確認 F02-RF 全部因素級距</span>
        </label>
        <label>
          <input
            data-testid="report-page-f02-confirm"
            type="checkbox"
            :checked="props.confirmations.f02"
            @change="updateConfirmation('f02', $event)"
          />
          <span>我已確認 F02 比較標的與權重</span>
        </label>
      </div>

      <div class="report-package-workspace__actions">
        <button
          type="button"
          data-testid="save-report-pages"
          :disabled="!props.pagesConfirmed || props.pageSaving || props.pageCalculating || props.pageValidating"
          @click="emit('savePages')"
        >
          <CheckCircle v-if="!props.pageSaving" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.pageSaving ? '三頁儲存中…' : '儲存三頁確認' }}</span>
        </button>
        <button
          type="button"
          data-testid="run-formal-calculation"
          :disabled="!props.pageSaved || props.pageCalculating || props.pageValidating"
          @click="emit('calculate')"
        >
          <Calculator v-if="!props.pageCalculating" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.pageCalculating ? '正式計算中…' : '執行正式計算' }}</span>
        </button>
        <button
          class="is-primary"
          type="button"
          data-testid="run-report-formal-validation"
          :disabled="!props.pageCalculated || props.pageValidating"
          @click="emit('validate')"
        >
          <ShieldCheck v-if="!props.pageValidating" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.pageValidating ? '三頁正式檢核中…' : '執行三頁正式檢核' }}</span>
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.report-package-workspace { display: grid; gap: 16px; padding: 22px; border: 1px solid var(--app-line); border-radius: var(--app-radius-md); background: #fff; }
.report-package-workspace__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.report-package-workspace__title { display: flex; align-items: flex-start; gap: 11px; min-width: 0; }
.report-package-workspace__icon { display: grid; width: 40px; height: 40px; flex: 0 0 auto; place-items: center; border-radius: 9px; color: #2e5984; background: #edf4fb; }
.report-package-workspace__title p { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.report-package-workspace__title h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; font-weight: 600; letter-spacing: -.04em; }
.report-package-workspace__marker { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 10px; border: 1px solid var(--app-line); border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f8fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.report-package-workspace__authoritative { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 10px; align-items: start; padding: 14px; border: 1px solid rgba(59,129,102,.24); border-radius: var(--app-radius-sm); color: var(--app-green); background: rgba(59,129,102,.08); }
.report-package-workspace__authoritative div { display: grid; gap: 4px; }
.report-package-workspace__authoritative span { color: var(--app-ink-soft); font-size: 12px; }
.report-package-workspace__description { margin: 0; color: var(--app-muted); font-size: 13px; line-height: 1.6; }
.report-package-workspace__editor-shell { display: grid; gap: 12px; }
.report-package-workspace__button,
.report-package-workspace__actions button { display: inline-flex; min-height: 42px; width: fit-content; align-items: center; justify-content: center; gap: 7px; padding: 9px 15px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 12px; font-weight: 800; }
.report-package-workspace__button:disabled,
.report-package-workspace__actions button:disabled { cursor: not-allowed; opacity: .55; }
.report-package-workspace__tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.report-package-workspace__tabs button { min-height: 38px; padding: 7px 13px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 12px; font-weight: 900; }
.report-package-workspace__tabs button.is-active { border-color: rgba(200,91,67,.32); color: var(--app-accent-deep); background: var(--app-accent-soft); }
.report-package-workspace__notice { margin: 0; padding: 10px 12px; border-radius: 8px; color: #2e5984; background: #edf4fb; font-size: 12px; line-height: 1.6; }
.report-package-workspace__confirmations { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.report-package-workspace__confirmations label { display: flex; align-items: flex-start; gap: 8px; color: var(--app-ink); font-size: 13px; font-weight: 700; }
.report-package-workspace__confirmations input { margin-top: 2px; accent-color: var(--app-accent); }
.report-package-workspace__actions { display: flex; flex-wrap: wrap; gap: 10px; }
.report-package-workspace__actions button.is-primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }

@media (max-width: 760px) {
  .report-package-workspace { padding: 16px; }
  .report-package-workspace__heading { flex-direction: column; }
  .report-package-workspace__button,
  .report-package-workspace__actions button { width: 100%; }
  .report-package-workspace__actions { flex-direction: column; }
}
</style>