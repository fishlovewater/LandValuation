<script setup lang="ts">
import type {
  BenchmarkLandModel,
  F03DraftModel,
  F03EditableValues,
  SourceMarker,
} from '../valuation.types'

const props = defineProps<{
  f03: F03DraftModel | null
  benchmarks: BenchmarkLandModel[]
  draft: F03EditableValues
  calculatedSource: SourceMarker
  canEditF03: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  dirty: []
  save: []
}>()
</script>

<template>
  <section v-if="!f03" class="valuation-surface setup-required" aria-labelledby="setup-required-title">
    <div>
      <p class="valuation-eyebrow">必要資料</p>
      <h2 id="setup-required-title">估價資料尚未可計算</h2>
    </div>
    <p>請先完成必要的來源文件、宗地與比準地資料；F03 草稿建立完成後即可進行計算與檢核。</p>
  </section>

  <section v-else id="f03-data-section" class="valuation-surface" aria-labelledby="f03-title">
    <div class="surface-heading">
      <div>
        <p class="valuation-eyebrow">F03 正式資料</p>
        <h2 id="f03-title">資料確認與正式採用值</h2>
      </div>
      <span class="source-marker" data-source-kind="human-confirmed">{{ f03.source.label }}</span>
    </div>

    <div class="official-value" data-testid="official-value">
      <div>
        <span>比準地正式採用價格</span>
        <strong>{{ f03.benchmarkLandPrice || '尚未計算' }}</strong>
      </div>
      <span class="value-kind" data-value-kind="calculated" data-source-kind="calculated">{{ calculatedSource.label }}</span>
    </div>

    <form class="confirmed-form" @submit.prevent="emit('save')">
      <div class="form-heading">
        <h3>人工確認欄位</h3>
        <span class="value-kind" data-value-kind="human-confirmed">人工確認後儲存</span>
      </div>
      <fieldset class="field-grid" :disabled="!canEditF03">
        <label>
          <span>比準地</span>
          <select id="f03-benchmark-land" v-model="props.draft.benchmarkLandId" data-value-kind="human-confirmed" @input="emit('dirty')">
            <option :value="null">請選擇比準地</option>
            <option v-for="land in benchmarks" :key="land.benchmarkLandId" :value="land.benchmarkLandId">{{ land.benchmarkLandNo }}｜{{ land.priceZoneNo }}</option>
          </select>
        </label>
        <label><span>估價基準日</span><input id="f03-valuation-base-date" v-model="props.draft.valuationBaseDate" type="date" @input="emit('dirty')" /></label>
        <label><span>比較法價格（正式值）</span><input id="f03-comparison-price" v-model="props.draft.comparisonPrice" data-testid="f03-comparison-price" inputmode="decimal" @input="emit('dirty')" /></label>
        <label><span>比較法權重</span><input id="f03-comparison-weight" v-model="props.draft.comparisonWeight" inputmode="decimal" @input="emit('dirty')" /></label>
        <label><span>收益法價格（正式值）</span><input id="f03-income-price" v-model="props.draft.incomePrice" inputmode="decimal" @input="emit('dirty')" /></label>
        <label><span>收益法權重</span><input id="f03-income-weight" v-model="props.draft.incomeWeight" inputmode="decimal" @input="emit('dirty')" /></label>
        <label><span>市場期間起日</span><input id="f03-market-period-start" v-model="props.draft.marketPeriodStart" type="date" @input="emit('dirty')" /></label>
        <label><span>市場期間迄日</span><input id="f03-market-period-end" v-model="props.draft.marketPeriodEnd" type="date" @input="emit('dirty')" /></label>
        <label class="field-grid__wide"><span>市場條件</span><input id="f03-market-condition" v-model="props.draft.marketCondition" @input="emit('dirty')" /></label>
        <label class="field-grid__wide"><span>選擇範圍理由</span><textarea id="f03-selection-scope-reason" v-model="props.draft.selectionScopeReason" rows="2" @input="emit('dirty')" /></label>
        <label class="field-grid__wide"><span>採用決策理由</span><textarea id="f03-decision-reason" v-model="props.draft.decisionReason" rows="2" @input="emit('dirty')" /></label>
      </fieldset>
      <div class="action-row">
        <button class="solid-button" data-testid="save-confirmed-fields" type="submit" :disabled="saving || !canEditF03">{{ saving ? '儲存中…' : '儲存確認欄位' }}</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.valuation-surface{padding:22px;border:1px solid var(--app-line);border-radius:var(--app-radius-md);background:var(--app-paper-strong);box-shadow:var(--app-shadow-soft)}.surface-heading,.form-heading,.action-row,.official-value{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.surface-heading{margin-bottom:18px}.surface-heading h2{margin:0;color:var(--app-ink);font-family:var(--app-font-display);font-size:24px;font-weight:600;letter-spacing:-.04em}.valuation-eyebrow{margin:0 0 6px;color:var(--app-accent-deep);font-size:11px;font-weight:800;letter-spacing:.12em}.source-marker,.value-kind{display:inline-flex;min-height:30px;align-items:center;padding:5px 10px;border:1px solid var(--app-line);border-radius:var(--app-radius-pill);color:var(--app-ink-soft);background:#f7f8fb;font-size:11px;font-weight:800;white-space:nowrap}.source-marker[data-source-kind="human-confirmed"]{border-color:rgba(200,91,67,.24);color:var(--app-accent-deep);background:rgba(200,91,67,.08)}.value-kind[data-source-kind="calculated"],.value-kind[data-value-kind="calculated"]{border-color:rgba(46,89,132,.22);color:#2e5984;background:#edf4fb}.setup-required{display:grid;gap:10px;border-color:rgba(214,166,62,.28);background:rgba(255,250,240,.78)}.setup-required h2{margin:0;color:var(--app-ink)}.setup-required p:last-child{margin:0;color:var(--app-ink-soft);line-height:1.7}.official-value{align-items:center;margin-bottom:20px;padding:16px;border:1px solid rgba(46,89,132,.18);border-radius:var(--app-radius-sm);background:#f5f8fc}.official-value div{display:grid;gap:6px}.official-value span{color:var(--app-muted);font-size:11px;font-weight:800}.official-value strong{color:#244d73;font-family:var(--app-font-display);font-size:24px;font-weight:600}.form-heading{align-items:center;margin-bottom:12px}.form-heading h3{margin:0;color:var(--app-ink);font-size:16px}.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;min-width:0;margin:0;padding:0;border:0}.field-grid:disabled{opacity:.68}.field-grid label{display:grid;gap:6px;color:var(--app-ink-soft);font-size:12px;font-weight:800}.field-grid__wide{grid-column:1/-1}.field-grid input,.field-grid select,.field-grid textarea{width:100%;min-height:44px;padding:9px 11px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-ink);background:#fff;font:inherit;font-weight:500}.field-grid textarea{min-height:72px;resize:vertical}.field-grid input:focus,.field-grid select:focus,.field-grid textarea:focus{outline:3px solid rgba(200,91,67,.18);border-color:var(--app-accent)}.action-row{justify-content:flex-end;margin-top:18px}.solid-button{min-height:44px;padding:10px 16px;border:1px solid var(--app-line);border-radius:9px;color:var(--app-ink-soft);background:var(--app-paper-strong);cursor:pointer;font-size:13px;font-weight:800}.solid-button:disabled{cursor:not-allowed;opacity:.55}@media(max-width:760px){.valuation-surface{padding:16px}.surface-heading,.official-value,.form-heading,.action-row{align-items:stretch;flex-direction:column}.field-grid{grid-template-columns:1fr}.field-grid__wide{grid-column:auto}.solid-button{width:100%}}
</style>
