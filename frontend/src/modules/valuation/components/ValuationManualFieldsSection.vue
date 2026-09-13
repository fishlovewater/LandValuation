<script setup lang="ts">
import { computed } from 'vue'
import {
  PhCheckCircle as CheckCircle,
  PhClipboardText as ClipboardText,
  PhFloppyDisk as FloppyDisk,
  PhInfo as Info,
  PhPencilSimple as PencilSimple,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
type FieldAnalysisFormCode = 'S01' | 'F01' | 'F02' | 'F02-RF' | 'F03' | 'F04'
type ManualFieldEntry = { key: string; formCode: string; fieldName: string }
type ManualFieldMetadata = { label: string; guidance: string; inputType?: 'date' | 'text' }

const props = defineProps<{
  activeForm: FieldAnalysisFormCode
  entries: ManualFieldEntry[]
  editableCount: number
  values: Record<string, string>
  errors: Record<string, string>
  saving: boolean
  fieldMetadata: (formCode: string, fieldName: string) => ManualFieldMetadata
}>()

const emit = defineEmits<{
  updateActiveForm: [formCode: FieldAnalysisFormCode]
  updateValue: [key: string, value: string]
  goLand: []
  save: []
}>()

const SYSTEM_MANAGED_FIELDS = new Set([
  'F01.accumulated_depreciation_raw',
  'F01.building_cost_total_raw',
  'F01.calculation_building_area',
  'F01.capital_interest_rate_raw',
  'F01.cost_components_raw',
  'F01.elapsed_years_raw',
  'F01.land_price_raw',
  'F01.normal_land_total_price',
  'F01.normal_land_unit_price',
  'F01.normal_land_unit_price_raw',
  'F01.normal_total_price_raw',
  'F02.absolute_adjustment_total',
  'F02.adjusted_unit_price_display',
  'F02.adjusted_unit_price_raw',
  'F02.benchmark_land_no',
  'F02.benchmark_comparison_price',
  'F02.benchmark_comparison_price_raw',
  'F02.date_adjustment_rate',
  'F02.individual_factor_rate',
  'F02.individual_factor_total',
  'F02.normal_land_unit_price',
  'F02.regional_factor_rate',
  'F02.regional_adjustment_rate',
  'F02.time_adjustment_rate',
  'F02.trial_price',
  'F02.trial_price_raw',
  'F02-RF.comparison_analysis_id',
  'F02-RF.comparison_targets',
  'F02-RF.rule_version_id',
  'F03.benchmark_land_price',
  'F03.comparison_price',
  'F03.comparison_price_raw',
  'F03.weight_total',
  'F03.weighted_value_raw',
  'F04.parcel_market_price',
  'F04.rule_version_id',
  'F04.total_adjustment_rate_raw',
  'F04.trial_price_raw',
  'S01.average_internal_road_width_m',
  'F02.parcel_id',
  'F02-RF.benchmark_land_id',
  'F03.benchmark_land_id',
  'F04.benchmark_valuation_id',
])

function isSystemManagedField(entry: ManualFieldEntry): boolean {
  return SYSTEM_MANAGED_FIELDS.has(`${entry.formCode}.${entry.fieldName}`)
}

const displayEntries = computed(() => props.entries.filter((entry) => !isSystemManagedField(entry)))
const activeEntries = computed(() => displayEntries.value.filter(
  (entry) => entry.formCode === props.activeForm,
))
const completedCount = computed(() => activeEntries.value.filter((entry) => {
  return Boolean((props.values[entry.key] ?? '').trim())
}).length)

function handleFormChange(event: Event): void {
  emit('updateActiveForm', (event.target as HTMLSelectElement).value as FieldAnalysisFormCode)
}

function handleValueInput(key: string, event: Event): void {
  emit('updateValue', key, (event.target as HTMLInputElement).value)
}
</script>

<template>
  <section
    v-if="displayEntries.length"
    class="manual-fields"
    data-testid="manual-field-workspace"
    aria-labelledby="manual-fields-title"
  >
    <div class="manual-fields__heading">
      <div class="manual-fields__title-group">
        <span class="manual-fields__title-icon" aria-hidden="true">
          <ClipboardText :size="22" weight="duotone" />
        </span>
        <div>
          <p class="manual-fields__eyebrow">人工補充</p>
          <h2 id="manual-fields-title">可補充正式欄位</h2>
          <span>只顯示 AI 未取得或被拒絕的欄位；空白欄位可以直接略過。</span>
        </div>
      </div>
      <div class="manual-fields__stats" aria-label="人工補充狀態">
        <span>{{ activeEntries.length }} 項欄位</span>
        <span>{{ completedCount }} 項已填</span>
      </div>
    </div>

    <div class="manual-fields__control-bar">
      <label class="manual-fields__selector">
        <span>目前補填表單</span>
        <select :value="props.activeForm" data-testid="manual-form-selector" @change="handleFormChange">
          <option value="F01">F01－買賣實例調查估價表</option>
          <option value="F02">F02－比較法調查估價表</option>
          <option value="F02-RF">F02-RF－影響地價區域因素分析明細表</option>
          <option value="F03">F03－比準地地價估計表</option>
          <option value="F04">F04－徵收土地宗地市價估計表</option>
          <option value="S01">S01－地價區段勘查表</option>
        </select>
      </label>
      <div class="manual-fields__notice">
        <Info :size="17" weight="duotone" aria-hidden="true" />
        <span>只會送出非空欄位；未填欄位保留空白，不會阻擋後續流程。</span>
      </div>
    </div>

    <div class="manual-fields__grid">
      <label v-for="entry in activeEntries" :key="entry.key" class="manual-field-card" :data-error="Boolean(props.errors[entry.key])">
          <span class="manual-field-card__heading">
            <span class="manual-field-card__label">
              <PencilSimple :size="14" weight="duotone" aria-hidden="true" />
              {{ props.fieldMetadata(entry.formCode, entry.fieldName).label }}
            </span>
            <span v-if="(props.values[entry.key] ?? '').trim()" class="manual-field-card__filled">
              <CheckCircle :size="13" weight="fill" aria-hidden="true" />
              已填寫
            </span>
          </span>
          <input
            :value="props.values[entry.key] ?? ''"
            :data-testid="`manual-field-${entry.formCode}-${entry.fieldName}`"
            :type="props.fieldMetadata(entry.formCode, entry.fieldName).inputType ?? 'text'"
            :placeholder="`請填寫：${props.fieldMetadata(entry.formCode, entry.fieldName).label}`"
            autocomplete="off"
            @input="handleValueInput(entry.key, $event)"
          >
          <small class="manual-fields__hint">
            {{ props.fieldMetadata(entry.formCode, entry.fieldName).guidance }}
          </small>
          <small v-if="props.errors[entry.key]" class="manual-fields__error">
            <WarningCircle :size="13" weight="fill" aria-hidden="true" />
            {{ props.errors[entry.key] }}
          </small>
      </label>
      <p v-if="!activeEntries.length" class="manual-fields__empty-form">
        此表單目前沒有需要人工補充的欄位，可切換其他表單查看。
      </p>
    </div>

    <div class="manual-fields__footer">
      <div class="manual-fields__footer-copy">
        <strong>儲存後會重新整理相關資料</strong>
        <span>人工輸入會更新同欄位先前的人工值；沒有填寫的欄位會維持空白。</span>
      </div>
      <button
        v-if="props.editableCount"
        class="manual-fields__save"
        type="button"
        data-testid="save-manual-fields"
        :disabled="props.saving"
        @click="emit('save')"
      >
        <FloppyDisk v-if="!props.saving" :size="16" weight="bold" aria-hidden="true" />
        {{ props.saving ? '儲存中…' : '儲存人工補充資料' }}
      </button>
    </div>
  </section>

  <section v-else class="manual-fields__empty">
    <CheckCircle :size="22" weight="duotone" aria-hidden="true" />
    <div>
      <strong>目前沒有需要人工補充的欄位</strong>
      <span>智能辨識與既有資料已提供目前可確認的欄位；可以繼續處理宗地與比準地或比準地地價估計表。</span>
    </div>
  </section>
</template>

<style scoped>
.manual-fields,
.manual-fields__empty {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: #fff;
}

.manual-fields__heading,
.manual-fields__title-group,
.manual-fields__stats,
.manual-fields__notice,
.manual-fields__relation,
.manual-fields__link,
.manual-field-card__heading,
.manual-field-card__label,
.manual-field-card__filled,
.manual-fields__error,
.manual-fields__footer,
.manual-fields__save,
.manual-fields__empty {
  display: flex;
  align-items: center;
}

.manual-fields__heading {
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.manual-fields__title-group { align-items: flex-start; gap: 11px; }
.manual-fields__title-icon {
  display: grid;
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 10px;
  color: var(--app-accent-deep);
  background: #edf4fb;
}

.manual-fields__heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 23px;
  font-weight: 650;
  letter-spacing: -.035em;
}

.manual-fields__title-group > div > span {
  display: block;
  margin-top: 5px;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.5;
}

.manual-fields__eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}

