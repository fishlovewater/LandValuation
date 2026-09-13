<script setup lang="ts">
import {
  PhCheckCircle as CheckCircle,
  PhClipboardText as ClipboardText,
  PhListChecks as ListChecks,
  PhMapTrifold as MapTrifold,
  PhScales as Scales,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'

type ValuationDataSection = 'manual' | 'land' | 'f03'

const props = defineProps<{
  activeSection: ValuationDataSection
  issueCounts: {
    manual: number
    land: number
    f03: number
  }
  blockingIssueCount: number
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
          <p>估價資料</p>
          <h2 id="data-confirmation-title">確認正式估價資料</h2>
          <span>直接處理宗地、必要欄位與估價採用值，不需要先經過額外總覽頁。</span>
        </div>
      </div>
      <span class="data-stage-nav__count" :data-state="props.blockingIssueCount ? 'attention' : 'ready'">
        <WarningCircle v-if="props.blockingIssueCount" :size="14" weight="fill" aria-hidden="true" />
        <CheckCircle v-else :size="14" weight="fill" aria-hidden="true" />
        {{ props.blockingIssueCount ? `待處理 ${props.blockingIssueCount} 項` : '資料已就緒' }}
      </span>
    </div>

    <nav class="data-stage-nav__tabs" aria-label="估價資料區塊">
      <button
        type="button"
        :class="{ 'is-active': props.activeSection === 'land' }"
        data-testid="data-section-land"
        @click="emit('select', 'land')"
      >
        <span class="data-stage-nav__tab-icon" aria-hidden="true"><MapTrifold :size="17" weight="duotone" /></span>
        <span>
          <strong>宗地與比準地</strong>
          <small>{{ props.issueCounts.land ? `${props.issueCounts.land} 項待處理` : `${props.parcelCount} 宗地 · ${props.benchmarkCount} 比準地` }}</small>
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
          <strong>查估必要欄位</strong>
          <small>{{ props.issueCounts.manual ? `${props.issueCounts.manual} 項必要資料待補` : '可檢視與補充' }}</small>
        </span>
      </button>
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
          <strong>估價參數</strong>
          <small>{{ props.issueCounts.f03 ? `${props.issueCounts.f03} 項採用值待確認` : props.hasF03 ? '比準地地價估計表可編輯' : '尚未建立估價表' }}</small>
        </span>
      </button>
    </nav>
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
.data-stage-nav__tabs button {
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

@media (max-width: 760px) {
  .data-stage-nav__heading { align-items: stretch; flex-direction: column; }
  .data-stage-nav__tabs { grid-template-columns: 1fr; }
}
</style>
