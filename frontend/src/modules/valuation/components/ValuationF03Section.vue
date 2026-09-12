<script setup lang="ts">
import { ref } from 'vue'
import {
  PhArrowRight as ArrowRight,
  PhCalculator as Calculator,
  PhCalendarBlank as CalendarBlank,
  PhChartLineUp as ChartLineUp,
  PhCheckCircle as CheckCircle,
  PhFloppyDisk as FloppyDisk,
  PhInfo as Info,
  PhScales as Scales,
  PhTarget as Target,
  PhTextAlignLeft as TextAlignLeft,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import type {
  BenchmarkLandModel,
  F03DraftModel,
  F03EditableValues,
  SourceMarker,
} from '../valuation.types'

type F03DetailStep = 'basis' | 'price' | 'market' | 'reason'

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

const activeStep = ref<F03DetailStep>('basis')

function setActiveStep(step: F03DetailStep): void {
  activeStep.value = step
}

function hasValue(value: string | null | undefined): boolean {
  return Boolean(String(value ?? '').trim())
}

function basisReady(): boolean {
  return Boolean(props.draft.benchmarkLandId && hasValue(props.draft.valuationBaseDate))
}

function priceDataReady(): boolean {
  return hasValue(props.draft.comparisonPrice)
    || hasValue(props.draft.incomePrice)
    || hasValue(props.draft.comparisonWeight)
    || hasValue(props.draft.incomeWeight)
}

function marketDataReady(): boolean {
  return hasValue(props.draft.marketPeriodStart)
    || hasValue(props.draft.marketPeriodEnd)
    || hasValue(props.draft.marketCondition)
}

function reasonDataReady(): boolean {
  return hasValue(props.draft.selectionScopeReason) || hasValue(props.draft.decisionReason)
}
</script>

<template>
  <section v-if="!f03" class="f03-setup-required" aria-labelledby="setup-required-title">
    <span class="f03-setup-required__icon" aria-hidden="true">
      <WarningCircle :size="24" weight="duotone" />
    </span>
    <div>
      <p>必要資料</p>
      <h2 id="setup-required-title">估價資料尚未可計算</h2>
      <span>請先完成必要的來源文件、宗地與比準地資料；系統建立比準地地價估計表草稿後，即可在此確認正式採用值。</span>
    </div>
  </section>

  <section v-else id="f03-data-section" class="f03-workspace" aria-labelledby="f03-title">
    <header class="f03-workspace__heading">
      <div class="f03-workspace__title">
        <span class="f03-workspace__title-icon" aria-hidden="true">
          <Scales :size="22" weight="duotone" />
        </span>
        <div>
          <p>比準地地價估計表</p>
          <h2 id="f03-title">資料確認與正式採用值</h2>
          <span>確認比準地、估價基準日、價格權重與理由，儲存後再進入計算與檢核。</span>
        </div>
      </div>
      <span class="source-marker" data-source-kind="human-confirmed">
        <CheckCircle :size="14" weight="fill" aria-hidden="true" />
        {{ f03.source.label }}
      </span>
    </header>

    <div class="official-value" data-testid="official-value">
      <span class="official-value__icon" aria-hidden="true">
        <Calculator :size="22" weight="duotone" />
      </span>
      <div class="official-value__copy">
        <span>系統計算結果</span>
        <strong>比準地地價</strong>
        <small>正式計算後產生，不在本頁人工輸入</small>
      </div>
      <div class="official-value__result">
        <strong>{{ f03.benchmarkLandPrice || '尚未計算' }}</strong>
        <span>元／㎡</span>
      </div>
      <span class="value-kind" data-value-kind="calculated" data-source-kind="calculated">
        {{ calculatedSource.label }}
      </span>
    </div>

    <form class="confirmed-form" @submit.prevent="emit('save')">
      <div class="form-heading">
        <div>
          <h3>人工確認欄位</h3>
          <span>依序確認估價基礎、價格權重、市場條件與專業判斷；不用一次閱讀整張表。</span>
        </div>
        <span class="value-kind" data-value-kind="human-confirmed">
          <CheckCircle :size="13" weight="fill" aria-hidden="true" />
          人工確認後儲存
        </span>
      </div>

      <nav class="f03-detail-flow" aria-label="估價參數填寫步驟" data-testid="f03-detail-flow">
        <button type="button" :class="{ 'is-active': activeStep === 'basis', 'is-complete': basisReady() }" data-testid="f03-step-basis" @click="setActiveStep('basis')">
          <span>1</span>
          <div><strong>比準地與基準日</strong><small>{{ basisReady() ? '已確認' : '先確認' }}</small></div>
        </button>
        <button type="button" :class="{ 'is-active': activeStep === 'price', 'is-complete': priceDataReady() }" data-testid="f03-step-price" @click="setActiveStep('price')">
          <span>2</span>
          <div><strong>價格與權重</strong><small>{{ priceDataReady() ? '已有資料' : '待確認' }}</small></div>
        </button>
        <button type="button" :class="{ 'is-active': activeStep === 'market', 'is-complete': marketDataReady() }" data-testid="f03-step-market" @click="setActiveStep('market')">
          <span>3</span>
          <div><strong>市場條件</strong><small>{{ marketDataReady() ? '已有資料' : '需要時補充' }}</small></div>
        </button>
        <button type="button" :class="{ 'is-active': activeStep === 'reason', 'is-complete': reasonDataReady() }" data-testid="f03-step-reason" @click="setActiveStep('reason')">
          <span>4</span>
          <div><strong>專業判斷</strong><small>{{ reasonDataReady() ? '已有說明' : '需要時補充' }}</small></div>
        </button>
      </nav>

      <fieldset class="field-sections" :disabled="!canEditF03">
        <section v-show="activeStep === 'basis'" class="field-section" aria-labelledby="f03-basis-title">
          <div class="field-section__heading">
            <span aria-hidden="true"><Target :size="18" weight="duotone" /></span>
            <div>
              <strong id="f03-basis-title">估價基礎</strong>
              <small>指定本次採用的比準地與估價基準日。</small>
            </div>
          </div>
          <div class="field-grid">
            <label>
              <span>比準地 *</span>
              <select id="f03-benchmark-land" v-model="props.draft.benchmarkLandId" data-value-kind="human-confirmed" @input="emit('dirty')">
                <option :value="null">請選擇比準地</option>
                <option v-for="land in benchmarks" :key="land.benchmarkLandId" :value="land.benchmarkLandId">{{ land.benchmarkLandNo }}｜{{ land.priceZoneNo }}</option>
              </select>
              <small>可選 {{ benchmarks.length }} 筆已建立比準地。</small>
            </label>
            <label>
              <span>估價基準日 *</span>
              <input id="f03-valuation-base-date" v-model="props.draft.valuationBaseDate" type="date" @input="emit('dirty')">
            </label>
          </div>
          <div class="field-section__next">
            <button type="button" data-testid="f03-next-price" @click="setActiveStep('price')">
              下一步：價格與權重
              <ArrowRight :size="14" weight="bold" aria-hidden="true" />
            </button>
          </div>
        </section>

        <section v-show="activeStep === 'price'" class="field-section" aria-labelledby="f03-price-title">
          <div class="field-section__heading">
            <span aria-hidden="true"><ChartLineUp :size="18" weight="duotone" /></span>
            <div>
              <strong id="f03-price-title">價格與權重</strong>
              <small>輸入比較法與收益法的價格及採用權重；正式結果由規則引擎計算。</small>
            </div>
          </div>
          <div class="field-grid">
            <label><span>比準地比較價格（元／㎡）</span><input id="f03-comparison-price" v-model="props.draft.comparisonPrice" data-testid="f03-comparison-price" inputmode="decimal" @input="emit('dirty')"></label>
            <label><span>比較價格權重</span><input id="f03-comparison-weight" v-model="props.draft.comparisonWeight" inputmode="decimal" @input="emit('dirty')"></label>
            <label><span>比準地收益價格（元／㎡）</span><input id="f03-income-price" v-model="props.draft.incomePrice" inputmode="decimal" @input="emit('dirty')"></label>
            <label><span>收益價格權重</span><input id="f03-income-weight" v-model="props.draft.incomeWeight" inputmode="decimal" @input="emit('dirty')"></label>
          </div>
          <div class="field-section__guidance">
            <Info :size="15" weight="duotone" aria-hidden="true" />
            <span>這裡只填採用的價格與權重；最終比準地地價由下一階段正式計算，不需要人工計算結果。</span>
          </div>
          <div class="field-section__next">
            <button type="button" data-testid="f03-next-market" @click="setActiveStep('market')">
              下一步：市場條件
              <ArrowRight :size="14" weight="bold" aria-hidden="true" />
            </button>
          </div>
        </section>

        <section v-show="activeStep === 'market'" class="field-section" aria-labelledby="f03-market-title">
          <div class="field-section__heading">
            <span aria-hidden="true"><CalendarBlank :size="18" weight="duotone" /></span>
            <div>
              <strong id="f03-market-title">市場條件</strong>
              <small>補充市場期間與本次價格判斷使用的市場條件。</small>
            </div>
          </div>
          <div class="field-grid">
            <label><span>市場期間起日</span><input id="f03-market-period-start" v-model="props.draft.marketPeriodStart" type="date" @input="emit('dirty')"></label>
            <label><span>市場期間迄日</span><input id="f03-market-period-end" v-model="props.draft.marketPeriodEnd" type="date" @input="emit('dirty')"></label>
            <label class="field-grid__wide"><span>市場條件</span><input id="f03-market-condition" v-model="props.draft.marketCondition" @input="emit('dirty')"></label>
          </div>
          <div class="field-section__next">
            <button type="button" data-testid="f03-next-reason" @click="setActiveStep('reason')">
              下一步：專業判斷
              <ArrowRight :size="14" weight="bold" aria-hidden="true" />
            </button>
          </div>
        </section>

        <section v-show="activeStep === 'reason'" class="field-section" aria-labelledby="f03-reason-title">
          <div class="field-section__heading">
            <span aria-hidden="true"><TextAlignLeft :size="18" weight="duotone" /></span>
            <div>
              <strong id="f03-reason-title">採用理由</strong>
              <small>記錄選擇範圍與最終決定的專業判斷依據。</small>
            </div>
          </div>
          <div class="field-grid field-grid--narrative">
            <label><span>選擇範圍理由</span><textarea id="f03-selection-scope-reason" v-model="props.draft.selectionScopeReason" rows="3" @input="emit('dirty')"></textarea></label>
            <label><span>決定理由</span><textarea id="f03-decision-reason" v-model="props.draft.decisionReason" rows="3" @input="emit('dirty')"></textarea></label>
          </div>
        </section>
      </fieldset>

      <div class="action-row">
        <div class="action-row__note">
          <Info :size="16" weight="duotone" aria-hidden="true" />
          <span>{{ canEditF03 ? '儲存後，計算與檢核會使用這一版正式採用值。' : '目前表單不是可編輯草稿，請先建立新的補正版。' }}</span>
        </div>
        <button class="solid-button" data-testid="save-confirmed-fields" type="submit" :disabled="saving || !canEditF03">
          <FloppyDisk v-if="!saving" :size="16" weight="bold" aria-hidden="true" />
          {{ saving ? '儲存中…' : '儲存確認欄位' }}
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.f03-workspace,
.f03-setup-required {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: #fff;
}

.f03-workspace__heading,
.f03-workspace__title,
.source-marker,
.official-value,
.form-heading,
.value-kind,
.field-section__heading,
.action-row,
.action-row__note,
.solid-button,
.f03-setup-required {
  display: flex;
  align-items: center;
}

.f03-workspace__heading { align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
.f03-workspace__title { align-items: flex-start; gap: 11px; }
.f03-workspace__title-icon {
  display: grid;
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 10px;
  color: var(--app-accent-deep);
  background: #edf4fb;
}
.f03-workspace__title p { margin: 0 0 4px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.f03-workspace__title h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 23px; font-weight: 650; letter-spacing: -.035em; }
.f03-workspace__title > div > span { display: block; margin-top: 5px; color: var(--app-muted); font-size: 12px; line-height: 1.5; }

.source-marker,
.value-kind {
  min-height: 30px;
  gap: 5px;
  padding: 5px 9px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-pill);
  color: var(--app-ink-soft);
  background: #f7f9fc;
  font-size: 10px;
  font-weight: 850;
  white-space: nowrap;
}
.source-marker[data-source-kind="human-confirmed"],
.value-kind[data-value-kind="human-confirmed"] { border-color: #d8e4ef; color: #315d84; background: #f1f6fb; }
.value-kind[data-source-kind="calculated"],
.value-kind[data-value-kind="calculated"] { border-color: #d7e4ef; color: #2e5984; background: #edf4fb; }

.official-value {
  gap: 12px;
  margin-bottom: 18px;
  padding: 14px 15px;
  border: 1px solid #dce7f1;
  border-radius: 10px;
  background: #f7faff;
}
.official-value__icon {
  display: grid;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 9px;
  color: var(--app-accent-deep);
  background: #e8f1fa;
}
.official-value__copy { display: grid; gap: 2px; min-width: 0; }
.official-value__copy > span { color: var(--app-muted); font-size: 9px; font-weight: 800; letter-spacing: .06em; }
.official-value__copy > strong { color: var(--app-ink); font-size: 13px; }
.official-value__copy > small { color: var(--app-muted); font-size: 10px; }
.official-value__result { display: flex; align-items: baseline; gap: 6px; margin-left: auto; }
.official-value__result strong { color: #244d73; font-family: var(--app-font-display); font-size: 25px; font-weight: 650; }
.official-value__result span { color: var(--app-muted); font-size: 10px; font-weight: 800; }

.confirmed-form { display: grid; gap: 13px; }
.form-heading { justify-content: space-between; gap: 12px; }
.form-heading > div { display: grid; gap: 3px; }
.form-heading h3 { margin: 0; color: var(--app-ink); font-size: 15px; }
.form-heading > div > span { color: var(--app-muted); font-size: 10px; line-height: 1.5; }

.f03-detail-flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.f03-detail-flow button {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 10px;
  border: 1px solid #dfe6ed;
  border-radius: 9px;
  color: #68798a;
  background: #fff;
  cursor: pointer;
  text-align: left;
}
.f03-detail-flow button > span {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 999px;
  color: #fff;
  background: #7a8b9d;
  font-size: 9px;
  font-weight: 900;
}
.f03-detail-flow button > div { display: grid; gap: 2px; min-width: 0; }
.f03-detail-flow button strong { color: var(--app-ink); font-size: 10px; line-height: 1.35; }
.f03-detail-flow button small { color: var(--app-muted); font-size: 8px; }
.f03-detail-flow button.is-active { border-color: #aac3db; color: #2e5984; background: #f1f6fb; }
.f03-detail-flow button.is-active > span { background: #2e5984; }
.f03-detail-flow button.is-complete:not(.is-active) { border-color: #cfe4da; background: #f5faf7; }
.f03-detail-flow button.is-complete:not(.is-active) > span { background: #3c8368; }

.field-sections { display: grid; gap: 10px; min-width: 0; margin: 0; padding: 0; border: 0; }
.field-sections:disabled { opacity: .68; }
.field-section {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid #e6ebf0;
  border-radius: 9px;
  background: #fbfcfe;
}
.field-section__heading { align-items: flex-start; gap: 8px; }
.field-section__heading > span {
  display: grid;
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 8px;
  color: var(--app-accent-deep);
  background: #edf4fb;
}
.field-section__heading > div { display: grid; gap: 2px; }
.field-section__heading strong { color: var(--app-ink); font-size: 12px; }
.field-section__heading small { color: var(--app-muted); font-size: 9px; line-height: 1.5; }

.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; min-width: 0; }
.field-grid--narrative { grid-template-columns: 1fr 1fr; }
.field-grid label { display: grid; gap: 6px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.field-grid label > small { color: var(--app-muted); font-size: 9px; font-weight: 500; }
.field-grid__wide { grid-column: 1 / -1; }
.field-grid input,
.field-grid select,
.field-grid textarea {
  width: 100%;
  min-height: 42px;
  padding: 8px 10px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  font: inherit;
  font-weight: 500;
  outline: none;
}
.field-grid textarea { min-height: 82px; resize: vertical; line-height: 1.55; }
.field-grid input:focus,
.field-grid select:focus,
.field-grid textarea:focus { border-color: rgba(46, 89, 132, .48); box-shadow: 0 0 0 3px rgba(46, 89, 132, .08); }
.field-section__guidance { display: flex; align-items: flex-start; gap: 7px; padding: 9px 10px; border: 1px solid #dce7f1; border-radius: 8px; color: #486075; background: #f6f9fc; font-size: 10px; line-height: 1.5; }
.field-section__guidance > svg { flex: 0 0 auto; margin-top: 1px; color: #2e5984; }
.field-section__next { display: flex; justify-content: flex-end; padding-top: 2px; }
.field-section__next button { display: inline-flex; min-height: 36px; align-items: center; justify-content: center; gap: 5px; padding: 7px 10px; border: 1px solid #c9d6e2; border-radius: 8px; color: #244d73; background: #fff; cursor: pointer; font-size: 10px; font-weight: 900; }

.action-row { justify-content: space-between; gap: 14px; padding-top: 2px; }
.action-row__note { align-items: flex-start; gap: 7px; max-width: 680px; color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.action-row__note svg { flex: 0 0 auto; margin-top: 1px; color: var(--app-accent-deep); }
.solid-button {
  flex: 0 0 auto;
  min-height: 42px;
  justify-content: center;
  gap: 6px;
  padding: 9px 15px;
  border: 1px solid var(--app-accent);
  border-radius: 8px;
  color: #fff;
  background: var(--app-accent);
  cursor: pointer;
  font-size: 12px;
  font-weight: 850;
}
.solid-button:disabled { cursor: not-allowed; opacity: .55; }

.f03-setup-required {
  align-items: flex-start;
  gap: 11px;
  border-color: #eadfbf;
  background: #fffbf2;
}
.f03-setup-required__icon {
  display: grid;
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 10px;
  color: #8f6621;
  background: #fff2d8;
}
.f03-setup-required > div { display: grid; gap: 4px; }
.f03-setup-required p { margin: 0; color: #8f6621; font-size: 10px; font-weight: 850; letter-spacing: .08em; }
.f03-setup-required h2 { margin: 0; color: var(--app-ink); font-size: 18px; }
.f03-setup-required > div > span { color: var(--app-ink-soft); font-size: 11px; line-height: 1.65; }

@media (max-width: 760px) {
  .f03-workspace,
  .f03-setup-required { padding: 16px; }
  .f03-workspace__heading,
  .official-value,
  .form-heading,
  .action-row { align-items: stretch; flex-direction: column; }
  .source-marker { align-self: flex-start; }
  .official-value__result { margin-left: 0; }
  .f03-detail-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .field-grid,
  .field-grid--narrative { grid-template-columns: 1fr; }
  .field-grid__wide { grid-column: auto; }
  .field-section__next button { width: 100%; }
  .solid-button { width: 100%; }
}

@media (max-width: 460px) {
  .f03-detail-flow { grid-template-columns: 1fr; }
}
</style>
