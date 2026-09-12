<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  PhArrowCounterClockwise as ArrowCounterClockwise,
  PhBracketsCurly as BracketsCurly,
  PhCheckCircle as CheckCircle,
  PhFileText as FileText,
  PhFloppyDisk as FloppyDisk,
  PhInfo as Info,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import { userStructuredValue } from '../../../utils/fieldLabels'
import type { ReportPageCode, ReportPageResponseDto } from '../valuation.types'

type FieldKind = 'text' | 'textarea' | 'date' | 'number' | 'json'

interface FieldDefinition {
  key: string
  label: string
  kind: FieldKind
  help?: string
}

const props = withDefaults(defineProps<{
  page: ReportPageResponseDto
  saving?: boolean
}>(), {
  saving: false,
})

const emit = defineEmits<{
  save: [value: { pageCode: ReportPageCode; payload: Record<string, unknown> }]
}>()

const fieldDefinitions: Readonly<Record<ReportPageCode, readonly FieldDefinition[]>> = {
  S01: [
    { key: 'district_name', label: '勘查地區名稱', kind: 'text' },
    { key: 'district_boundary', label: '勘查範圍／界線', kind: 'textarea' },
    { key: 'survey_date', label: '勘查日期', kind: 'date' },
    { key: 'urban_plan_status', label: '都市計畫（內、外）', kind: 'text' },
    { key: 'land_use_zone', label: '使用分區（使用地類別）', kind: 'text' },
    { key: 'building_coverage_rate', label: '建蔽率', kind: 'number' },
    { key: 'floor_area_ratio', label: '容積率', kind: 'number' },
    { key: 'prohibited_building', label: '有無禁止建築', kind: 'textarea' },
    { key: 'restricted_building', label: '有無限制建築（整體開發、面積限制、高度限制……等）', kind: 'textarea' },
    { key: 'main_road_name', label: '主要道路名稱', kind: 'text' },
    { key: 'main_road_width_m', label: '主要道路寬度（m）', kind: 'number' },
    { key: 'average_road_width_m', label: '區段內道路平均寬度（m）', kind: 'number' },
    {
      key: 'observations',
      label: '勘查觀察項目',
      kind: 'json',
      help: '可修改觀察值與來源資料；儲存前系統會檢查內容格式。',
    },
    { key: 'notes', label: '備註', kind: 'textarea' },
    { key: 'site_opinion', label: '現場意見', kind: 'textarea' },
    { key: 'handler_name', label: '承辦員', kind: 'text' },
    { key: 'section_head_name', label: '課（股）長', kind: 'text' },
    { key: 'director_name', label: '主任（局、處長）', kind: 'text' },
    { key: 'appraiser_name', label: '不動產估價師', kind: 'text' },
  ],
  'F02-RF': [
    {
      key: 'factor_rows',
      label: '區域因素級距',
      kind: 'json',
      help: '可修正各因素的填報值、確認值、來源說明與人工確認狀態；系統計算出的調整率不會由此欄位覆寫。',
    },
    { key: 'other_influences', label: '其他影響因素', kind: 'textarea' },
    { key: 'notes', label: '備註', kind: 'textarea' },
    { key: 'appraiser_name', label: '不動產估價師', kind: 'text' },
  ],
  F02: [
    { key: 'benchmark_notes', label: '比準地說明', kind: 'textarea' },
    { key: 'notes', label: '備註', kind: 'textarea' },
    { key: 'handler_name', label: '承辦員', kind: 'text' },
    { key: 'section_head_name', label: '課（股）長', kind: 'text' },
    { key: 'director_name', label: '主任（局、處長）', kind: 'text' },
    { key: 'appraiser_name', label: '不動產估價師', kind: 'text' },
  ],
}

const drafts = reactive<Record<string, string>>({})
const error = ref('')
const dirty = ref(false)
const fields = computed(() => fieldDefinitions[props.page.page_code])
const pageLabel = computed(() => ({
  S01: '地價區段勘查表',
  'F02-RF': '影響地價區域因素分析明細表（商業用地）',
  F02: '比較法調查估價表',
} as const)[props.page.page_code])

