<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../../../components/common/PageHeader.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import RiskBadge from '../../../components/common/RiskBadge.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { useAuthStore } from '../../auth/auth.store'
import { reviewApi } from '../review.api'
import type { GeneratedReportDto, ReviewCaseDetail, ReviewReportDto } from '../review.types'

const route = useRoute(); const auth = useAuthStore(); const reviewId = String(route.params.reviewId)
const detail = ref<ReviewCaseDetail | null>(null); const report = ref<ReviewReportDto | null>(null)
const loading = ref(true); const error = ref(''); const actionBusy = ref(false); const completeOpen = ref(false); const completeReason = ref('')
const canDecide = computed(() => auth.user?.permissions.includes('review.decide') ?? false)
const latestRunId = computed(() => detail.value?.runs.at(-1)?.runId)
const unresolvedCount = computed(() => detail.value?.findings.filter((f) => !['RESOLVED','DISMISSED'].includes(f.status)).length ?? 0)

async function load() {
  loading.value = true; error.value = ''
  try {
    detail.value = await reviewApi.getWorkbenchCase(reviewId)
    if (detail.value.runs.length) report.value = await reviewApi.getStructuredReport(detail.value.runs.at(-1)!.runId)
  } catch { error.value = '暫時無法載入審查結果。' }
  finally { loading.value = false }
}

async function completeReview() {
  if (!completeReason.value.trim()) return
  actionBusy.value = true
  try { await reviewApi.completeReview(reviewId, completeReason.value.trim()); completeOpen.value = false; await load() }
  catch { error.value = '目前無法完成審查，可能仍有未處理疑點。請重新確認案件狀態。' }
  finally { actionBusy.value = false }
}

async function createAndDownload(format: 'pdf' | 'xlsx' | 'docx') {
  if (!latestRunId.value) return
  actionBusy.value = true
  try {
    const meta: GeneratedReportDto = format === 'pdf'
      ? await reviewApi.generatePdfReport(latestRunId.value)
      : await reviewApi.generateReport(latestRunId.value, format)
    const blob = await reviewApi.downloadReport(meta.document_id)
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = meta.original_filename; a.click(); URL.revokeObjectURL(url)
  } catch { error.value = '報告產生或下載失敗，請稍後重試。' }
  finally { actionBusy.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <PageHeader title="審查結果與報告" :description="detail ? `${detail.caseNo}｜${detail.title}` : undefined">
      <button v-if="canDecide && detail?.status !== 'REVIEW_COMPLETED'" class="primary-button" type="button" @click="completeOpen=true">完成審查</button>
    </PageHeader>
    <LoadingSkeleton v-if="loading && !detail" :lines="6" />
    <ErrorState v-else-if="error && !detail" :message="error" @retry="load" />
    <template v-else-if="detail">
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <section class="result-summary solid-panel"><div><span>案件狀態</span><strong>{{ detail.statusLabel }}</strong></div><div><span>風險</span><RiskBadge :level="detail.riskLevel" /></div><div><span>未處理疑點</span><strong>{{ unresolvedCount }}</strong></div></section>
      <section class="report-actions solid-panel"><h2>報告</h2><div><button class="text-button" :disabled="actionBusy || !latestRunId" @click="createAndDownload('pdf')">PDF</button><button class="text-button" :disabled="actionBusy || !latestRunId" @click="createAndDownload('xlsx')">XLSX</button><button class="text-button" :disabled="actionBusy || !latestRunId" @click="createAndDownload('docx')">DOCX</button></div></section>
      <section v-if="report" class="report-content solid-panel">
        <h2>結構化審查報告</h2>
        <p><strong>規則/機器結果：</strong>{{ report.findings.length }} 項疑點；風險 {{ report.risk_summary.overall_risk_level }}</p>
        <article v-for="finding in report.findings" :key="finding.finding_id" class="report-finding">
          <h3>{{ finding.finding_code }}｜{{ finding.title }}</h3><p>{{ finding.description }}</p>
          <p v-if="finding.ai_assessment.reasoning_summary"><strong>AI 說明：</strong>{{ finding.ai_assessment.reasoning_summary }}</p>
          <p v-if="finding.decisions.length"><strong>人工結論：</strong>{{ finding.decisions.at(-1)?.decision }} — {{ finding.decisions.at(-1)?.reason }}</p>
        </article>
      </section>
    </template>
    <GlassModal :open="completeOpen" title="確認完成審查" @close="completeOpen=false">
      <p>目前未處理疑點：{{ unresolvedCount }}。後端會再次驗證是否允許完成。</p>
      <label>完成理由<textarea v-model="completeReason" required maxlength="2000" rows="4" /></label>
      <div class="modal-actions"><button class="text-button" @click="completeOpen=false">取消</button><button class="primary-button" :disabled="actionBusy || !completeReason.trim()" @click="completeReview">確認完成</button></div>
    </GlassModal>
  </section>
</template>