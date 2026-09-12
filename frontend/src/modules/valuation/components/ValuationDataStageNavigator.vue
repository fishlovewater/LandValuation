<script setup lang="ts">
import {
  PhArrowRight as ArrowRight,
  PhCheckCircle as CheckCircle,
  PhClipboardText as ClipboardText,
  PhListChecks as ListChecks,
  PhMapTrifold as MapTrifold,
  PhScales as Scales,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'

type ValuationDataSection = 'overview' | 'manual' | 'land' | 'f03'

const props = defineProps<{
  activeSection: ValuationDataSection
  issueCounts: {
    overview: number
    manual: number
    land: number
    f03: number
  }
  parcelCount: number
  benchmarkCount: number
  hasF03: boolean
}>()

const emit = defineEmits<{
  select: [section: ValuationDataSection]
}>()
</script>

<template>
  <section class="data-stage-nav" data-testid="valuation-data-stage-nav" aria-labelledby="data-confirmation-title">
    <div class="data-stage-nav__heading">
      <div class="data-stage-nav__title">
        <span class="data-stage-nav__title-icon" aria-hidden="true">
          <ListChecks :size="21" weight="duotone" />
        </span>
        <div>
          <p>資料確認</p>
          <h2 id="data-confirmation-title">資料補齊</h2>
          <span>依資料類別分區處理，完成後才能進入計算與檢核。</span>
        </div>
      </div>
      <span class="data-stage-nav__count" :data-state="props.issueCounts.overview ? 'attention' : 'ready'">
        <WarningCircle v-if="props.issueCounts.overview" :size="14" weight="fill" aria-hidden="true" />
        <CheckCircle v-else :size="14" weight="fill" aria-hidden="true" />
        {{ props.issueCounts.overview ? `待處理 ${props.issueCounts.overview} 項` : '資料已就緒' }}
      </span>
    </div>

    <nav class="data-stage-nav__tabs" aria-label="資料確認子選單">
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'overview' }"
        data-testid="data-section-overview"
        @click="emit('select', 'overview')"
      >
        <span class="data-stage-nav__tab-icon" aria-hidden="true"><ListChecks :size="17" weight="duotone" /></span>
        <span>
          <strong>總覽</strong>
          <small>{{ props.issueCounts.overview ? `${props.issueCounts.overview} 待處理` : '已完成' }}</small>
        </span>
      </button>
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'manual' }"
        data-testid="data-section-manual"
        @click="emit('select', 'manual')"
      >
        <span class="data-stage-nav__tab-icon" aria-hidden="true"><ClipboardText :size="17" weight="duotone" /></span>
        <span>
          <strong>人工補充</strong>
          <small>{{ props.issueCounts.manual ? `${props.issueCounts.manual} 可補充` : '無缺漏' }}</small>
        </span>
      </button>
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'land' }"
        data-testid="data-section-land"
        @click="emit('select', 'land')"
      >
        <span class="data-stage-nav__tab-icon" aria-hidden="true"><MapTrifold :size="17" weight="duotone" /></span>
        <span>
          <strong>宗地與比準地</strong>
          <small>{{ props.issueCounts.land ? `${props.issueCounts.land} 待處理` : '沿用前面資料，可留白' }}</small>
        </span>
      </button>
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'f03' }"
        data-testid="data-section-f03"
        @click="emit('select', 'f03')"
      >
        <span class="data-stage-nav__tab-icon" aria-hidden="true"><Scales :size="17" weight="duotone" /></span>
        <span>
          <strong>比準地地價估計表</strong>
          <small>{{ props.issueCounts.f03 ? `${props.issueCounts.f03} 缺欄位` : props.hasF03 ? '可編輯' : '尚未建立' }}</small>
        </span>
      </button>
    </nav>

    <div v-if="props.activeSection === 'overview'" class="data-stage-nav__overview">
      <article :data-state="props.issueCounts.manual ? 'attention' : 'ready'">
        <span class="data-stage-nav__overview-icon" aria-hidden="true"><ClipboardText :size="18" weight="duotone" /></span>
        <div class="data-stage-nav__overview-copy">
          <strong>人工補充</strong>
          <span>補上文件辨識未取得或仍需人工確認的正式欄位。</span>
        </div>
        <div class="data-stage-nav__overview-action">
          <small>{{ props.issueCounts.manual ? `${props.issueCounts.manual} 項可補充` : '目前沒有缺漏欄位' }}</small>
          <button type="button" @click="emit('select', 'manual')">前往 <ArrowRight :size="13" weight="bold" aria-hidden="true" /></button>
        </div>
      </article>

      <article :data-state="props.issueCounts.land ? 'attention' : 'ready'">
        <span class="data-stage-nav__overview-icon" aria-hidden="true"><MapTrifold :size="18" weight="duotone" /></span>
        <div class="data-stage-nav__overview-copy">
          <strong>宗地與比準地</strong>
          <span>沿用前面步驟已帶入的資料；缺少時可保留空白，不阻擋後續流程。</span>
        </div>
        <div class="data-stage-nav__overview-action">
          <small>{{ props.parcelCount }} 宗地 · {{ props.benchmarkCount }} 比準地</small>
          <button type="button" @click="emit('select', 'land')">前往 <ArrowRight :size="13" weight="bold" aria-hidden="true" /></button>
        </div>
      </article>

      <article :data-state="props.issueCounts.f03 ? 'attention' : props.hasF03 ? 'ready' : 'attention'">
        <span class="data-stage-nav__overview-icon" aria-hidden="true"><Scales :size="18" weight="duotone" /></span>
        <div class="data-stage-nav__overview-copy">
          <strong>比準地地價估計表</strong>
          <span>確認最後會進入公式計算與正式檢核的採用值。</span>
        </div>
        <div class="data-stage-nav__overview-action">
          <small>{{ props.hasF03 ? props.issueCounts.f03 ? `${props.issueCounts.f03} 欄未完成` : '正式資料可編輯' : '尚未建立比準地地價估計表' }}</small>
          <button type="button" @click="emit('select', 'f03')">前往 <ArrowRight :size="13" weight="bold" aria-hidden="true" /></button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.data-stage-nav {
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid #dce5ef;
  border-radius: 12px;
  background: #fff;
}