function formStatusLabel(status: string): string {
  const labels: Readonly<Record<string, string>> = {
    DRAFT: '草稿',
    READY: '已就緒',
    CHECKED: '已檢核',
    FINAL: '已完成',
    VOID: '已作廢',
  }
  return labels[status] ?? '狀態待確認'
}

function stringifyValue(value: unknown, kind: FieldKind): string {
  if (kind === 'json') return JSON.stringify(value ?? [], null, 2)
  if (value === null || value === undefined) return ''
  return String(value)
}

function structuredDraftSummary(fieldKey: string): string {
  try {
    return userStructuredValue(JSON.parse(drafts[fieldKey] || '[]'))
  } catch {
    return '內容格式待確認'
  }
}

function resetDraft(): void {
  for (const key of Object.keys(drafts)) delete drafts[key]
  for (const field of fields.value) {
    drafts[field.key] = stringifyValue(props.page.data[field.key], field.kind)
  }
  error.value = ''
  dirty.value = false
}

function stripServerCalculatedFields(pageCode: ReportPageCode, fieldKey: string, value: unknown): unknown {
  if (pageCode === 'F02-RF' && fieldKey === 'factor_rows' && Array.isArray(value)) {
    return value.map((row) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return row
      const next = { ...(row as Record<string, unknown>) }
      if (Array.isArray(next.targets)) {
        next.targets = next.targets.map((target) => {
          if (!target || typeof target !== 'object' || Array.isArray(target)) return target
          const clean = { ...(target as Record<string, unknown>) }
          delete clean.calculated_adjustment_rate
          return clean
        })
      }
      return next
    })
  }
  return value
}

function parseField(field: FieldDefinition): unknown {
  const raw = drafts[field.key] ?? ''
  if (field.kind === 'json') {
    try {
      return stripServerCalculatedFields(props.page.page_code, field.key, JSON.parse(raw))
    } catch {
      throw new Error(`${field.label}的內容格式不正確，請先修正。`)
    }
  }
  if (field.kind === 'number') {
    if (!raw.trim()) return null
    const value = Number(raw)
    if (!Number.isFinite(value)) throw new Error(`${field.label}必須是有效數字。`)
    return value
  }
  if (field.kind === 'date') return raw.trim() || null
  const original = props.page.data[field.key]
  if (!raw.trim() && original === null) return null
  return raw
}

function save(): void {
  if (props.saving) return
  try {
    const payload = Object.fromEntries(fields.value.map((field) => [field.key, parseField(field)]))
    error.value = ''
    emit('save', { pageCode: props.page.page_code, payload })
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '表單內容格式錯誤，請重新確認。'
  }
}

watch(() => [props.page.page_code, props.page.version_no, props.page.data] as const, resetDraft, { immediate: true, deep: true })
</script>

