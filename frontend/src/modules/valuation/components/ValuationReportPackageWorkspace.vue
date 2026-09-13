<script setup lang="ts">
import { computed } from 'vue'
import {
  PhArrowRight as ArrowRight,
  PhCalculator as Calculator,
  PhCheckCircle as CheckCircle,
  PhEye as Eye,
  PhFileText as FileText,
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
  caseEditable: boolean
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
const confirmationCount = computed(() => [
  props.confirmations.s01,
  props.confirmations.f02Rf,
  props.confirmations.f02,
].filter(Boolean).length)
const activePageIndex = computed(() => Math.max(0, pageCodes.indexOf(props.activePageCode)))
const nextPageCode = computed(() => pageCodes[activePageIndex.value + 1] ?? null)

function confirmationKey(code: ReportPageCode): keyof ReportPageConfirmations {
  if (code === 'S01') return 's01'
  if (code === 'F02-RF') return 'f02Rf'
  return 'f02'
}

function pageConfirmed(code: ReportPageCode): boolean {
  return props.confirmations[confirmationKey(code)]
}

function pagePurpose(code: ReportPageCode): string {
  return ({
    S01: '確認現場勘查、土地使用與道路等基礎資料。',
    'F02-RF': '確認區域因素級距與影響地價的採用內容。',
    F02: '確認比較標的、權重與最後採用的比較法資料。',
  } as const)[code]
}

function pageLabel(code: ReportPageCode): string {
  return ({
    S01: '勘查資料（S01）',
    'F02-RF': '影響因素（F02-RF）',
    F02: '比較法資料（F02）',
  } as const)[code]
}

function updateActiveConfirmation(event: Event): void {
  const checked = (event.target as HTMLInputElement).checked
  emit('updateConfirmation', confirmationKey(props.activePageCode), checked)
}

function goToNextPage(): void {
  if (!nextPageCode.value || !pageConfirmed(props.activePageCode)) return
  emit('update:activePageCode', nextPageCode.value)
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
          <h2 id="report-package-title">逐頁確認查估書內容</h2>
          <span>依序確認 S01、F02-RF、F02；每次只處理目前頁面，三頁完成後再更新查估書計算。</span>
        </div>
      </div>
      <span class="report-package-workspace__marker" :data-state="props.authoritativeF02 ? 'ready' : 'draft'">
        <CheckCircle v-if="props.authoritativeF02" :size="14" weight="fill" aria-hidden="true" />
        <FileText v-else :size="14" weight="duotone" aria-hidden="true" />
        {{ props.authoritativeF02 ? '正式版本已完成' : '三頁草稿' }}
      </span>
    </div>

    <div v-if="!props.authoritativeF02" class="report-package-workspace__progress" aria-label="查估書頁面確認進度">
      <div>
        <span>查估書內容</span>
        <strong>{{ confirmationCount }} / 3 頁已確認</strong>
      </div>
      <div class="report-package-workspace__progress-track" role="progressbar" :aria-valuenow="confirmationCount" aria-valuemin="0" aria-valuemax="3">
        <span :style="{ width: `${(confirmationCount / 3) * 100}%` }"></span>
      </div>
    </div>

    <div
      v-if="props.authoritativeF02"
      class="report-package-workspace__authoritative"
      data-testid="report-package-authoritative"
    >
      <CheckCircle :size="20" weight="fill" aria-hidden="true" />
      <div>
        <strong>查估書內容已完成確認</strong>
        <span>F02 第 {{ props.authoritativeF02.versionNo }} 版已確認</span>
        <small>下一步會以此版本進行送審文件檢核與正式 PDF 產製。</small>
      </div>
    </div>

    <template v-else>
      <div class="report-package-workspace__description">
        <Eye :size="17" weight="duotone" aria-hidden="true" />
        <span>先看目前頁面；內容正確就勾選「本頁已確認」，再按「下一頁」。需要修改時直接在本頁儲存後再確認。</span>
      </div>

      <div class="report-package-workspace__editor-shell">
        <button
          v-if="!hasEditors"
          class="report-package-workspace__button"
          type="button"
          data-testid="open-report-page-editors"
          :disabled="props.editorsLoading"
          @click="emit('loadEditors')"
        >
          <Eye v-if="!props.editorsLoading" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.editorsLoading ? '查估書載入中…' : '開始逐頁確認' }}</span>
        </button>

        <template v-else>
          <nav class="report-package-workspace__tabs" aria-label="三頁表單切換">
            <button
              v-for="(pageCode, index) in pageCodes"
              :key="pageCode"
              type="button"
              :class="{ 'is-active': props.activePageCode === pageCode, 'is-complete': pageConfirmed(pageCode) }"
              :aria-current="props.activePageCode === pageCode ? 'page' : undefined"
              @click="emit('update:activePageCode', pageCode)"
            >
              <span class="report-package-workspace__tab-index">
                <CheckCircle v-if="pageConfirmed(pageCode)" :size="13" weight="fill" aria-hidden="true" />
                <span v-else>{{ index + 1 }}</span>
              </span>
              <span class="report-package-workspace__tab-copy">
                <strong>{{ pageLabel(pageCode) }}</strong>
                <small>{{ pageConfirmed(pageCode) ? '已確認' : props.activePageCode === pageCode ? '目前頁面' : '待確認' }}</small>
              </span>
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

          <label v-if="activePage" class="report-package-workspace__active-confirmation" :data-checked="pageConfirmed(props.activePageCode)">
            <input
              :data-testid="props.activePageCode === 'S01' ? 'report-page-s01-confirm' : props.activePageCode === 'F02-RF' ? 'report-page-f02-rf-confirm' : 'report-page-f02-confirm'"
              type="checkbox"
              :checked="pageConfirmed(props.activePageCode)"
              @change="updateActiveConfirmation"
            />
            <span>
              <strong>{{ pageLabel(props.activePageCode) }}內容已確認</strong>
              <small>{{ pagePurpose(props.activePageCode) }}{{ nextPageCode ? ' 確認後即可前往下一頁。' : ' 這是最後一頁。' }}</small>
            </span>
            <CheckCircle v-if="pageConfirmed(props.activePageCode)" :size="20" weight="fill" aria-hidden="true" />
          </label>
        </template>

        <p v-if="props.editorNotice" class="report-package-workspace__notice" role="status">
          {{ props.editorNotice }}
        </p>
      </div>

      <div class="report-package-workspace__actions">
        <button
          v-show="!props.pageSaved && !props.pagesConfirmed && !!nextPageCode"
          class="is-primary"
          type="button"
          data-testid="report-next-page"
          :disabled="!pageConfirmed(props.activePageCode) || props.pageSaving || props.pageCalculating || props.pageValidating"
          @click="goToNextPage"
        >
          <span>下一頁：{{ nextPageCode ? pageLabel(nextPageCode) : '' }}</span>
          <ArrowRight :size="15" weight="bold" aria-hidden="true" />
        </button>
        <button
          v-show="!props.pageSaved && (props.pagesConfirmed || !nextPageCode)"
          type="button"
          data-testid="save-report-pages"
          :disabled="!props.caseEditable || !props.pagesConfirmed || props.pageSaving || props.pageCalculating || props.pageValidating"
          @click="emit('savePages')"
        >
          <CheckCircle v-if="!props.pageSaving" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.pageSaving ? '確認結果儲存中…' : props.pagesConfirmed ? '儲存三頁確認結果' : `還有 ${3 - confirmationCount} 頁待確認` }}</span>
        </button>
        <button
          v-show="props.pageSaved && !props.pageCalculated"
          type="button"
          data-testid="run-formal-calculation"
          :disabled="!props.caseEditable || !props.pageSaved || props.pageCalculating || props.pageValidating"
          @click="emit('calculate')"
        >
          <Calculator v-if="!props.pageCalculating" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.pageCalculating ? '查估書計算更新中…' : '更新查估書計算' }}</span>
        </button>
        <button
          v-show="props.pageCalculated"
          class="is-primary"
          type="button"
          data-testid="run-report-formal-validation"
          :disabled="!props.caseEditable || !props.pageCalculated || props.pageValidating"
          @click="emit('validate')"
        >
          <ShieldCheck v-if="!props.pageValidating" :size="16" weight="bold" aria-hidden="true" />
          <span>{{ props.pageValidating ? '查估書確認中…' : '完成查估書一致性確認' }}</span>
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
.report-package-workspace__title > div > span { display: block; margin-top: 5px; color: var(--app-muted); font-size: 11px; line-height: 1.5; }
.report-package-workspace__marker { display: inline-flex; min-height: 30px; align-items: center; gap: 5px; padding: 5px 10px; border: 1px solid var(--app-line); border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f8fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.report-package-workspace__marker[data-state="ready"] { border-color: #cfe4da; color: #2f7456; background: #f1f8f5; }
.report-package-workspace__progress { display:grid; gap:8px; padding:11px 12px; border:1px solid #dbe4ec; border-radius:9px; background:#fafcfe; }
.report-package-workspace__progress > div:first-child { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.report-package-workspace__progress span { color:var(--app-muted); font-size:10px; font-weight:800; }
.report-package-workspace__progress strong { color:var(--app-ink); font-size:11px; }
.report-package-workspace__progress-track { height:6px; overflow:hidden; border-radius:999px; background:#e6ebf0; }
.report-package-workspace__progress-track > span { display:block; height:100%; border-radius:inherit; background:#3c8368; transition:width .18s ease; }
.report-package-workspace__authoritative { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 10px; align-items: start; padding: 14px; border: 1px solid rgba(59,129,102,.24); border-radius: var(--app-radius-sm); color: var(--app-green); background: rgba(59,129,102,.08); }
.report-package-workspace__authoritative div { display: grid; gap: 4px; }
.report-package-workspace__authoritative span,
.report-package-workspace__authoritative small { color: var(--app-ink-soft); font-size: 11px; line-height: 1.5; }
.report-package-workspace__description { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 10px 12px; border: 1px solid #e0e7ef; border-radius: 8px; color: var(--app-ink-soft); background: #f8fafc; font-size: 11px; line-height: 1.6; }
.report-package-workspace__description > svg { flex: 0 0 auto; margin-top: 1px; color: var(--app-accent-deep); }
.report-package-workspace__editor-shell { display: grid; gap: 12px; }
.report-package-workspace__button,
.report-package-workspace__actions button { display: inline-flex; min-height: 42px; width: fit-content; align-items: center; justify-content: center; gap: 7px; padding: 9px 15px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-size: 12px; font-weight: 800; }
.report-package-workspace__button:disabled,
.report-package-workspace__actions button:disabled { cursor: not-allowed; opacity: .55; }
.report-package-workspace__tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.report-package-workspace__tabs button { display:grid; grid-template-columns:auto minmax(0,1fr); min-height:48px; flex:1 1 180px; align-items:center; gap:8px; padding:8px 10px; border:1px solid var(--app-line); border-radius:9px; color:var(--app-ink-soft); background:#fff; cursor:pointer; text-align:left; }
.report-package-workspace__tabs button.is-active { border-color: #bfd0e2; color: #244d73; background: #edf4fb; }
.report-package-workspace__tabs button.is-complete:not(.is-active) { border-color:#cfe4da; background:#f5faf7; }
.report-package-workspace__tab-index { display:grid; width:25px; height:25px; place-items:center; border-radius:999px; color:#fff; background:#718397; font-size:9px; font-weight:900; }
.report-package-workspace__tabs button.is-active .report-package-workspace__tab-index { background:#2e5984; }
.report-package-workspace__tabs button.is-complete .report-package-workspace__tab-index { background:#3c8368; }
.report-package-workspace__tab-copy { display:grid; gap:2px; min-width:0; }
.report-package-workspace__tab-copy strong { color:var(--app-ink); font-size:10px; line-height:1.35; }
.report-package-workspace__tab-copy small { color:var(--app-muted); font-size:8px; font-weight:700; }
.report-package-workspace__notice { margin: 0; padding: 10px 12px; border-radius: 8px; color: #2e5984; background: #edf4fb; font-size: 12px; line-height: 1.6; }
.report-package-workspace__active-confirmation { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:start; gap:10px; padding:12px 13px; border:1px solid #d9e2eb; border-radius:9px; color:var(--app-ink); background:#fbfcfe; cursor:pointer; }
.report-package-workspace__active-confirmation[data-checked="true"] { border-color:#c9e0d4; color:#2f7456; background:#f3f9f6; }
.report-package-workspace__active-confirmation input { margin-top:3px; accent-color:var(--app-accent); }
.report-package-workspace__active-confirmation > span { display:grid; gap:3px; }
.report-package-workspace__active-confirmation strong { color:var(--app-ink); font-size:11px; }
.report-package-workspace__active-confirmation small { color:var(--app-muted); font-size:9px; line-height:1.5; }
.report-package-workspace__actions { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:10px; padding-top:2px; }
.report-package-workspace__actions button.is-primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }

@media (max-width: 980px) {
  .report-package-workspace__tabs button { flex-basis: 220px; }
}

@media (max-width: 760px) {
  .report-package-workspace { padding: 16px; }
  .report-package-workspace__heading { flex-direction: column; }
  .report-package-workspace__button,
  .report-package-workspace__actions button { width: 100%; }
  .report-package-workspace__actions { flex-direction: column; }
  .report-package-workspace__active-confirmation { grid-template-columns:auto minmax(0,1fr); }
  .report-package-workspace__active-confirmation > svg { display:none; }
}
</style>
