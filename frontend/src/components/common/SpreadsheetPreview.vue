<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { SpreadsheetPreviewDto, SpreadsheetPreviewSheetDto } from '../../types/spreadsheet'

const props = defineProps<{
  preview: SpreadsheetPreviewDto
}>()

const activeSheetIndex = ref(0)

watch(
  () => props.preview.sheets,
  () => { activeSheetIndex.value = 0 },
)

const activeSheet = computed<SpreadsheetPreviewSheetDto | null>(() => (
  props.preview.sheets[activeSheetIndex.value] ?? null
))

function cellText(value: string | number | boolean | null): string {
  if (value === null || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}
</script>

<template>
  <div class="spreadsheet-preview" data-testid="spreadsheet-preview">
    <div v-if="preview.sheets.length > 1" class="spreadsheet-preview__tabs" role="tablist" aria-label="Excel 工作表">
      <button
        v-for="(sheet, index) in preview.sheets"
        :key="`${sheet.name}-${index}`"
        type="button"
        role="tab"
        :aria-selected="activeSheetIndex === index ? 'true' : 'false'"
        :class="{ 'is-active': activeSheetIndex === index }"
        @click="activeSheetIndex = index"
      >{{ sheet.name }}</button>
    </div>

    <div v-if="activeSheet" class="spreadsheet-preview__meta">
      <strong>{{ activeSheet.name }}</strong>
      <span>{{ activeSheet.total_rows }} 列 × {{ activeSheet.total_columns }} 欄</span>
      <span v-if="activeSheet.truncated">僅顯示前段資料，完整內容請下載文件。</span>
    </div>

    <div v-if="activeSheet?.rows.length" class="spreadsheet-preview__table-wrap">
      <table>
        <tbody>
          <tr v-for="(row, rowIndex) in activeSheet.rows" :key="rowIndex">
            <th class="spreadsheet-preview__row-number" scope="row">{{ rowIndex + 1 }}</th>
            <td v-for="(cell, columnIndex) in row" :key="columnIndex">{{ cellText(cell) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="spreadsheet-preview__empty">這個工作表目前沒有可顯示的儲存格內容。</p>
  </div>
</template>

<style scoped>
.spreadsheet-preview { display:grid; min-width:0; gap:10px; }
.spreadsheet-preview__tabs { display:flex; flex-wrap:wrap; gap:6px; }
.spreadsheet-preview__tabs button { min-height:38px; padding:7px 11px; border:1px solid var(--app-line); border-radius:8px; color:var(--app-ink-soft); background:#fff; cursor:pointer; font-size:11px; font-weight:800; }
.spreadsheet-preview__tabs button:hover,
.spreadsheet-preview__tabs button.is-active { border-color:var(--app-primary); color:var(--app-primary-deep); background:var(--app-primary-soft); }
.spreadsheet-preview__meta { display:flex; flex-wrap:wrap; gap:6px 12px; color:var(--app-muted); font-size:11px; }
.spreadsheet-preview__meta strong { color:var(--app-ink); }
.spreadsheet-preview__table-wrap { max-height:560px; overflow:auto; border:1px solid var(--app-line); border-radius:10px; background:#fff; }
.spreadsheet-preview table { border-collapse:separate; border-spacing:0; min-width:100%; font-size:11px; }
.spreadsheet-preview td,
.spreadsheet-preview th { min-width:110px; max-width:280px; padding:8px 10px; border-right:1px solid #e8edf3; border-bottom:1px solid #e8edf3; overflow-wrap:anywhere; vertical-align:top; }
.spreadsheet-preview td { color:var(--app-ink-soft); background:#fff; }
.spreadsheet-preview tr:first-child td { position:sticky; top:0; z-index:1; color:var(--app-ink); background:#f1f5f9; font-weight:800; }
.spreadsheet-preview__row-number { position:sticky; left:0; z-index:2; min-width:46px !important; width:46px; color:var(--app-muted); background:#f8fafc; text-align:right; font-weight:700; }
.spreadsheet-preview tr:first-child .spreadsheet-preview__row-number { z-index:3; }
.spreadsheet-preview__empty { margin:0; padding:24px; color:var(--app-muted); text-align:center; font-size:12px; }
</style>
