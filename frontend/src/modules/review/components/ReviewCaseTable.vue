<script setup lang="ts">
import StatusBadge from '../../../components/common/StatusBadge.vue'
import RiskBadge from '../../../components/common/RiskBadge.vue'
import { formatDateTime } from '../../../utils/formatters'
import type { ReviewCaseSummary } from '../review.types'

defineProps<{ items: ReviewCaseSummary[] }>()
defineEmits<{ open: [reviewId: string] }>()
</script>
<template>
  <div class="table-wrap">
    <table class="case-table">
      <thead><tr><th>案件</th><th>地區</th><th>狀態</th><th>風險</th><th>缺件</th><th>期限</th><th><span class="sr-only">操作</span></th></tr></thead>
      <tbody>
        <tr v-for="item in items" :key="item.reviewId">
          <td><strong>{{ item.caseNo }}</strong><small>{{ item.title }}</small></td>
          <td>{{ item.district ?? '—' }}</td><td><StatusBadge :status="item.status" /></td><td><RiskBadge :level="item.riskLevel" /></td>
          <td>{{ item.missingItemCount }}</td><td>{{ formatDateTime(item.dueAt) }}</td>
          <td><button class="text-button" type="button" :data-review-id="item.reviewId" @click="$emit('open', item.reviewId)">開啟</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>