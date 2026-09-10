<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
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
    { key: 'urban_plan_status', label: '都市計畫狀態', kind: 'text' },
    { key: 'land_use_zone', label: '土地使用分區', kind: 'text' },
    { key: 'building_coverage_rate', label: '建蔽率', kind: 'number' },
    { key: 'floor_area_ratio', label: '容積率', kind: 'number' },
    { key: 'prohibited_building', label: '禁建情形', kind: 'textarea' },
    { key: 'restricted_building', label: '限建情形', kind: 'textarea' },
    { key: 'main_road_name', label: '主要道路名稱', kind: 'text' },
    { key: 'main_road_width_m', label: '主要道路寬度（m）', kind: 'number' },
    { key: 'average_road_width_m', label: '平均道路寬度（m）', kind: 'number' },
    {
      key: 'observations',
      label: '勘查觀察項目',
      kind: 'json',
      help: '結構化項目。可修改觀察值與來源資料；儲存前會檢查 JSON 格式。',
    },
    { key: 'notes', label: '備註', kind: 'textarea' },
    { key: 'site_opinion', label: '現場意見', kind: 'textarea' },
    { key: 'handler_name', label: '承辦人', kind: 'text' },
    { key: 'section_head_name', label: '科長／主管', kind: 'text' },
    { key: 'director_name', label: '局處長', kind: 'text' },
    { key: 'appraiser_name', label: '估價人員', kind: 'text' },
  ],
  'F02-RF': [
    { key: 'benchmark_land_id', label: '比準地 ID', kind: 'text' },
    { key: 'comparison_analysis_id', label: '比較分析 ID', kind: 'text' },
    { key: 'rule_version_id', label: '規則版本 ID', kind: 'text' },
    {
      key: 'factor_rows',
      label: '區域因素級距',
      kind: 'json',
      help: '可修正各因素的 reported / confirmed level、來源說明與人工確認狀態；伺服器計算出的調整率不會由此欄位覆寫。',
    },
    { key: 'other_influences', label: '其他影響因素', kind: 'textarea' },
    { key: 'notes', label: '備註', kind: 'textarea' },
    { key: 'appraiser_name', label: '估價人員', kind: 'text' },
  ],
  F02: [
    { key: 'benchmark_land_id', label: '比準地 ID', kind: 'text' },
    { key: 'comparison_analysis_id', label: '比較分析 ID', kind: 'text' },
    {
      key: 'comparison_targets',
      label: '比較標的、個別因素與權重',
      kind: 'json',
      help: '可修正比較標的、權重、理由與個別因素；價格與調整率等伺服器計算欄位不會由此欄位覆寫。',
    },
    { key: 'benchmark_notes', label: '比準地說明', kind: 'textarea' },
    { key: 'notes', label: '備註', kind: 'textarea' },
    { key: 'handler_name', label: '承辦人', kind: 'text' },
    { key: 'section_head_name', label: '科長／主管', kind: 'text' },
    { key: 'director_name', label: '局處長', kind: 'text' },
    { key: 'appraiser_name', label: '估價人員', kind: 'text' },
  ],
}

const drafts = reactive<Record<string, string>>({})
const error = ref('')
const dirty = ref(false)
const fields = computed(() => fieldDefinitions[props.page.page_code])

