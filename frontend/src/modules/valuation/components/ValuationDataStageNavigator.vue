<script setup lang="ts">
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
      <div>
        <p>資料確認</p>
        <h2 id="data-confirmation-title">資料補齊</h2>
        <span>依資料類別分區處理，只顯示目前需要確認或補充的內容。</span>
      </div>
      <span class="data-stage-nav__count">待處理 {{ props.issueCounts.overview }} 項</span>
    </div>

    <nav class="data-stage-nav__tabs" aria-label="資料確認子選單">
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'overview' }"
        data-testid="data-section-overview"
        @click="emit('select', 'overview')"
      >
        <strong>總覽</strong>
        <small>{{ props.issueCounts.overview ? `${props.issueCounts.overview} 待處理` : '已完成' }}</small>
      </button>
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'manual' }"
        data-testid="data-section-manual"
        @click="emit('select', 'manual')"
      >
        <strong>人工補充</strong>
        <small>{{ props.issueCounts.manual ? `${props.issueCounts.manual} 可補充` : '無缺漏' }}</small>
      </button>
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'land' }"
        data-testid="data-section-land"
        @click="emit('select', 'land')"
      >
        <strong>宗地與比準地</strong>
        <small>{{ props.issueCounts.land ? `${props.issueCounts.land} 待處理` : '已建立' }}</small>
      </button>
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'f03' }"
        data-testid="data-section-f03"
        @click="emit('select', 'f03')"
      >
        <strong>比準地地價估計表</strong>
        <small>{{ props.issueCounts.f03 ? `${props.issueCounts.f03} 缺欄位` : props.hasF03 ? '可編輯' : '尚未建立' }}</small>
      </button>
    </nav>

    <div v-if="props.activeSection === 'overview'" class="data-stage-nav__overview">
      <article :data-state="props.issueCounts.manual ? 'attention' : 'ready'">
        <div>
          <strong>人工補充</strong>
          <span>文件辨識沒有取得的欄位，可在這裡人工補齊。</span>
        </div>
        <div>
          <small>{{ props.issueCounts.manual ? `${props.issueCounts.manual} 項可補充` : '目前沒有缺漏欄位' }}</small>
          <button type="button" @click="emit('select', 'manual')">前往</button>
        </div>
      </article>

      <article :data-state="props.issueCounts.land ? 'attention' : 'ready'">
        <div>
          <strong>宗地與比準地</strong>
          <span>確認宗地基本資料與後續計算使用的比準地。</span>
        </div>
        <div>
          <small>{{ props.parcelCount }} 宗地 · {{ props.benchmarkCount }} 比準地</small>
          <button type="button" @click="emit('select', 'land')">前往</button>
        </div>
      </article>

      <article :data-state="props.issueCounts.f03 ? 'attention' : props.hasF03 ? 'ready' : 'attention'">
        <div>
          <strong>比準地地價估計表</strong>
          <span>確認最後會進入公式計算與正式檢核的採用值。</span>
        </div>
        <div>
          <small>{{ props.hasF03 ? props.issueCounts.f03 ? `${props.issueCounts.f03} 欄未完成` : '正式資料可編輯' : '尚未建立比準地地價估計表' }}</small>
          <button type="button" @click="emit('select', 'f03')">前往</button>
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
  background: #f8fbfe;
}

.data-stage-nav__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
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

.data-stage-nav__heading > div > span {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.55;
}

.data-stage-nav__count {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid var(--app-line);
  border-radius: 999px;
  color: var(--app-ink-soft);
  background: #fff;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.data-stage-nav__tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.data-stage-nav__tabs button {
  display: grid;
  min-height: 62px;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
  color: #4b5d70;
  background: #fff;
  cursor: pointer;
  text-align: left;
}

.data-stage-nav__tabs button.is-active {
  border-color: #2e5984;
  color: #244d73;
  background: #edf4fb;
  box-shadow: inset 0 0 0 1px rgba(46, 89, 132, .12);
}

.data-stage-nav__tabs strong { font-size: 11px; }
.data-stage-nav__tabs small { color: #718094; font-size: 9px; }

.data-stage-nav__overview {
  display: grid;
  gap: 8px;
}

.data-stage-nav__overview article {
  display: flex;
  align-items: center;
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
.data-stage-nav__overview article > div { display: grid; gap: 3px; }
.data-stage-nav__overview article > div:last-child {
  flex: 0 0 auto;
  grid-template-columns: auto auto;
  align-items: center;
  gap: 10px;
}
.data-stage-nav__overview strong { color: var(--app-ink); font-size: 12px; }
.data-stage-nav__overview span,
.data-stage-nav__overview small { color: var(--app-muted); font-size: 10px; line-height: 1.5; }
.data-stage-nav__overview button {
  min-height: 34px;
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
  .data-stage-nav__overview article > div:last-child { grid-template-columns: 1fr auto; }
}
</style>
