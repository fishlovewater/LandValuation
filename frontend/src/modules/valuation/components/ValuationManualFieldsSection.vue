<script setup lang="ts">
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

function handleFormChange(event: Event): void {
  emit('updateActiveForm', (event.target as HTMLSelectElement).value as FieldAnalysisFormCode)
}

function handleValueInput(key: string, event: Event): void {
  emit('updateValue', key, (event.target as HTMLInputElement).value)
}
</script>

<template>
  <section
    v-if="props.entries.length"
    class="manual-fields"
    data-testid="manual-field-workspace"
    aria-labelledby="manual-fields-title"
  >
    <div class="manual-fields__heading">
      <div>
        <p class="manual-fields__eyebrow">人工補充</p>
        <h2 id="manual-fields-title">補齊未辨識到的欄位</h2>
      </div>
      <span class="manual-fields__count">{{ props.entries.length }} 項</span>
    </div>

    <p class="manual-fields__intro">
      只會送出非空欄位。一般欄位可在這裡人工補值；像「比準地」這種關聯資料則必須從既有資料中選擇，不需要另外填寫系統識別資料。
    </p>

    <label class="manual-fields__selector">
      <span>選擇要補填的表單</span>
      <select :value="props.activeForm" data-testid="manual-form-selector" @change="handleFormChange">
        <option value="F01">F01－買賣實例調查估價表</option>
        <option value="F02">F02－比較法調查估價表</option>
        <option value="F02-RF">F02-RF－影響地價區域因素分析明細表</option>
        <option value="F03">F03－比準地地價估計表</option>
        <option value="F04">F04－徵收土地宗地市價估計表</option>
        <option value="S01">S01－地價區段勘查表</option>
      </select>
    </label>

    <div class="manual-fields__grid">
      <template v-for="entry in props.entries" :key="entry.key">
        <div
          v-if="entry.formCode === 'F03' && entry.fieldName === 'benchmark_land_id'"
          class="manual-fields__relation"
          data-testid="manual-benchmark-helper"
        >
          <div>
            <strong>比準地地價估計表 → 比準地</strong>
            <span>比準地是本案已建立資料的關聯，不是文字欄位。請先在「宗地與比準地」建立或選擇，再回到比準地地價估計表確認正式採用值。</span>
          </div>
          <button class="manual-fields__link" type="button" @click="emit('goLand')">前往宗地與比準地</button>
        </div>

        <label v-else>
          <span>{{ props.fieldMetadata(entry.formCode, entry.fieldName).label }}</span>
          <input
            :value="props.values[entry.key] ?? ''"
            :data-testid="`manual-field-${entry.formCode}-${entry.fieldName}`"
            :type="props.fieldMetadata(entry.formCode, entry.fieldName).inputType ?? 'text'"
            :placeholder="`請填寫：${props.fieldMetadata(entry.formCode, entry.fieldName).label}`"
            autocomplete="off"
            @input="handleValueInput(entry.key, $event)"
          >
          <small class="manual-fields__hint">
            主要填寫：{{ props.fieldMetadata(entry.formCode, entry.fieldName).guidance }}
          </small>
          <small v-if="props.errors[entry.key]" class="manual-fields__error">
            {{ props.errors[entry.key] }}
          </small>
        </label>
      </template>
    </div>

    <div class="manual-fields__footer">
      <span>人工輸入會覆蓋先前同欄位的人工值，並使相關比準地地價估計表單表與送審文件需要重新計算／檢核。</span>
      <button
        v-if="props.editableCount"
        class="manual-fields__save"
        type="button"
        data-testid="save-manual-fields"
        :disabled="props.saving"
        @click="emit('save')"
      >
        {{ props.saving ? '儲存中…' : '儲存人工補充資料' }}
      </button>
    </div>
  </section>

  <section v-else class="manual-fields__empty">
    <strong>目前沒有需要人工補充的欄位</strong>
    <span>智能辨識與既有資料已提供目前可確認的欄位；你可以直接前往宗地與比準地或比準地地價估計表。</span>
  </section>
</template>

<style scoped>
.manual-fields,
.manual-fields__empty {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-paper-strong);
}

.manual-fields {
  border-color: rgba(59, 129, 102, .2);
}

.manual-fields__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.manual-fields__heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -.04em;
}

.manual-fields__eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}

.manual-fields__count {
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

.manual-fields__intro {
  margin: -4px 0 14px;
  color: var(--app-ink-soft);
  font-size: 12px;
  line-height: 1.65;
}

.manual-fields__selector {
  display: grid;
  gap: 6px;
  max-width: 390px;
  margin: 0 0 14px;
  color: var(--app-ink-soft);
  font-size: 11px;
  font-weight: 800;
}

.manual-fields__selector select,
.manual-fields__grid input {
  min-height: 42px;
  padding: 8px 10px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  font: inherit;
}

.manual-fields__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.manual-fields__grid label {
  display: grid;
  gap: 5px;
  color: var(--app-ink-soft);
  font-size: 11px;
  font-weight: 800;
}

.manual-fields__relation {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 13px;
  border: 1px solid rgba(46, 89, 132, .2);
  border-radius: 9px;
  background: #f6faff;
}

.manual-fields__relation > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.manual-fields__relation strong {
  color: var(--app-ink);
  font-size: 12px;
}

.manual-fields__relation span,
.manual-fields__hint {
  color: var(--app-muted);
  font-size: 10px;
  font-weight: 500;
  line-height: 1.55;
}

.manual-fields__error {
  color: #a44334;
  font-size: 10px;
  line-height: 1.5;
}

.manual-fields__link {
  flex: 0 0 auto;
  min-height: 36px;
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 14px;
}

.manual-fields__footer > span {
  color: var(--app-muted);
  font-size: 11px;
}

.manual-fields__save {
  min-height: 44px;
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
  display: grid;
  gap: 5px;
  color: var(--app-muted);
  font-size: 12px;
}

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
