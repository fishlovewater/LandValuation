<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../../components/common/PageHeader.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import RiskBadge from '../../../components/common/RiskBadge.vue'
import StatusBadge from '../../../components/common/StatusBadge.vue'
import EvidenceViewer from '../components/EvidenceViewer.vue'
import FindingPanel from '../components/FindingPanel.vue'
import ReviewActionBar from '../components/ReviewActionBar.vue'
import { reviewApi } from '../review.api'
import type { FindingViewModel, ReviewCaseDetail, ReviewStartResult } from '../review.types'

const route = useRoute(); const router = useRouter(); const reviewId = String(route.params.reviewId)
const detail = ref<ReviewCaseDetail | null>(null); const loading = ref(true); const starting = ref(false); const error = ref('')
const startResult = ref<ReviewStartResult | null>(null); const selectedFinding = ref<FindingViewModel | null>(null); const selectedDocumentId = ref<string>()
const blockedItems = computed(() => startResult.value?.outcome === 'BLOCKED' ? startResult.value.missingItems : detail.value?.missingItems ?? [])

async function load() {
  loading.value = true; error.value = ''
  try {
    detail.value = await reviewApi.getWorkbenchCase(reviewId)
    selectedFinding.value = detail.value.findings[0] ?? null
    selectedDocumentId.value = selectedFinding.value?.documentId ?? detail.value.documents.find((d) => d.contentAvailable)?.documentId
  } catch { error.value = '暫時無法取得案件審查資料。' }
  finally { loading.value = false }
}

async function startReview() {
  if (starting.value) return
  starting.value = true; error.value = ''
  try {
    startResult.value = await reviewApi.startWorkbenchCase(reviewId)
    if (startResult.value.outcome === 'COMPLETED') await load()
  } catch { error.value = '無法啟動審查。案件狀態可能已變更，請重新載入。' }
  finally { starting.value = false }
}

function chooseFinding(finding: FindingViewModel) { selectedFinding.value = finding; if (finding.documentId) selectedDocumentId.value = finding.documentId }
function goResult() { void router.push(`/app/review/cases/${reviewId}/result`) }
onMounted(load)
</script>

<template>
  <section>
    <PageHeader v-if="detail" :title="`${detail.caseNo}｜${detail.title}`" :description="detail.district">
      <div class="header-badges"><StatusBadge :status="detail.status" /><RiskBadge :level="detail.riskLevel" /></div>
    </PageHeader>
    <LoadingSkeleton v-if="loading && !detail" :lines="7" />
    <ErrorState v-else-if="error && !detail" :message="error" @retry="load" />
    <template v-else-if="detail">
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <ReviewActionBar :starting="starting" :can-start="detail.status !== 'REVIEW_COMPLETED'" :can-complete="detail.findings.length > 0" @start="startReview" @complete="goResult" />
      <section v-if="blockedItems.length" class="blocked-panel solid-panel">
        <h2>缺件／待補資料</h2><ul><li v-for="item in blockedItems" :key="item.missingItemId"><strong>{{ item.itemName }}</strong> — {{ item.reason ?? item.status }}</li></ul>
      </section>
      <div class="workbench-grid">
        <aside class="workbench-nav solid-panel">
          <h2>文件</h2><button v-for="doc in detail.documents" :key="doc.documentId" type="button" :disabled="!doc.contentAvailable" @click="selectedDocumentId=doc.documentId">{{ doc.filename }}</button>
          <h2>疑點</h2><button v-for="finding in detail.findings" :key="finding.findingId" type="button" :class="{ selected:selectedFinding?.findingId===finding.findingId }" @click="chooseFinding(finding)">{{ finding.severityLabel }}｜{{ finding.title }}</button>
        </aside>
        <EvidenceViewer :review-id="reviewId" :document-id="selectedDocumentId" />
        <FindingPanel :finding="selectedFinding" @select-document="selectedDocumentId=$event" />
      </div>
    </template>
  </section>
</template>