<template>
  <section class="report-page-editor" :data-page-code="page.page_code" :aria-labelledby="`report-editor-${page.page_code}`">
    <header class="report-page-editor__header">
      <div class="report-page-editor__title">
        <span class="report-page-editor__title-icon" aria-hidden="true">
          <FileText :size="20" weight="duotone" />
        </span>
        <div>
          <p>{{ pageLabel }}編輯</p>
          <h3 :id="`report-editor-${page.page_code}`">{{ pageLabel }}可修改資料</h3>
          <span>只修改人工填寫內容；正式計算值仍由系統產生。</span>
        </div>
      </div>
      <div class="report-page-editor__header-actions">
        <span class="report-page-editor__version" :data-status="page.form_status">
          第 {{ page.version_no }} 版 · {{ formStatusLabel(page.form_status) }}
        </span>
        <button type="button" :disabled="saving || !dirty" @click="resetDraft">
          <ArrowCounterClockwise :size="15" weight="bold" aria-hidden="true" />
          <span>還原本頁</span>
        </button>
      </div>
    </header>

    <div class="report-page-editor__note">
      <Info :size="16" weight="duotone" aria-hidden="true" />
      <div>
        <strong>人工欄位可修改</strong>
        <span>正式計算結果、調整率與價格屬於系統計算結果，不會由這裡的人工輸入覆寫。</span>
      </div>
    </div>

    <div class="report-page-editor__grid">
      <label v-for="field in fields" :key="field.key" :class="{ 'is-wide': field.kind === 'textarea' || field.kind === 'json' }">
        <span>{{ field.label }}</span>
        <small v-if="field.help">{{ field.help }}</small>
        <div v-if="field.kind === 'json'" class="report-page-editor__structured">
          <div class="report-page-editor__structured-summary">
            <BracketsCurly :size="16" weight="duotone" aria-hidden="true" />
            <span><strong>結構化內容摘要</strong><small>{{ structuredDraftSummary(field.key) }}</small></span>
          </div>
          <details>
            <summary>進階資料編輯</summary>
            <p>一般情況不需要直接修改資料結構；只有在確認內容來源與格式時才需要展開。</p>
            <textarea
              :id="`report-field-${page.page_code}-${field.key}`"
              v-model="drafts[field.key]"
              :data-report-field="field.key"
              :rows="12"
              :spellcheck="false"
              @input="dirty = true"
            />
          </details>
        </div>
        <textarea
          v-else-if="field.kind === 'textarea'"
          :id="`report-field-${page.page_code}-${field.key}`"
          v-model="drafts[field.key]"
          :data-report-field="field.key"
          :rows="3"
          @input="dirty = true"
        />
        <input
          v-else
          :id="`report-field-${page.page_code}-${field.key}`"
          v-model="drafts[field.key]"
          :data-report-field="field.key"
          :type="field.kind === 'date' ? 'date' : 'text'"
          :inputmode="field.kind === 'number' ? 'decimal' : undefined"
          @input="dirty = true"
        />
      </label>
    </div>

    <div v-if="error" class="report-page-editor__error" role="alert">
      <WarningCircle :size="16" weight="fill" aria-hidden="true" />
      <span>{{ error }}</span>
    </div>
    <footer class="report-page-editor__actions" :data-state="dirty ? 'dirty' : 'saved'">
      <div>
        <WarningCircle v-if="dirty" :size="17" weight="fill" aria-hidden="true" />
        <CheckCircle v-else :size="17" weight="fill" aria-hidden="true" />
        <span>
          <strong>{{ dirty ? '有尚未儲存的修改' : '目前內容已儲存' }}</strong>
          <small>{{ dirty ? '儲存後才會成為目前查估書草稿的一部分。' : '可以繼續檢視其他頁面或進行後續確認。' }}</small>
        </span>
      </div>
      <button type="button" data-testid="save-report-page-editor" :disabled="saving || !dirty" @click="save">
        <FloppyDisk v-if="!saving" :size="16" weight="bold" aria-hidden="true" />
        <span>{{ saving ? '儲存中…' : '儲存本頁修改' }}</span>
      </button>
    </footer>
  </section>
</template>

