<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../../components/common/PageHeader.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import ReviewSummary from '../components/ReviewSummary.vue'
import ReviewCaseTable from '../components/ReviewCaseTable.vue'
import { reviewApi } from '../review.api'
import type { ReviewCasePage, ReviewSummary as Summary } from '../review.types'

const route = useRoute(); const router = useRouter()
const summary = ref<Summary | null>(null); const page = ref<ReviewCasePage | null>(null)
const loading = ref(true); const error = ref('')
const q = ref(typeof route.query.q === 'string' ? route.query.q : '')
const statusGroup = ref(typeof route.query.status_group === 'string' ? route.query.status_group : '')
const riskLevel = ref(typeof route.query.risk_level === 'string' ? route.query.risk_level : '')
const offset = ref(Number(route.query.offset ?? 0) || 0); const limit = 20
const hasPrevious = computed(() => offset.value > 0); const hasNext = computed(() => page.value ? page.value.offset + page.value.limit < page.value.total : false)

async function load() {
  loading.value = true; error.value = ''
  try {
    const [summaryData, caseData] = await Promise.all([
      reviewApi.getWorkbenchSummary(),
      reviewApi.listWorkbenchCases({ q:q.value || undefined, statusGroup:statusGroup.value || undefined, riskLevel:riskLevel.value || undefined, limit, offset:offset.value }),
    ])
    summary.value = summaryData; page.value = caseData
  } catch { error.value = '暫時無法取得審查工作台，請稍後重試。' }
  finally { loading.value = false }
}

async function applyFilters() { offset.value = 0; await syncQuery(); await load() }
async function syncQuery() { await router.replace({ query:{ ...(q.value && {q:q.value}), ...(statusGroup.value && {status_group:statusGroup.value}), ...(riskLevel.value && {risk_level:riskLevel.value}), ...(offset.value && {offset:String(offset.value)}) } }) }
async function move(delta:number) { offset.value = Math.max(0, offset.value + delta * limit); await syncQuery(); await load() }
function openCase(reviewId:string) { void router.push(`/app/review/cases/${reviewId}`) }
watch(() => route.query, () => {}, { deep:true })
onMounted(load)
</script>
<template>
  <section>
    <PageHeader title="智慧審查工作台" description="案件摘要、風險與待處理工作集中管理。" />
    <LoadingSkeleton v-if="loading && !page" :lines="6" />
    <ErrorState v-else-if="error && !page" :message="error" @retry="load" />
    <template v-else>
      <ReviewSummary v-if="summary" :summary="summary" />
      <form class="filter-bar" @submit.prevent="applyFilters">
        <label>搜尋<input v-model="q" placeholder="案件編號、標題或地區" /></label>
        <label>工作群組<select v-model="statusGroup"><option value="">全部</option><option value="PENDING">待處理</option><option value="ACTIVE">進行中</option><option value="ACTION_REQUIRED">需處理</option><option value="COMPLETED">已完成</option></select></label>
        <label>風險<select v-model="riskLevel"><option value="">全部</option><option value="CRITICAL">重大</option><option value="HIGH">高</option><option value="MEDIUM">中</option><option value="LOW">低</option></select></label>
        <button class="primary-button" type="submit">套用</button>
      </form>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <EmptyState v-if="page && page.items.length === 0" title="沒有符合條件的案件" />
      <ReviewCaseTable v-else-if="page" :items="page.items" @open="openCase" />
      <footer v-if="page" class="pagination"><span>共 {{ page.total }} 件</span><div><button class="text-button" :disabled="!hasPrevious" @click="move(-1)">上一頁</button><button class="text-button" :disabled="!hasNext" @click="move(1)">下一頁</button></div></footer>
    </template>
  </section>
</template>