<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../../components/common/PageHeader.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import RiskBadge from '../../../components/common/RiskBadge.vue'
import StatusBadge from '../../../components/common/StatusBadge.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { useAuthStore } from '../../auth/auth.store'
import EvidenceViewer from '../components/EvidenceViewer.vue'
import FindingPanel from '../components/FindingPanel.vue'
import ReviewActionBar from '../components/ReviewActionBar.vue'
import { reviewApi } from '../review.api'
import type { FindingTriageDecision, FindingViewModel, ReviewCaseDetail, ReviewStartResult } from '../review.types'

const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const reviewId = String(route.params.reviewId)
const detail = ref<ReviewCaseDetail | null>(null); const loading = ref(true); const starting = ref(false); const error = ref('')
const startResult = ref<ReviewStartResult | null>(null); const selectedFinding = ref<FindingViewModel | null>(null); const selectedDocumentId = ref<string>()
const actionBusy = ref(false)
const pendingDecision = ref<{ decision: FindingTriageDecision; reason: string } | null>(null)
const correctionOpen = ref(false); const correctionMessage = ref(''); const correctionDue = ref('')
const blockedItems = computed(() => startResult.value?.outcome === 'BLOCKED' ? startResult.value.missingItems : detail.value?.missingItems ?? [])
const canDecide = computed(() => auth.user?.permissions.includes('review.decide') ?? false)

async function load() {
  loading.value = true; error.value = ''
  const selectedId = selectedFinding.value?.findingId
  try {
    detail.value = await reviewApi.getWorkbenchCase(reviewId)
    selectedFinding.value = detail.value.findings.find((item) => item.findingId === selectedId) ?? detail.value.findings[0] ?? null
    selectedDocumentId.value = selectedFinding.value?.documentId ?? detail.value.documents.find((d) => d.contentAvailable)?.documentId
  } catch { error.value = '暫時無法取得案件審查資料。' }
  finally { loading.value = false }
}

async function confirmFindingDecision() {
  if (!pendingDecision.value || !selectedFinding.value || actionBusy.value) return
  actionBusy.value = true; error.value = ''
  try {
    await reviewApi.triageFinding(reviewId, selectedFinding.value.findingId, pendingDecision.value.decision, pendingDecision.value.reason)
    pendingDecision.value = null
    await load()
  } catch { error.value = '疑點判定未送出。案件可能已被其他操作更新，請重新確認。'; await load() }
  finally { actionBusy.value = false }
}

async function sendCorrection() {
  if (!correctionMessage.value.trim() || !correctionDue.value || actionBusy.value) return
  actionBusy.value = true; error.value = ''
  try {
    const dueAt = new Date(correctionDue.value).toISOString()
    await reviewApi.createAndSendCorrection(reviewId, correctionMessage.value.trim(), dueAt)
    correctionOpen.value = false; correctionMessage.value = ''; correctionDue.value = ''
    await load()
  } catch { error.value = '補正通知未送出，請確認仍有可補正的疑點與期限。'; await load() }
  finally { actionBusy.value = false }
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
      <ReviewActionBar :starting="starting" :can-start="detail.status !== 'REVIEW_COMPLETED'" :can-correct="canDecide && detail.findings.length > 0" :can-complete="canDecide && detail.findings.length > 0" @start="startReview" @correct="correctionOpen=true" @complete="goResult" />
      <section v-if="blockedItems.length" class="blocked-panel solid-panel">
        <h2>缺件／待補資料</h2><ul><li v-for="item in blockedItems" :key="item.missingItemId"><strong>{{ item.itemName }}</strong> — {{ item.reason ?? item.status }}</li></ul>
      </section>
      <div class="workbench-grid">
        <aside class="workbench-nav solid-panel">
          <h2>文件</h2><button v-for="doc in detail.documents" :key="doc.documentId" type="button" :disabled="!doc.contentAvailable" @click="selectedDocumentId=doc.documentId">{{ doc.filename }}</button>
          <h2>疑點</h2><button v-for="finding in detail.findings" :key="finding.findingId" type="button" :class="{ selected:selectedFinding?.findingId===finding.findingId }" @click="chooseFinding(finding)">{{ finding.severityLabel }}｜{{ finding.title }}</button>
        </aside>
        <EvidenceViewer :review-id="reviewId" :document-id="selectedDocumentId" />
        <FindingPanel :finding="selectedFinding" :can-decide="canDecide" :busy="actionBusy" @select-document="selectedDocumentId=$event" @request-decision="pendingDecision=$event" />
      </div>
    </template>
    <GlassModal :open="Boolean(pendingDecision)" title="確認疑點判定" @close="pendingDecision=null">
      <p>判定送出後會寫入審查決策紀錄。請確認理由與選項正確。</p>
      <p v-if="pendingDecision"><strong>{{ pendingDecision.decision }}</strong> — {{ pendingDecision.reason }}</p>
      <div class="modal-actions"><button class="text-button" type="button" @click="pendingDecision=null">取消</button><button class="primary-button" type="button" :disabled="actionBusy" @click="confirmFindingDecision">確認送出</button></div>
    </GlassModal>
    <GlassModal :open="correctionOpen" title="送出補正通知" @close="correctionOpen=false">
      <form class="decision-form" @submit.prevent="sendCorrection">
        <label>補正內容<textarea v-model="correctionMessage" required maxlength="4000" rows="5" /></label>
        <label>補正期限<input v-model="correctionDue" type="datetime-local" required /></label>
        <div class="modal-actions"><button class="text-button" type="button" @click="correctionOpen=false">取消</button><button class="primary-button" type="submit" :disabled="actionBusy || !correctionMessage.trim() || !correctionDue">建立並送出</button></div>
      </form>
    </GlassModal>
  </section>
</template>