<style scoped>
.report-page-editor { display: grid; gap: 14px; padding: 16px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fff; }
.report-page-editor__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.report-page-editor__title { display: flex; align-items: flex-start; gap: 10px; min-width: 0; }
.report-page-editor__title-icon { display: grid; width: 36px; height: 36px; flex: 0 0 auto; place-items: center; border-radius: 9px; color: #2e5984; background: #edf4fb; }
.report-page-editor__header p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 9px; font-weight: 900; letter-spacing: .13em; }
.report-page-editor__header h3 { margin: 0; color: var(--app-ink); font-size: 17px; }
.report-page-editor__title > div > span { display: block; margin-top: 4px; color: var(--app-muted); font-size: 11px; line-height: 1.5; }
.report-page-editor__header-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.report-page-editor__version { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 9px; border: 1px solid #dbe3eb; border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f9fb; font-size: 10px; font-weight: 800; white-space: nowrap; }
.report-page-editor__version[data-status="CHECKED"],
.report-page-editor__version[data-status="FINAL"] { border-color: #cfe4da; color: #2f7456; background: #f3f9f6; }
.report-page-editor__header button,
.report-page-editor__actions button { display: inline-flex; min-height: 38px; align-items: center; justify-content: center; gap: 6px; padding: 7px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-weight: 800; }
.report-page-editor__actions button { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.report-page-editor button:disabled { cursor: not-allowed; opacity: .5; }
.report-page-editor__note { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 10px 12px; border-radius: 8px; color: #2e5984; background: #edf4fb; font-size: 11px; line-height: 1.6; }
.report-page-editor__note > svg { flex: 0 0 auto; margin-top: 1px; }
.report-page-editor__note > div { display: grid; gap: 2px; }
.report-page-editor__note strong { color: #244d73; font-size: 11px; }
.report-page-editor__note span { color: var(--app-ink-soft); }
.report-page-editor__grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 12px; }
.report-page-editor__grid label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.report-page-editor__grid label.is-wide { grid-column: 1 / -1; }
.report-page-editor__grid small { color: var(--app-muted); font-weight: 500; line-height: 1.5; }
.report-page-editor__grid input,
.report-page-editor__grid textarea { width: 100%; min-height: 42px; padding: 9px 10px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; font: inherit; font-weight: 500; }
.report-page-editor__grid textarea { resize: vertical; line-height: 1.5; }
.report-page-editor__grid textarea[spellcheck="false"] { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }
.report-page-editor__structured { display:grid; gap:8px; }
.report-page-editor__structured-summary { display:flex; align-items:flex-start; gap:8px; padding:9px 10px; border:1px solid #e0e7ef; border-radius:8px; color:#2e5984; background:#f8fafc; }
.report-page-editor__structured-summary > svg { flex:0 0 auto; margin-top:1px; }
.report-page-editor__structured-summary > span { display:grid; gap:2px; min-width:0; }
.report-page-editor__structured-summary strong { color:var(--app-ink); font-size:10px; }
.report-page-editor__structured-summary small { color:var(--app-ink-soft); font-size:10px; font-weight:600; line-height:1.55; }
.report-page-editor__structured details { display:grid; gap:8px; }
.report-page-editor__structured summary { width:fit-content; color:var(--app-primary-deep); cursor:pointer; font-size:11px; font-weight:800; }
.report-page-editor__structured details p { margin:7px 0; color:var(--app-muted); font-size:10px; font-weight:500; line-height:1.55; }
.report-page-editor__structured details textarea { width:100%; }
.report-page-editor__grid input:focus,
.report-page-editor__grid textarea:focus { outline: 3px solid rgba(200,91,67,.15); border-color: var(--app-accent); }
.report-page-editor__error { display: flex; align-items: flex-start; gap: 7px; margin: 0; padding: 10px 12px; border: 1px solid #edc8c0; border-radius: 8px; color: #a44334; background: #fff5f3; font-size: 11px; font-weight: 700; line-height: 1.55; }
.report-page-editor__error > svg { flex: 0 0 auto; margin-top: 1px; }
.report-page-editor__actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid #e1e7ee; border-radius: 9px; background: #fafbfd; }
.report-page-editor__actions[data-state="dirty"] { border-color: #ead9b2; background: #fffaf0; }
.report-page-editor__actions[data-state="saved"] { border-color: #cfe4da; background: #f3f9f6; }
.report-page-editor__actions > div { display: flex; align-items: center; gap: 8px; color: #2f7456; }
.report-page-editor__actions[data-state="dirty"] > div { color: #8a6515; }
.report-page-editor__actions > div > span { display: grid; gap: 2px; }
.report-page-editor__actions strong { color: var(--app-ink); font-size: 11px; }
.report-page-editor__actions small { color: var(--app-muted); font-size: 9px; line-height: 1.45; }
@media (max-width: 760px) {
  .report-page-editor__header,
  .report-page-editor__actions { align-items: stretch; flex-direction: column; }
  .report-page-editor__header-actions { width: 100%; align-items: stretch; flex-direction: column; }
  .report-page-editor__version { width: fit-content; }
  .report-page-editor__grid { grid-template-columns: 1fr; }
  .report-page-editor__grid label.is-wide { grid-column: auto; }
  .report-page-editor__header button,
  .report-page-editor__actions button { width: 100%; }
}
</style>
