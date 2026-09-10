<script setup lang="ts">
import type { ReviewSummary as Summary } from '../review.types'
defineProps<{ summary: Summary }>()
</script>
<template>
  <section class="summary-grid" aria-label="審查摘要">
    <article><strong>{{ summary.totalCount }}</strong><span>全部案件</span></article>
    <article><strong>{{ summary.highRiskCount }}</strong><span>高風險案件</span></article>
    <article><strong>{{ summary.openFindingCount }}</strong><span>未處理疑點</span></article>
    <article><strong>{{ summary.missingItemCount }}</strong><span>缺件項目</span></article>
  </section>
</template>