.manual-fields__stats { flex-wrap: wrap; justify-content: flex-end; gap: 7px; }
.manual-fields__stats span {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  padding: 5px 9px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-pill);
  color: var(--app-ink-soft);
  background: #f7f9fc;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.manual-fields__control-bar {
  display: grid;
  grid-template-columns: minmax(260px, 390px) minmax(0, 1fr);
  align-items: end;
  gap: 12px;
  margin-bottom: 14px;
}

.manual-fields__selector {
  display: grid;
  gap: 6px;
  color: var(--app-ink-soft);
  font-size: 11px;
  font-weight: 800;
}

.manual-fields__notice {
  min-height: 42px;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 11px;
  border: 1px solid #dbe5ef;
  border-radius: 8px;
  color: #486075;
  background: #f6f9fc;
  font-size: 10px;
  line-height: 1.55;
}
.manual-fields__notice svg { flex: 0 0 auto; margin-top: 1px; color: var(--app-accent-deep); }

.manual-fields__selector select,
.manual-fields__grid input {
  min-height: 42px;
  padding: 8px 10px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  font: inherit;
  outline: none;
}
.manual-fields__selector select:focus,
.manual-fields__grid input:focus { border-color: rgba(46, 89, 132, .48); box-shadow: 0 0 0 3px rgba(46, 89, 132, .08); }

