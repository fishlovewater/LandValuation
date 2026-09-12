<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import {
  PhArrowClockwise as ArrowClockwise,
  PhCheckCircle as CheckCircle,
  PhChecks as Checks,
  PhInfo as Info,
  PhUploadSimple as UploadSimple,
  PhWarningCircle as WarningCircle,
  PhX as X,
} from '@phosphor-icons/vue'
import { newTaipeiDistrictName } from '../newTaipei'
import type { ParcelImportPreviewDto, ParcelImportRowDto } from '../valuation.types'

type EditableRow = {
  selected: boolean
  sourceLocation: string
  sourceSerial: string
  sourceOwnerName: string
  districtCode: string
  sectionName: string
  subsectionName: string
  landNo: string
  areaSqm: string
  landUseZone: string
  designatedUse: string
  ownershipNumerator: string
  ownershipDenominator: string
  status: string
  errors: string[]
  warnings: string[]
}

const props = defineProps<{
  preview: ParcelImportPreviewDto | null
  caseDistrictCode: string
  loading: boolean
  importing: boolean
  canImport: boolean
}>()

const emit = defineEmits<{
  import: [rows: ParcelImportRowDto[]]
}>()

const rows = reactive<EditableRow[]>([])

function validRow(row: EditableRow): boolean {
  const area = Number(row.areaSqm)
  return row.status !== 'DUPLICATE'
    && row.districtCode === props.caseDistrictCode
    && Boolean(row.sectionName.trim())
    && Boolean(row.landNo.trim())
    && Number.isFinite(area)
    && area > 0
    && ((!row.ownershipNumerator && !row.ownershipDenominator)
      || (Number(row.ownershipNumerator) > 0
        && Number(row.ownershipDenominator) > 0
        && Number(row.ownershipNumerator) <= Number(row.ownershipDenominator)))
}

function rebuildRows(): void {
  rows.splice(0, rows.length)
  for (const candidate of props.preview?.candidates ?? []) {
    rows.push({
      selected: candidate.status === 'READY',
      sourceLocation: candidate.source_location,
      sourceSerial: candidate.source_serial ?? '',
      sourceOwnerName: candidate.source_owner_name ?? '',
      districtCode: candidate.district_code ?? props.caseDistrictCode,
      sectionName: candidate.section_name ?? '',
      subsectionName: candidate.subsection_name ?? '',
      landNo: candidate.land_no ?? '',
      areaSqm: candidate.area_sqm ?? '',
      landUseZone: candidate.land_use_zone ?? '',
      designatedUse: candidate.designated_use ?? '',
      ownershipNumerator: candidate.ownership_numerator ?? '',
      ownershipDenominator: candidate.ownership_denominator ?? '',
      status: candidate.status,
      errors: candidate.errors,
      warnings: candidate.warnings,
    })
  }
}

watch(() => props.preview, rebuildRows, { immediate: true })

const selectableCount = computed(() => rows.filter(validRow).length)
const selectedRows = computed(() => rows.filter((row) => row.selected && validRow(row)))

function selectAllValid(): void {
  for (const row of rows) row.selected = validRow(row)
}

function clearSelection(): void {
  for (const row of rows) row.selected = false
}

function submit(): void {
  if (!selectedRows.value.length) return
  emit('import', selectedRows.value.map((row) => ({
    source_location: row.sourceLocation,
    source_serial: row.sourceSerial || null,
    district_code: props.caseDistrictCode,
    section_name: row.sectionName.trim(),
    subsection_name: row.subsectionName.trim(),
    land_no: row.landNo.trim(),
    area_sqm: row.areaSqm.trim(),
    land_use_zone: row.landUseZone.trim() || null,
    designated_use: row.designatedUse.trim() || null,
    ownership_numerator: row.ownershipNumerator.trim() || null,
    ownership_denominator: row.ownershipDenominator.trim() || null,
  })))
}
</script>