function stringifyValue(value: unknown, kind: FieldKind): string {
  if (kind === 'json') return JSON.stringify(value ?? [], null, 2)
  if (value === null || value === undefined) return ''
  return String(value)
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
  if (pageCode === 'F02' && fieldKey === 'comparison_targets' && Array.isArray(value)) {
    const calculatedKeys = [
      'regional_adjustment_rate',
      'individual_adjustment_rate',
      'total_adjustment_absolute',
      'trial_price',
      'normal_unit_price_snapshot',
      'transaction_date_snapshot',
      'date_adjusted_price',
      'regional_adjusted_price',
    ]
    return value.map((target) => {
      if (!target || typeof target !== 'object' || Array.isArray(target)) return target
      const clean = { ...(target as Record<string, unknown>) }
      for (const key of calculatedKeys) delete clean[key]
      if (Array.isArray(clean.individual_factors)) {
        clean.individual_factors = clean.individual_factors.map((factor) => {
          if (!factor || typeof factor !== 'object' || Array.isArray(factor)) return factor
          const next = { ...(factor as Record<string, unknown>) }
          delete next.calculated_adjustment_rate
          return next
        })
      }
      return clean
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
      throw new Error(`${field.label}不是有效的 JSON，請先修正格式。`)
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
      <div>
        <p>EDIT {{ page.page_code }}</p>
        <h3 :id="`report-editor-${page.page_code}`">{{ page.page_code }} 可修改資料</h3>
        <span>第 {{ page.version_no }} 版｜{{ page.form_status }}</span>
      </div>
      <button type="button" :disabled="saving || !dirty" @click="resetDraft">還原本頁</button>
    </header>

    <p class="report-page-editor__note">這裡修改的是後端 PATCH 契約允許的草稿欄位。正式計算結果、調整率與價格仍由伺服器產生。</p>

    <div class="report-page-editor__grid">
      <label v-for="field in fields" :key="field.key" :class="{ 'is-wide': field.kind === 'textarea' || field.kind === 'json' }">
        <span>{{ field.label }}</span>
        <small v-if="field.help">{{ field.help }}</small>
        <textarea
          v-if="field.kind === 'textarea' || field.kind === 'json'"
          :id="`report-field-${page.page_code}-${field.key}`"
          v-model="drafts[field.key]"
          :data-report-field="field.key"
          :rows="field.kind === 'json' ? 12 : 3"
          :spellcheck="field.kind === 'json' ? false : undefined"
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

    <p v-if="error" class="report-page-editor__error" role="alert">{{ error }}</p>
    <footer class="report-page-editor__actions">
      <span>{{ dirty ? '有尚未儲存的修改' : '目前內容已與伺服器版本同步' }}</span>
      <button type="button" data-testid="save-report-page-editor" :disabled="saving || !dirty" @click="save">
        {{ saving ? '儲存中…' : `儲存 ${page.page_code} 修改` }}
      </button>
    </footer>
  </section>
</template>

<style scoped>
.report-page-editor { display: grid; gap: 14px; padding: 16px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: rgba(255,255,255,.72); }
.report-page-editor__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.report-page-editor__header p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 9px; font-weight: 900; letter-spacing: .13em; }
.report-page-editor__header h3 { margin: 0; color: var(--app-ink); font-size: 17px; }
.report-page-editor__header span { display: block; margin-top: 4px; color: var(--app-muted); font-size: 11px; }
.report-page-editor__header button,
.report-page-editor__actions button { min-height: 38px; padding: 7px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; cursor: pointer; font-weight: 800; }
.report-page-editor__actions button { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.report-page-editor button:disabled { cursor: not-allowed; opacity: .5; }
.report-page-editor__note { margin: 0; padding: 9px 11px; border-radius: 8px; color: #2e5984; background: #edf4fb; font-size: 11px; line-height: 1.6; }
.report-page-editor__grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 12px; }
.report-page-editor__grid label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.report-page-editor__grid label.is-wide { grid-column: 1 / -1; }
.report-page-editor__grid small { color: var(--app-muted); font-weight: 500; line-height: 1.5; }
.report-page-editor__grid input,
.report-page-editor__grid textarea { width: 100%; min-height: 42px; padding: 9px 10px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; font: inherit; font-weight: 500; }
.report-page-editor__grid textarea { resize: vertical; line-height: 1.5; }
.report-page-editor__grid textarea[spellcheck="false"] { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }
.report-page-editor__grid input:focus,
.report-page-editor__grid textarea:focus { outline: 3px solid rgba(200,91,67,.15); border-color: var(--app-accent); }
.report-page-editor__error { margin: 0; color: #a44334; font-size: 12px; font-weight: 700; }
.report-page-editor__actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 12px; border-top: 1px solid var(--app-line); }
.report-page-editor__actions span { color: var(--app-muted); font-size: 11px; }
@media (max-width: 760px) {
  .report-page-editor__header,
  .report-page-editor__actions { align-items: stretch; flex-direction: column; }
  .report-page-editor__grid { grid-template-columns: 1fr; }
  .report-page-editor__grid label.is-wide { grid-column: auto; }
  .report-page-editor__header button,
  .report-page-editor__actions button { width: 100%; }
}
</style>