.manual-fields__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.manual-fields__empty-form {
  grid-column: 1 / -1;
  margin: 0;
  padding: 14px;
  border: 1px dashed var(--app-line);
  border-radius: 8px;
  color: var(--app-muted);
  font-size: 12px;
}

.manual-field-card {
  display: grid;
  gap: 7px;
  padding: 12px;
  border: 1px solid #edf0f4;
  border-radius: 9px;
  color: var(--app-ink-soft);
  background: #fbfcfe;
  font-size: 11px;
  font-weight: 800;
}
.manual-field-card[data-error="true"] { border-color: rgba(164, 67, 52, .32); background: #fff8f6; }
.manual-field-card__heading { justify-content: space-between; gap: 10px; }
.manual-field-card__label { min-width: 0; gap: 6px; color: var(--app-ink); }
.manual-field-card__label svg { flex: 0 0 auto; color: var(--app-accent-deep); }
.manual-field-card__filled { flex: 0 0 auto; gap: 4px; color: #2f7456; font-size: 9px; font-weight: 850; white-space: nowrap; }

.manual-fields__relation {
  grid-column: 1 / -1;
  justify-content: space-between;
  gap: 14px;
  padding: 13px;
  border: 1px solid rgba(46, 89, 132, .2);
  border-radius: 9px;
  background: #f6faff;
}

.manual-fields__relation-icon {
  display: grid;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 8px;
  color: var(--app-accent-deep);
  background: #e9f2fb;
}

.manual-fields__relation-copy {
  display: grid;
  gap: 4px;
  flex: 1 1 auto;
  min-width: 0;
}

.manual-fields__relation-copy strong {
  color: var(--app-ink);
  font-size: 12px;
}

.manual-fields__relation-copy span,
.manual-fields__hint {
  color: var(--app-muted);
  font-size: 10px;
  font-weight: 500;
  line-height: 1.55;
}

.manual-fields__error {
  align-items: flex-start;
  gap: 5px;
  color: #a44334;
  font-size: 10px;
  line-height: 1.5;
}
.manual-fields__error svg { flex: 0 0 auto; margin-top: 1px; }

.manual-fields__link {
  flex: 0 0 auto;
  min-height: 36px;
  justify-content: center;
  gap: 5px;
  padding: 6px 11px;
  border: 1px solid rgba(46, 89, 132, .28);
  border-radius: 8px;
  color: #244d73;
  background: #fff;
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

.manual-fields__footer {
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--app-line);
}

.manual-fields__footer-copy { display: grid; gap: 3px; }
.manual-fields__footer-copy strong { color: var(--app-ink); font-size: 11px; }
.manual-fields__footer-copy span {
  color: var(--app-muted);
  font-size: 10px;
  line-height: 1.5;
}

.manual-fields__save {
  flex: 0 0 auto;
  min-height: 44px;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  border: 1px solid var(--app-accent);
  border-radius: 9px;
  color: #fff;
  background: var(--app-accent);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}

.manual-fields__save:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.manual-fields__empty {
  gap: 10px;
  color: var(--app-muted);
  font-size: 12px;
}
.manual-fields__empty > svg { flex: 0 0 auto; color: var(--app-green); }
.manual-fields__empty > div { display: grid; gap: 4px; }

.manual-fields__empty strong {
  color: var(--app-green);
  font-size: 14px;
}

@media (max-width: 760px) {
  .manual-fields,
  .manual-fields__empty {
    padding: 16px;
  }

  .manual-fields__heading,
  .manual-fields__relation,
  .manual-fields__footer {
    align-items: stretch;
    flex-direction: column;
  }

  .manual-fields__control-bar { grid-template-columns: 1fr; }
  .manual-fields__stats { justify-content: flex-start; }
  .manual-fields__relation-icon { display: none; }

  .manual-fields__grid {
    grid-template-columns: 1fr;
  }

  .manual-fields__relation {
    grid-column: auto;
  }

  .manual-fields__save {
    width: 100%;
  }
}
</style>
