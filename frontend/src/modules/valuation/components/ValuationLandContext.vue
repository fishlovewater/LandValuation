<script setup lang="ts">
import {
  PhCheckCircle as CheckCircle,
  PhFileText as FileText,
  PhMapPin as MapPin,
  PhMapTrifold as MapTrifold,
  PhPencilSimple as PencilSimple,
  PhPlus as Plus,
  PhTarget as Target,
  PhX as X,
} from '@phosphor-icons/vue'
import type { BenchmarkLandModel, DocumentArtifactModel, ParcelResponseDto } from '../valuation.types'
import { newTaipeiDistrictName } from '../newTaipei'

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
    class="land-context"
    data-testid="valuation-land-context"
    tabindex="-1"
    aria-labelledby="land-context-title"
  >
    <header class="land-context__heading">
      <div class="land-context__title">
        <span class="land-context__title-icon" aria-hidden="true">
          <MapTrifold :size="22" weight="duotone" />
        </span>
        <div>
          <p>土地資料</p>
          <h2 id="land-context-title">宗地與比準地</h2>
          <span>本區只顯示前面步驟已帶入的宗地與比準地資料；沒有資料時可保留空白。</span>
        </div>
      </div>
      <div class="land-context__summary" aria-label="土地資料統計">
        <span><MapPin :size="15" weight="fill" aria-hidden="true" />宗地 {{ parcels.length }}</span>
        <span><Target :size="15" weight="fill" aria-hidden="true" />比準地 {{ benchmarks.length }}</span>
      </div>
    </header>

    <div class="land-context__grid">
      <section class="land-panel" aria-labelledby="parcel-panel-title">
        <div class="land-panel__heading">
          <div class="land-panel__heading-title">
            <span class="land-panel__icon" aria-hidden="true"><MapPin :size="19" weight="duotone" /></span>
            <div>
              <strong id="parcel-panel-title">宗地資料</strong>
              <span>本案實際要記錄與估價的土地</span>
            </div>
          </div>
          <span class="land-panel__count">{{ parcels.length }} 筆</span>
        </div>

        <p class="land-panel__help">
          宗地資料沿用前面步驟的辨識或匯入結果；本步驟不需重複填寫，缺少的欄位可留白。
        </p>

        <ul v-if="parcels.length" class="land-records">
          <li v-for="parcel in parcels" :key="parcel.parcel_id">
            <div class="land-records__content">
              <strong>{{ parcel.section_name }} {{ parcel.land_no }}</strong>
              <span>{{ parcel.area_sqm }} m² · {{ newTaipeiDistrictName(parcel.district_code) }}</span>
            </div>
            <button
              v-if="canEditLandContext"
              class="land-records__action"
              type="button"
              :data-testid="`edit-parcel-${parcel.parcel_id}`"
              @click="emit('editParcel', parcel)"
            >
              <PencilSimple :size="14" weight="bold" aria-hidden="true" />
              修改
            </button>
          </li>
        </ul>
        <div v-else class="land-panel__empty">
          <MapPin :size="20" weight="duotone" aria-hidden="true" />
          <span>前面步驟尚未帶入宗地資料；本步驟可直接保留空白並繼續。</span>
        </div>

        <form
          v-if="false"
          id="parcel-editor"
          class="land-form"
          tabindex="-1"
          @submit.prevent="emit('saveParcel')"
        >
          <div class="land-form__heading">
            <div>
              <span>{{ editingParcelId ? '編輯既有資料' : '新增土地資料' }}</span>
              <h3>{{ editingParcelId ? '修改宗地' : '新增宗地' }}</h3>
            </div>
            <PencilSimple v-if="editingParcelId" :size="18" weight="duotone" aria-hidden="true" />
            <Plus v-else :size="18" weight="duotone" aria-hidden="true" />
          </div>

          <div class="land-form__fields">
            <label>
              <span>行政區 *</span>
              <input
                :value="newTaipeiDistrictName(props.parcelDraft.districtCode)"
                data-testid="parcel-district-code"
                disabled
              >
              <small>依案件行政區自動帶入，不需重複選擇。</small>
            </label>
            <label>
              <span>段名 *</span>
              <input v-model="props.parcelDraft.sectionName" data-testid="parcel-section-name" required>
            </label>
            <label>
              <span>小段</span>
              <input v-model="props.parcelDraft.subsectionName">
            </label>
            <label>
              <span>地號 *</span>
              <input v-model="props.parcelDraft.landNo" data-testid="parcel-land-no" required>
            </label>
            <label>
              <span>面積 m² *</span>
              <input v-model="props.parcelDraft.areaSqm" data-testid="parcel-area-sqm" inputmode="decimal" required>
            </label>
            <label>
              <span>使用分區</span>
              <input v-model="props.parcelDraft.landUseZone">
            </label>
            <label>
              <span>指定用途</span>
              <input v-model="props.parcelDraft.designatedUse">
            </label>
            <label>
              <span>來源文件</span>
              <div class="land-form__select-with-icon">
                <FileText :size="15" weight="duotone" aria-hidden="true" />
                <select v-model="props.parcelDraft.sourceDocumentId">
                  <option value="">不指定</option>
                  <option
                    v-for="document in documents"
                    :key="document.documentId"
                    :value="document.documentId"
                  >
                    {{ document.filename }}
                  </option>
                </select>
              </div>
            </label>
          </div>

          <div class="land-form__actions">
            <button
              v-if="editingParcelId"
              type="button"
              class="land-button"
              @click="emit('resetParcel')"
            >
              <X :size="15" weight="bold" aria-hidden="true" />
              取消修改
            </button>
            <button
              class="land-button land-button--primary"
              type="submit"
              data-testid="save-parcel"
              :disabled="!canEditLandContext || saving"
            >
              <CheckCircle v-if="editingParcelId && !saving" :size="16" weight="bold" aria-hidden="true" />
              <Plus v-else-if="!saving" :size="16" weight="bold" aria-hidden="true" />
              {{ saving ? '儲存中…' : editingParcelId ? '儲存宗地修改' : '建立宗地' }}
            </button>
          </div>
        </form>
      </section>

      <section class="land-panel" aria-labelledby="benchmark-panel-title">
        <div class="land-panel__heading">
          <div class="land-panel__heading-title">
            <span class="land-panel__icon land-panel__icon--benchmark" aria-hidden="true">
              <Target :size="19" weight="duotone" />
            </span>
            <div>
              <strong id="benchmark-panel-title">比準地資料</strong>
              <span>後續查估使用的比較基準</span>
            </div>
          </div>
          <span class="land-panel__count">{{ benchmarks.length }} 筆</span>
        </div>

        <p class="land-panel__help">
          比準地沿用前面步驟已選定的宗地；本步驟不需重新建立或指定，缺少時可保留空白。
        </p>

        <ul v-if="benchmarks.length" class="land-records land-records--benchmark">
          <li v-for="benchmark in benchmarks" :key="benchmark.benchmarkLandId">
            <div class="land-records__content">
              <strong>{{ benchmark.benchmarkLandNo }}</strong>
              <span>地價區段 {{ benchmark.priceZoneNo }}</span>
            </div>
            <div class="land-records__benchmark-actions">
              <span
                v-if="selectedBenchmarkLandId === benchmark.benchmarkLandId"
                class="benchmark-current"
              >
                <CheckCircle :size="14" weight="fill" aria-hidden="true" />
                目前採用
              </span>
              <button
                v-else-if="hasF03 && canEditF03"
                class="land-records__action"
                type="button"
                :data-testid="`choose-benchmark-${benchmark.benchmarkLandId}`"
                @click="emit('chooseBenchmark', benchmark.benchmarkLandId)"
              >
                <Target :size="14" weight="bold" aria-hidden="true" />
                採用此比準地
              </button>
            </div>
          </li>
        </ul>
        <div v-else class="land-panel__empty">
          <Target :size="20" weight="duotone" aria-hidden="true" />
          <span>前面步驟尚未選定比準地；本步驟可直接保留空白並繼續。</span>
        </div>

        <form v-if="false" class="land-form" @submit.prevent="emit('saveBenchmark')">
          <div class="land-form__heading">
            <div>
              <span>新增比較基準</span>
              <h3>新增比準地</h3>
            </div>
            <Plus :size="18" weight="duotone" aria-hidden="true" />
          </div>

          <div class="land-form__fields">
            <label>
              <span>來源宗地 *</span>
              <select v-model="props.benchmarkDraft.parcelId" data-testid="benchmark-parcel" required>
                <option value="">請選擇宗地</option>
                <option v-for="parcel in parcels" :key="parcel.parcel_id" :value="parcel.parcel_id">
                  {{ parcel.section_name }} {{ parcel.land_no }}
                </option>
              </select>
            </label>
            <label>
              <span>比準地編號 *</span>
              <input v-model="props.benchmarkDraft.benchmarkLandNo" data-testid="benchmark-no" required>
            </label>
            <label>
              <span>地價區段 *</span>
              <input v-model="props.benchmarkDraft.priceZoneNo" data-testid="benchmark-zone" required>
            </label>
            <label>
              <span>重劃序號</span>
              <input v-model="props.benchmarkDraft.landConsolidationSerial">
            </label>
            <label>
              <span>緯度</span>
              <input v-model="props.benchmarkDraft.latitude" inputmode="decimal">
            </label>
            <label>
              <span>經度</span>
              <input v-model="props.benchmarkDraft.longitude" inputmode="decimal">
            </label>
          </div>

          <div class="land-form__actions">
            <button
              class="land-button land-button--primary"
              type="submit"
              data-testid="save-benchmark"
              :disabled="!canEditLandContext || !parcels.length || saving"
            >
              <Plus v-if="!saving" :size="16" weight="bold" aria-hidden="true" />
              {{ saving ? '儲存中…' : '建立比準地' }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.land-context {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: #fff;
}

.land-context__heading,
.land-context__title,
.land-context__summary,
.land-context__summary span,
.land-panel__heading,
.land-panel__heading-title,
.land-records li,
.land-records__action,
.land-records__benchmark-actions,
.benchmark-current,
.land-form__heading,
.land-form__actions,
.land-button,
.land-form__select-with-icon,
.land-panel__empty {
  display: flex;
  align-items: center;
}

.land-context__heading {
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}
.land-context__title { align-items: flex-start; gap: 11px; }
.land-context__title-icon,
.land-panel__icon {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  color: var(--app-accent-deep);
  background: #edf4fb;
}
.land-context__title-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
}
.land-context__title p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.land-context__title h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 23px; font-weight: 650; letter-spacing: -.035em; }
.land-context__title > div > span { display: block; margin-top: 5px; color: var(--app-muted); font-size: 12px; line-height: 1.5; }
.land-context__summary { flex-wrap: wrap; justify-content: flex-end; gap: 7px; }
.land-context__summary span {
  min-height: 30px;
  gap: 6px;
  padding: 5px 9px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-pill);
  color: var(--app-ink-soft);
  background: #f7f9fc;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.land-context__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.land-panel {
  display: grid;
  align-content: start;
  gap: 13px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
  background: #fbfcfe;
}
.land-panel__heading { justify-content: space-between; gap: 12px; }
.land-panel__heading-title { align-items: flex-start; gap: 9px; }
.land-panel__icon { width: 32px; height: 32px; border-radius: 8px; }
.land-panel__icon--benchmark { color: #6546a5; background: #f2edfb; }
.land-panel__heading-title > div { display: grid; gap: 3px; }
.land-panel__heading-title strong { color: var(--app-ink); font-size: 13px; }
.land-panel__heading-title span { color: var(--app-muted); font-size: 10px; }
.land-panel__count {
  padding: 5px 8px;
  border-radius: 999px;
  color: var(--app-ink-soft);
  background: #eef2f7;
  font-size: 10px;
  font-weight: 850;
  white-space: nowrap;
}
.land-panel__help { margin: -3px 0 0; color: var(--app-ink-soft); font-size: 11px; line-height: 1.65; }
.land-panel__empty {
  min-height: 54px;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  border: 1px dashed #cfd9e5;
  border-radius: 8px;
  color: var(--app-muted);
  background: #fff;
  font-size: 11px;
  line-height: 1.5;
}

.land-records { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.land-records li {
  justify-content: space-between;
  gap: 10px;
  padding: 10px 11px;
  border: 1px solid #edf0f4;
  border-radius: 8px;
  background: #fff;
}
.land-records__content { display: grid; min-width: 0; gap: 3px; }
.land-records__content strong { color: var(--app-ink); font-size: 12px; overflow-wrap: anywhere; }
.land-records__content span { color: var(--app-muted); font-size: 10px; }
.land-records__action {
  flex: 0 0 auto;
  min-height: 34px;
  justify-content: center;
  gap: 5px;
  padding: 5px 9px;
  border: 1px solid var(--app-line);
  border-radius: 7px;
  color: var(--app-accent-deep);
  background: #fff;
  cursor: pointer;
  font-size: 10px;
  font-weight: 850;
}
.land-records__benchmark-actions { flex: 0 0 auto; gap: 6px; }
.benchmark-current {
  gap: 5px;
  padding: 5px 8px;
  border-radius: 999px;
  color: #2f7456;
  background: #edf8f2;
  font-size: 9px;
  font-weight: 850;
  white-space: nowrap;
}

.land-form {
  display: grid;
  gap: 11px;
  padding-top: 13px;
  border-top: 1px solid var(--app-line);
}
.land-form__heading { justify-content: space-between; gap: 10px; color: var(--app-accent-deep); }
.land-form__heading > div { display: grid; gap: 2px; }
.land-form__heading span { color: var(--app-muted); font-size: 9px; font-weight: 750; letter-spacing: .06em; }
.land-form__heading h3 { margin: 0; color: var(--app-ink); font-size: 13px; }
.land-form__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
}
.land-form__fields label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 10px; font-weight: 800; }
.land-form__fields label small { color: var(--app-muted); font-size: 9px; font-weight: 500; line-height: 1.45; }
.land-form__fields input,
.land-form__fields select {
  width: 100%;
  min-height: 42px;
  padding: 8px 9px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  outline: none;
}
.land-form__fields input:focus,
.land-form__fields select:focus { border-color: rgba(46, 89, 132, .48); box-shadow: 0 0 0 3px rgba(46, 89, 132, .08); }
.land-form__fields input:disabled { color: #52657a; background: #f1f4f7; }
.land-form__select-with-icon { position: relative; color: var(--app-muted); }
.land-form__select-with-icon > svg { position: absolute; z-index: 1; left: 9px; pointer-events: none; }
.land-form__select-with-icon select { padding-left: 30px; }
.land-form__actions { flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.land-button {
  min-height: 40px;
  justify-content: center;
  gap: 6px;
  padding: 8px 13px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: #fff;
  cursor: pointer;
  font-size: 11px;
  font-weight: 850;
}
.land-button--primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.land-button:disabled { cursor: not-allowed; opacity: .55; }

@media (max-width: 980px) {
  .land-context__grid { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .land-context { padding: 16px; }
  .land-context__heading { align-items: flex-start; flex-direction: column; }
  .land-context__summary { justify-content: flex-start; }
  .land-panel { padding: 14px; }
  .land-form__fields { grid-template-columns: 1fr; }
  .land-records li { align-items: flex-start; flex-direction: column; }
  .land-records__benchmark-actions { width: 100%; }
  .land-records__action { width: 100%; }
  .land-form__actions { flex-direction: column-reverse; }
  .land-button { width: 100%; }
}
</style>
