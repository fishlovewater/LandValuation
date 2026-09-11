<script setup lang="ts">
import type { BenchmarkLandModel, DocumentArtifactModel, ParcelResponseDto } from '../valuation.types'

type ParcelDraft = {
  districtCode: string
  sectionName: string
  subsectionName: string
  landNo: string
  areaSqm: string
  landUseZone: string
  designatedUse: string
  sourceDocumentId: string
}

type BenchmarkDraft = {
  parcelId: string
  benchmarkLandNo: string
  priceZoneNo: string
  landConsolidationSerial: string
  latitude: string
  longitude: string
}

const props = defineProps<{
  parcels: ParcelResponseDto[]
  benchmarks: BenchmarkLandModel[]
  documents: DocumentArtifactModel[]
  parcelDraft: ParcelDraft
  benchmarkDraft: BenchmarkDraft
  editingParcelId: string | null
  selectedBenchmarkLandId: string | null
  canEditLandContext: boolean
  canEditF03: boolean
  hasF03: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  editParcel: [parcel: ParcelResponseDto]
  resetParcel: []
  saveParcel: []
  saveBenchmark: []
  chooseBenchmark: [benchmarkLandId: string]
}>()
</script>

<template>
  <section
    id="valuation-land-context"
    class="valuation-surface land-context"
    data-testid="valuation-land-context"
    tabindex="-1"
    aria-labelledby="land-context-title"
  >
    <div class="surface-heading">
      <div>
        <p class="valuation-eyebrow">土地資料</p>
        <h2 id="land-context-title">宗地與比準地</h2>
      </div>
      <span class="value-kind">宗地 {{ parcels.length }} · 比準地 {{ benchmarks.length }}</span>
    </div>

    <div class="land-context__grid">
      <section class="land-context__panel">
        <div class="land-context__panel-heading"><strong>宗地資料</strong><span>可新增或修改</span></div>
        <p class="land-context__help">宗地是本案要記錄與估價的土地資料。先確認段名、地號、面積與使用分區；資料有誤可直接修改既有宗地。</p>
        <ul v-if="parcels.length" class="land-context__records">
          <li v-for="parcel in parcels" :key="parcel.parcel_id">
            <div>
              <strong>{{ parcel.section_name }} {{ parcel.land_no }}</strong>
              <span>{{ parcel.area_sqm }} m² · {{ parcel.district_code }}</span>
            </div>
            <button v-if="canEditLandContext" type="button" :data-testid="`edit-parcel-${parcel.parcel_id}`" @click="emit('editParcel', parcel)">修改</button>
          </li>
        </ul>
        <p v-else class="empty-copy">尚未建立宗地；請直接使用下方表單建立。</p>

        <form id="parcel-editor" class="land-context__form" tabindex="-1" @submit.prevent="emit('saveParcel')">
          <h3>{{ editingParcelId ? '修改宗地' : '新增宗地' }}</h3>
          <div class="land-context__fields">
            <label><span>行政區代碼 *</span><input v-model="props.parcelDraft.districtCode" data-testid="parcel-district-code" required></label>
            <label><span>段名 *</span><input v-model="props.parcelDraft.sectionName" data-testid="parcel-section-name" required></label>
            <label><span>小段</span><input v-model="props.parcelDraft.subsectionName"></label>
            <label><span>地號 *</span><input v-model="props.parcelDraft.landNo" data-testid="parcel-land-no" required></label>
            <label><span>面積 m² *</span><input v-model="props.parcelDraft.areaSqm" data-testid="parcel-area-sqm" inputmode="decimal" required></label>
            <label><span>使用分區</span><input v-model="props.parcelDraft.landUseZone"></label>
            <label><span>指定用途</span><input v-model="props.parcelDraft.designatedUse"></label>
            <label><span>來源文件</span>
              <select v-model="props.parcelDraft.sourceDocumentId">
                <option value="">不指定</option>
                <option v-for="document in documents" :key="document.documentId" :value="document.documentId">{{ document.filename }}</option>
              </select>
            </label>
          </div>
          <div class="land-context__form-actions">
            <button v-if="editingParcelId" type="button" class="solid-button" @click="emit('resetParcel')">取消修改</button>
            <button class="solid-button solid-button--primary" type="submit" data-testid="save-parcel" :disabled="!canEditLandContext || saving">
              {{ saving ? '儲存中…' : editingParcelId ? '儲存宗地修改' : '建立宗地' }}
            </button>
          </div>
        </form>
      </section>

      <section class="land-context__panel">
        <div class="land-context__panel-heading"><strong>比準地資料</strong><span>如需更換比準地資料，請新增一筆，再明確指定給 F03；既有紀錄不直接覆寫</span></div>
        <p class="land-context__help">比準地是後續查估所使用的比較基準。此系統建立時需指定來源宗地、比準地編號與地價區段；要改用另一筆時，新增後按「採用此比準地」。</p>
        <ul v-if="benchmarks.length" class="land-context__records">
          <li v-for="benchmark in benchmarks" :key="benchmark.benchmarkLandId">
            <div>
              <strong>{{ benchmark.benchmarkLandNo }}</strong>
              <span>地價區段 {{ benchmark.priceZoneNo }}</span>
            </div>
            <div class="land-context__record-actions">
              <span v-if="selectedBenchmarkLandId === benchmark.benchmarkLandId" class="benchmark-current">目前 F03 採用</span>
              <button v-else-if="hasF03 && canEditF03" type="button" :data-testid="`choose-benchmark-${benchmark.benchmarkLandId}`" @click="emit('chooseBenchmark', benchmark.benchmarkLandId)">採用此比準地</button>
            </div>
          </li>
        </ul>
        <p v-else class="empty-copy">尚未建立比準地；建立後才能初始化／選擇 F03 比準地。</p>

        <form class="land-context__form" @submit.prevent="emit('saveBenchmark')">
          <h3>新增比準地</h3>
          <div class="land-context__fields">
            <label><span>來源宗地 *</span>
              <select v-model="props.benchmarkDraft.parcelId" data-testid="benchmark-parcel" required>
                <option value="">請選擇宗地</option>
                <option v-for="parcel in parcels" :key="parcel.parcel_id" :value="parcel.parcel_id">{{ parcel.section_name }} {{ parcel.land_no }}</option>
              </select>
            </label>
            <label><span>比準地編號 *</span><input v-model="props.benchmarkDraft.benchmarkLandNo" data-testid="benchmark-no" required></label>
            <label><span>地價區段 *</span><input v-model="props.benchmarkDraft.priceZoneNo" data-testid="benchmark-zone" required></label>
            <label><span>重劃序號</span><input v-model="props.benchmarkDraft.landConsolidationSerial"></label>
            <label><span>緯度</span><input v-model="props.benchmarkDraft.latitude" inputmode="decimal"></label>
            <label><span>經度</span><input v-model="props.benchmarkDraft.longitude" inputmode="decimal"></label>
          </div>
          <div class="land-context__form-actions">
            <button class="solid-button solid-button--primary" type="submit" data-testid="save-benchmark" :disabled="!canEditLandContext || !parcels.length || saving">
              {{ saving ? '儲存中…' : '建立比準地' }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.valuation-surface{padding:22px;border:1px solid var(--app-line);border-radius:var(--app-radius-md);background:var(--app-paper-strong);box-shadow:var(--app-shadow-soft)}.surface-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.surface-heading h2{margin:0;color:var(--app-ink);font-family:var(--app-font-display);font-size:24px;font-weight:600;letter-spacing:-.04em}.valuation-eyebrow{margin:0 0 6px;color:var(--app-accent-deep);font-size:11px;font-weight:800;letter-spacing:.12em}.value-kind{display:inline-flex;min-height:30px;align-items:center;padding:5px 10px;border:1px solid var(--app-line);border-radius:var(--app-radius-pill);color:var(--app-ink-soft);background:#f7f8fb;font-size:11px;font-weight:800;white-space:nowrap}.land-context__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.land-context__panel{display:grid;align-content:start;gap:12px;padding:15px;border:1px solid var(--app-line);border-radius:11px;background:#fbfcfe}.land-context__panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.land-context__panel-heading strong{color:var(--app-ink);font-size:13px}.land-context__panel-heading span{color:var(--app-muted);font-size:10px;text-align:right}.land-context__help{margin:-4px 0 0;color:var(--app-ink-soft);font-size:10px;line-height:1.6}.land-context__records{display:grid;gap:7px;margin:0;padding:0;list-style:none}.land-context__records li{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px;border-radius:8px;background:#fff}.land-context__records li>div{display:grid;gap:3px;min-width:0}.land-context__records strong{color:var(--app-ink);font-size:12px}.land-context__records span{color:var(--app-muted);font-size:10px}.land-context__records button{min-height:34px;padding:5px 9px;border:1px solid var(--app-line);border-radius:7px;color:var(--app-accent-deep);background:#fff;cursor:pointer;font-size:10px;font-weight:900}.land-context__record-actions{display:flex!important;flex:0 0 auto;align-items:center;gap:6px!important}.land-context__record-actions .benchmark-current{padding:5px 8px;border-radius:999px;color:var(--app-green);background:rgba(59,129,102,.09);font-size:9px;font-weight:900;white-space:nowrap}.land-context__form{display:grid;gap:10px;padding-top:11px;border-top:1px solid var(--app-line)}.land-context__form h3{margin:0;color:var(--app-ink);font-size:13px}.land-context__fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.land-context__fields label{display:grid;gap:5px;color:var(--app-ink-soft);font-size:10px;font-weight:800}.land-context__fields input,.land-context__fields select{width:100%;min-height:42px;padding:8px 9px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-ink);background:#fff}.land-context__form-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.solid-button{min-height:44px;padding:10px 16px;border:1px solid var(--app-line);border-radius:9px;color:var(--app-ink-soft);background:var(--app-paper-strong);cursor:pointer;font-size:13px;font-weight:800}.solid-button--primary{border-color:var(--app-accent);color:#fff;background:var(--app-accent)}.solid-button:disabled{cursor:not-allowed;opacity:.55}.empty-copy{margin:0;color:var(--app-muted);font-size:13px}@media(max-width:760px){.valuation-surface{padding:16px}.surface-heading{align-items:stretch;flex-direction:column}.land-context__grid,.land-context__fields{grid-template-columns:1fr}.solid-button{width:100%}}
</style>
