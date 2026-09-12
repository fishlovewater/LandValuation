<script setup lang="ts">
import { computed } from 'vue'
import {
  PhArrowRight as ArrowRight,
  PhCheckCircle as CheckCircle,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'

export interface ValuationIssueItem {
  id: string
  title: string
  detail: string
  target: string
  severity?: 'error' | 'warning' | 'pending'
}

const props = defineProps<{
  items: ValuationIssueItem[]
}>()

const emit = defineEmits<{
  select: [target: string]
}>()

const count = computed(() => props.items.length)

function selectIssue(target: string): void {
  emit('select', target)
}
</script>

<template>
  <section
    class="issue-drawer"
    :class="{ 'is-complete': count === 0 }"
    data-testid="valuation-issue-drawer"
    aria-labelledby="valuation-issue-title"
  >
    <header class="issue-drawer__heading">
      <div class="issue-drawer__title">
        <CheckCircle v-if="count === 0" :size="20" weight="duotone" aria-hidden="true" />
        <WarningCircle v-else :size="20" weight="duotone" aria-hidden="true" />
        <div>
        <span class="issue-drawer__eyebrow">作業檢查</span>
        <h2 id="valuation-issue-title">{{ count ? `待處理事項 ${count} 項` : '目前流程已完成' }}</h2>
        </div>
      </div>
      <span class="issue-drawer__status" :class="{ 'is-complete': count === 0 }">
        <span class="issue-drawer__status-dot" aria-hidden="true" />
        {{ count ? '請依序處理' : '可以繼續下一步' }}
      </span>
    </header>

    <div v-if="items.length" class="issue-drawer__list">
      <article v-for="item in items" :key="item.id" :class="['issue-drawer__item', `is-${item.severity ?? 'pending'}`]">
        <span class="issue-drawer__severity" aria-hidden="true" />
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.detail }}</p>
        </div>
        <button type="button" @click="selectIssue(item.target)">
          <span>前往修正</span>
          <ArrowRight :size="14" weight="bold" aria-hidden="true" />
        </button>
      </article>
    </div>
    <div v-else class="issue-drawer__empty">
      <strong>目前沒有阻擋事項</strong>
      <p>必要資料、人工確認與系統檢核目前都已完成。</p>
    </div>
  </section>
</template>

<style scoped>
.issue-drawer { display:grid; gap:12px; padding:16px; border:1px solid #e4c38d; border-radius:12px; background:#fffaf2; }
.issue-drawer.is-complete { border-color:#b6d7c8; background:#f4faf7; }
.issue-drawer__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.issue-drawer__title { display:flex; align-items:flex-start; gap:9px; color:#8b5d19; }
.issue-drawer.is-complete .issue-drawer__title { color:#2f745b; }
.issue-drawer__title > div { display:grid; gap:0; }
.issue-drawer__eyebrow { color:var(--app-primary); font-size:9px; font-weight:900; letter-spacing:.15em; }
.issue-drawer__heading h2 { margin:4px 0 0; color:var(--app-ink); font-size:18px; }
.issue-drawer__status { display:inline-flex; align-items:center; gap:7px; min-height:32px; padding:0 10px; border:1px solid #e4c38d; border-radius:999px; color:#73400e; background:#fff; font-size:10px; font-weight:900; white-space:nowrap; }
.issue-drawer__status.is-complete { border-color:#9ec9b5; color:#205f49; }
.issue-drawer__status-dot { width:7px; height:7px; border-radius:50%; background:var(--app-highlight); }
.issue-drawer__status.is-complete .issue-drawer__status-dot { background:var(--app-green); }
.issue-drawer__list { display:grid; align-content:start; gap:8px; }
.issue-drawer__item { display:grid; grid-template-columns:10px minmax(0,1fr) auto; align-items:start; gap:10px; padding:13px; border:1px solid var(--app-line); border-radius:10px; background:#fff; }
.issue-drawer__severity { width:8px; height:8px; margin-top:5px; border-radius:50%; background:var(--app-highlight); }
.issue-drawer__item.is-error .issue-drawer__severity { background:var(--app-red); }
.issue-drawer__item.is-warning .issue-drawer__severity { background:var(--app-highlight); }
.issue-drawer__item.is-pending .issue-drawer__severity { background:var(--app-primary); }
.issue-drawer__item strong { color:var(--app-ink); font-size:12px; }
.issue-drawer__item p { margin:4px 0 0; color:var(--app-muted); font-size:11px; line-height:1.55; }
.issue-drawer__item > button { display:inline-flex; min-height:36px; align-items:center; justify-content:center; gap:6px; padding:0 10px; border:1px solid var(--app-primary); border-radius:8px; color:var(--app-primary-deep); background:var(--app-primary-soft); cursor:pointer; font-size:11px; font-weight:900; }
.issue-drawer__empty { align-self:start; padding:14px; border:1px dashed #a7c7b9; border-radius:10px; color:#205f49; background:#fff; text-align:left; }
.issue-drawer__empty p { margin:6px 0 0; color:#587366; font-size:11px; line-height:1.6; }
@media (max-width:640px) {
  .issue-drawer__heading { flex-direction:column; }
  .issue-drawer__item { grid-template-columns:10px minmax(0,1fr); }
  .issue-drawer__item > button { grid-column:2; justify-self:start; }
}
</style>
