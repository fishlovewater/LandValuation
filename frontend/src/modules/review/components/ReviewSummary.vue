<script setup lang="ts">
import type { ReviewSummary as Summary } from '../review.types'
defineProps<{ summary: Summary }>()
</script>
<template>
  <section class="summary-grid" aria-label="審查摘要">
    <article><strong>{{ summary.pendingCount }}</strong><span>待處理</span></article>
    <article><strong>{{ summary.inReviewCount }}</strong><span>審查中</span></article>
    <article><strong>{{ summary.actionRequiredCount }}</strong><span>需處理</span></article>
    <article><strong>{{ summary.urgentCount }}</strong><span>緊急</span></article>
    <article><strong>{{ summary.completedCount }}</strong><span>已完成</span></article>
  </section>
</template>