.data-stage-nav__heading,
.data-stage-nav__title,
.data-stage-nav__count,
.data-stage-nav__tabs button,
.data-stage-nav__overview article,
.data-stage-nav__overview-action,
.data-stage-nav__overview button {
  display: flex;
  align-items: center;
}

.data-stage-nav__heading {
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.data-stage-nav__title { align-items: flex-start; gap: 10px; }
.data-stage-nav__title-icon {
  display: grid;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 9px;
  color: var(--app-accent-deep);
  background: #edf4fb;
}

.data-stage-nav__heading p {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}

.data-stage-nav__heading h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 22px;
}

.data-stage-nav__title > div > span {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.55;
}

.data-stage-nav__count {
  min-height: 30px;
  gap: 5px;
  padding: 5px 9px;
  border: 1px solid var(--app-line);
  border-radius: 999px;
  color: var(--app-ink-soft);
  background: #fff;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}
.data-stage-nav__count[data-state="attention"] { border-color: #ead7bc; color: #855820; background: #fff8ed; }
.data-stage-nav__count[data-state="ready"] { border-color: #cfe4da; color: #2f7456; background: #f1f8f5; }

.data-stage-nav__tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.data-stage-nav__tabs button {
  min-height: 62px;
  gap: 9px;
  padding: 10px 12px;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
  color: #4b5d70;
  background: #fff;
  cursor: pointer;
  text-align: left;
}
.data-stage-nav__tabs button > span:last-child { display: grid; min-width: 0; gap: 3px; }
.data-stage-nav__tab-icon {
  display: grid;
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 8px;
  color: #5c7085;
  background: #f3f6f9;
}

.data-stage-nav__tabs button.is-active {
  border-color: #2e5984;
  color: #244d73;
  background: #edf4fb;
  box-shadow: inset 0 0 0 1px rgba(46, 89, 132, .12);
}
.data-stage-nav__tabs button.is-active .data-stage-nav__tab-icon { color: #244d73; background: #dfeefa; }

.data-stage-nav__tabs strong { font-size: 11px; }
.data-stage-nav__tabs small { color: #718094; font-size: 9px; }

.data-stage-nav__overview {
  display: grid;
  gap: 8px;
}

.data-stage-nav__overview article {
  justify-content: space-between;
  gap: 14px;
  padding: 13px 14px;
  border: 1px solid #dfe6ee;
  border-left-width: 4px;
  border-radius: 9px;
  background: #fff;
}

.data-stage-nav__overview article[data-state="ready"] { border-left-color: #4c9275; }
.data-stage-nav__overview article[data-state="attention"] { border-left-color: #e09837; }
.data-stage-nav__overview-icon {
  display: grid;
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 8px;
  color: var(--app-accent-deep);
  background: #edf4fb;
}
.data-stage-nav__overview-copy { display: grid; flex: 1 1 auto; gap: 3px; min-width: 0; }
.data-stage-nav__overview-action {
  flex: 0 0 auto;
  gap: 10px;
}
.data-stage-nav__overview strong { color: var(--app-ink); font-size: 12px; }
.data-stage-nav__overview span,
.data-stage-nav__overview small { color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.data-stage-nav__overview button {
  min-height: 34px;
  justify-content: center;
  gap: 4px;
  padding: 6px 10px;
  border: 1px solid #cbd8e5;
  border-radius: 8px;
  color: #244d73;
  background: #f5f9fd;
  cursor: pointer;
  font-size: 10px;
  font-weight: 900;
}

@media (max-width: 760px) {
  .data-stage-nav__heading,
  .data-stage-nav__overview article { align-items: stretch; flex-direction: column; }
  .data-stage-nav__tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .data-stage-nav__overview-action { justify-content: space-between; }
  .data-stage-nav__overview-icon { display: none; }
}
</style>