<template>
  <section id="parcel-import-panel" class="parcel-import" data-testid="parcel-import-panel" tabindex="-1">
    <div class="parcel-import__heading">
      <div class="parcel-import__title">
        <span class="parcel-import__title-icon" aria-hidden="true">
          <UploadSimple :size="20" weight="duotone" />
        </span>
        <div>
          <strong>宗地個別因素清冊批次匯入</strong>
          <span>系統先解析清冊，再由你確認要建立的宗地；不會直接把辨識結果寫入正式資料。</span>
        </div>
      </div>
      <span v-if="preview" class="parcel-import__layout">{{ preview.layout === 'OFFICIAL_TRANSPOSED' ? '內政部清冊格式' : '列式表格' }}</span>
    </div>

    <div v-if="loading" class="parcel-import__empty">
      <ArrowClockwise :size="17" weight="bold" aria-hidden="true" />
      <span>正在解析宗地清冊…</span>
    </div>
    <template v-else-if="preview">
      <div class="parcel-import__summary">
        <span><strong>{{ preview.candidates.length }}</strong><small>清冊總筆數</small></span>
        <span data-state="ready"><strong>{{ selectableCount }}</strong><small>可匯入</small></span>
        <span v-if="preview.needs_confirmation_count" data-state="attention"><strong>{{ preview.needs_confirmation_count }}</strong><small>原始資料待確認</small></span>
        <span v-if="preview.duplicate_count" data-state="neutral"><strong>{{ preview.duplicate_count }}</strong><small>既有宗地 {{ preview.duplicate_count }} 筆</small></span>
      </div>

      <div class="parcel-import__note">
        <Info :size="16" weight="duotone" aria-hidden="true" />
        <span>宗地流水號與所有權人名稱會保留在這個確認畫面作來源核對；正式宗地資料會建立行政區、段小段、地號、面積、使用分區／編定用途、持分及來源文件。</span>
      </div>

      <div class="parcel-import__toolbar">
        <button type="button" @click="selectAllValid">
          <Checks :size="14" weight="bold" aria-hidden="true" />
          <span>選取全部可匯入宗地</span>
        </button>
        <button type="button" @click="clearSelection">
          <X :size="14" weight="bold" aria-hidden="true" />
          <span>清除選取</span>
        </button>
        <span>已選 {{ selectedRows.length }} 筆</span>
      </div>

      <div class="parcel-import__table-wrap">
        <table>
          <thead>
            <tr>
              <th>匯入</th>
              <th>來源</th>
              <th>行政區</th>
              <th>段／小段</th>
              <th>地號</th>
              <th>面積 m²</th>
              <th>使用分區／編定用途</th>
              <th>狀態</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in rows" :key="`${row.sourceLocation}-${index}`" :data-testid="`parcel-import-row-${index}`" :data-state="row.status.toLowerCase()">
              <td>
                <input v-model="row.selected" type="checkbox" :disabled="!validRow(row) || importing" :aria-label="`匯入第 ${index + 1} 筆宗地`">
              </td>
              <td class="parcel-import__source">
                <strong>{{ row.sourceSerial || `第 ${index + 1} 筆` }}</strong>
                <span>{{ row.sourceLocation }}</span>
                <small v-if="row.sourceOwnerName">所有權人／管理人：{{ row.sourceOwnerName }}</small>
              </td>
              <td><span class="parcel-import__fixed">{{ newTaipeiDistrictName(caseDistrictCode) }}</span></td>
              <td class="parcel-import__split-fields">
                <input v-model="row.sectionName" aria-label="段名" placeholder="段名">
                <input v-model="row.subsectionName" aria-label="小段" placeholder="小段（可空白）">
              </td>
              <td><input v-model="row.landNo" aria-label="地號" placeholder="地號"></td>
              <td><input v-model="row.areaSqm" aria-label="面積" inputmode="decimal" placeholder="面積"></td>
              <td class="parcel-import__split-fields">
                <input v-model="row.landUseZone" aria-label="使用分區" placeholder="使用分區">
                <input v-model="row.designatedUse" aria-label="編定用途" placeholder="編定用途（可空白）">
              </td>
              <td class="parcel-import__status">
                <strong v-if="row.status === 'DUPLICATE'"><Info :size="13" weight="duotone" aria-hidden="true" />已存在</strong>
                <strong v-else-if="validRow(row)"><CheckCircle :size="13" weight="fill" aria-hidden="true" />可匯入</strong>
                <strong v-else><WarningCircle :size="13" weight="fill" aria-hidden="true" />待修正</strong>
                <small v-for="message in row.errors" :key="message">{{ message }}</small>
                <small v-for="message in row.warnings" :key="message" class="is-warning">{{ message }}</small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="parcel-import__actions" :data-state="selectedRows.length ? 'ready' : 'idle'">
        <div>
          <CheckCircle v-if="selectedRows.length" :size="17" weight="duotone" aria-hidden="true" />
          <Info v-else :size="17" weight="duotone" aria-hidden="true" />
          <span>
            <strong>已選 {{ selectedRows.length }} 筆可匯入宗地</strong>
            <small>只有勾選且通過基本欄位檢查的宗地才會建立；重複的段小段＋地號會由後端再次擋下。</small>
          </span>
        </div>
        <button
          class="parcel-import__submit"
          type="button"
          data-testid="parcel-import-submit"
          :disabled="!canImport || importing || !selectedRows.length"
          @click="submit"
        >
          <UploadSimple v-if="!importing" :size="15" weight="bold" aria-hidden="true" />
          <span>{{ importing ? '匯入中…' : `確認匯入 ${selectedRows.length} 筆` }}</span>
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.parcel-import{display:grid;gap:12px;margin-top:14px;padding:14px;border:1px solid #d6e3ef;border-radius:14px;background:#f8fbfe}.parcel-import__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.parcel-import__title{display:flex;align-items:flex-start;gap:9px;min-width:0}.parcel-import__title-icon{display:grid;width:36px;height:36px;flex:0 0 auto;place-items:center;border-radius:9px;color:#2e5984;background:#eaf2fa}.parcel-import__title>div{display:grid;gap:4px;min-width:0}.parcel-import__heading strong{color:var(--app-ink);font-size:13px}.parcel-import__heading span{color:var(--app-muted);font-size:10px;line-height:1.6}.parcel-import__layout{padding:5px 8px;border-radius:999px;background:#e9f2fb;color:#2e5984!important;font-weight:800;white-space:nowrap}.parcel-import__summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.parcel-import__summary span{display:grid;gap:1px;padding:8px 9px;border:1px solid #e0e7ee;border-radius:8px;background:#fff;color:var(--app-ink-soft)}.parcel-import__summary strong{font-size:12px}.parcel-import__summary small{color:var(--app-muted);font-size:9px;font-weight:700}.parcel-import__summary span[data-state="ready"]{border-color:#cfe4da;color:#2f7456;background:#f3f9f6}.parcel-import__summary span[data-state="attention"]{border-color:#ead9b2;color:#8a6515;background:#fffaf0}.parcel-import__note,.parcel-import__empty{display:flex;align-items:flex-start;gap:7px;margin:0;padding:9px 10px;border-radius:8px;color:var(--app-ink-soft);background:#fff;font-size:10px;line-height:1.6}.parcel-import__note>svg,.parcel-import__empty>svg{flex:0 0 auto;margin-top:1px;color:#2e5984}.parcel-import__toolbar{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.parcel-import__toolbar button{display:inline-flex;min-height:32px;align-items:center;justify-content:center;gap:5px;padding:5px 9px;border:1px solid var(--app-line);border-radius:7px;background:#fff;color:var(--app-ink-soft);cursor:pointer;font-size:10px;font-weight:800}.parcel-import__toolbar>span{margin-left:auto;color:var(--app-muted);font-size:10px;font-weight:800}.parcel-import__table-wrap{overflow:auto;border:1px solid #dde5ed;border-radius:10px;background:#fff}.parcel-import table{width:100%;min-width:980px;border-collapse:collapse}.parcel-import th,.parcel-import td{padding:8px;border-bottom:1px solid #edf0f4;vertical-align:top;text-align:left}.parcel-import th{position:sticky;top:0;z-index:1;background:#f4f7fa;color:#5b6978;font-size:9px;letter-spacing:.03em}.parcel-import td{color:var(--app-ink-soft);font-size:10px}.parcel-import input[type="text"],.parcel-import td input:not([type]){width:100%}.parcel-import td input:not([type="checkbox"]){min-height:34px;padding:5px 7px;border:1px solid var(--app-line);border-radius:6px;background:#fff;color:var(--app-ink);font-size:10px}.parcel-import__split-fields{display:grid;gap:5px;min-width:150px}.parcel-import__source{display:grid;gap:3px;min-width:130px}.parcel-import__source strong{font-size:10px}.parcel-import__source span,.parcel-import__source small{color:var(--app-muted);font-size:9px}.parcel-import__fixed{display:inline-flex;min-height:34px;align-items:center;padding:5px 8px;border-radius:6px;background:#f1f4f7;font-weight:800}.parcel-import__status{display:grid;gap:3px;min-width:120px}.parcel-import__status strong{display:inline-flex;align-items:center;gap:4px;color:#2f745b;font-size:10px}.parcel-import tr[data-state="duplicate"] .parcel-import__status strong{color:#66788a}.parcel-import__status small{color:#a44334;font-size:9px;line-height:1.4}.parcel-import__status small.is-warning{color:#925421}.parcel-import tr[data-state="duplicate"]{opacity:.65}.parcel-import__actions{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:11px;border:1px solid #e1e7ee;border-radius:9px;background:#fff}.parcel-import__actions[data-state="ready"]{border-color:#bfd0e2;background:#f3f7fb}.parcel-import__actions>div{display:flex;align-items:center;gap:8px;color:#66788a}.parcel-import__actions[data-state="ready"]>div{color:#2e5984}.parcel-import__actions>div>span{display:grid;gap:2px}.parcel-import__actions strong{color:var(--app-ink);font-size:10px}.parcel-import__actions small{color:var(--app-muted);font-size:9px;line-height:1.45}.parcel-import__submit{display:inline-flex;flex:0 0 auto;min-height:42px;align-items:center;justify-content:center;gap:6px;padding:9px 14px;border:1px solid #2e5984;border-radius:8px;background:#2e5984;color:#fff;cursor:pointer;font-size:11px;font-weight:900}.parcel-import__submit:disabled{cursor:not-allowed;opacity:.5}@media(max-width:900px){.parcel-import__summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.parcel-import__heading,.parcel-import__actions{align-items:stretch;flex-direction:column}.parcel-import__summary{grid-template-columns:1fr}.parcel-import__toolbar>span{width:100%;margin-left:0}.parcel-import__submit{width:100%}}
</style>
