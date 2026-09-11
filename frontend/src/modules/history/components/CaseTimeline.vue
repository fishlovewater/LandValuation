<script setup lang="ts">
import { formatDateZhTw } from '../../../utils/formatters'
import type { HistoryTimelineEvent } from '../history.types'

defineProps<{
  events: HistoryTimelineEvent[]
}>()

function moduleLabel(module: HistoryTimelineEvent['module']): string {
  if (module === 'valuation') return '估價'
  if (module === 'review') return '審查'
  if (module === 'document') return '文件'
  return '案件'
}
</script>

<template>
  <section class="case-timeline" aria-labelledby="case-timeline-title">
    <div class="case-timeline__heading">
      <div>
        <p class="case-timeline__eyebrow">案件歷程</p>
        <h2 id="case-timeline-title">案件時間軸</h2>
      </div>
      <span class="case-timeline__count">{{ events.length }} 筆事件</span>
    </div>

    <p v-if="!events.length" class="case-timeline__empty">目前沒有可顯示的歷程事件。</p>
    <ol v-else class="case-timeline__list">
      <li v-for="event in events" :key="event.id" class="case-timeline__item">
        <span class="case-timeline__dot" aria-hidden="true" />
        <div class="case-timeline__body">
          <div class="case-timeline__meta">
            <time :datetime="event.occurredAt">{{ formatDateZhTw(event.occurredAt) }}</time>
            <span class="case-timeline__module">{{ moduleLabel(event.module) }}</span>
          </div>
          <h3>{{ event.title }}</h3>
          <p>{{ event.description }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.case-timeline {
  padding: 20px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
}

.case-timeline__heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 17px;
}

.case-timeline__eyebrow {
  margin: 0 0 5px;
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .15em;
}

.case-timeline h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 24px;
}

.case-timeline__count {
  color: var(--app-muted);
  font-size: 12px;
}

.case-timeline__list {
  position: relative;
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.case-timeline__list::before {
  position: absolute;
  top: 11px;
  bottom: 11px;
  left: 7px;
  width: 1px;
  background: var(--app-line);
  content: "";
}

.case-timeline__item {
  position: relative;
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 13px;
  min-height: 74px;
}

.case-timeline__dot {
  position: relative;
  z-index: 1;
  display: block;
  width: 15px;
  height: 15px;
  margin-top: 4px;
  border: 4px solid var(--app-paper-strong);
  border-radius: 50%;
  background: var(--app-accent);
  box-shadow: 0 0 0 1px rgba(200, 91, 67, .25);
}

.case-timeline__body {
  padding-bottom: 17px;
}

.case-timeline__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--app-muted);
  font-size: 11px;
}

.case-timeline__module {
  padding: 3px 8px;
  border-radius: var(--app-radius-pill);
  color: var(--app-blue);
  background: #edf4fb;
  font-weight: 800;
}

.case-timeline h3 {
  margin: 5px 0 3px;
  color: var(--app-ink);
  font-size: 14px;
}

.case-timeline__body p,
.case-timeline__empty {
  margin: 0;
  color: var(--app-ink-soft);
  font-size: 12px;
  line-height: 1.6;
}

.case-timeline__empty {
  padding: 24px 0 6px;
}
</style>
