<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import type { ComparisonSetupContextDto, ComparisonSetupTargetDto, ReportPageResponseDto } from '../valuation.types'

interface TargetDraft {
  transactionNo: string
  transactionDate: string
  transactionTotalPrice: string
  normalLandUnitPrice: string
  weight: string
  sourceNotes: string
  subjectAddress: string
  landAreaSqm: string
}

const props = defineProps<{ caseId: string; reportId: string; page: ReportPageResponseDto }>()
const emit = defineEmits<{ changed: [] }>()

const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const context = ref<ComparisonSetupContextDto | null>(null)
const enabled = ref(true)
const targetCount = ref(1)
const benchmarkLandId = ref('')
const existingAnalysisId = ref('')
const notes = ref('')
const targets = reactive<TargetDraft[]>([])

function blankTarget(): TargetDraft {
  return {
    transactionNo: '', transactionDate: '', transactionTotalPrice: '', normalLandUnitPrice: '',
    weight: '', sourceNotes: '', subjectAddress: '', landAreaSqm: '',
  }
}

function syncTargetCount(): void {
  const count = Math.min(3, Math.max(1, Number(targetCount.value) || 1))
  targetCount.value = count
  while (targets.length < count) targets.push(blankTarget())
  while (targets.length > count) targets.pop()
}

const currentAnalysisId = computed(() => typeof props.page.data.comparison_analysis_id === 'string' ? props.page.data.comparison_analysis_id : null)
const currentBenchmarkLandId = computed(() => typeof props.page.data.benchmark_land_id === 'string' ? props.page.data.benchmark_land_id : null)
const weightTotal = computed(() => targets.reduce((sum, target) => {
  const value = Number(target.weight)
  return sum + (Number.isFinite(value) ? value : 0)
}, 0))
const weightsValid = computed(() => targets.length >= 1 && targets.length <= 3 && targets.every((target) => {
  const value = Number(target.weight)
  return Number.isFinite(value) && value > 0 && value <= 1
}) && Math.abs(weightTotal.value - 1) < 1e-9)
const createReady = computed(() => Boolean(
  enabled.value && benchmarkLandId.value && weightsValid.value && targets.every((target) => (
    target.transactionNo.trim()
    && target.transactionNo.trim().length <= 30
    && target.transactionDate
    && Number(target.transactionTotalPrice) > 0
    && Number(target.normalLandUnitPrice) > 0
    && target.sourceNotes.trim()
    && target.subjectAddress.length <= 300
    && (!target.landAreaSqm || Number(target.landAreaSqm) > 0)
  )) && new Set(targets.map((target) => target.transactionNo.trim())).size === targets.length,
))

async function loadContext(): Promise<void> {
  if (!props.caseId || !props.reportId) return
  loading.value = true
  error.value = ''
  try {
    const result = await valuationApi.getComparisonSetup(props.caseId)
    context.value = result
    benchmarkLandId.value = currentBenchmarkLandId.value ?? result.benchmark_lands[0]?.benchmark_land_id ?? ''
    existingAnalysisId.value = currentAnalysisId.value ?? ''
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    loading.value = false
  }
}

async function setEnabled(next: boolean): Promise<void> {
  if (busy.value || props.page.form_status !== 'DRAFT') return
  const previous = enabled.value
  enabled.value = next
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await valuationApi.updateReportPage(props.caseId, props.reportId, 'F02', { comparison_workflow_enabled: next })
    notice.value = next
      ? '已啟用比較分析；正式計算前請建立或套用一組可追溯的比較分析。'
      : '已停用本報告的比較分析；正式計算將依後端規則走不使用比較標的的合法流程。'
    emit('changed')
  } catch (caught: unknown) {
    enabled.value = previous
    error.value = safeValuationErrorMessage(caught)
  } finally {
    busy.value = false
  }
}

async function createSetup(): Promise<void> {
  if (!createReady.value || busy.value || props.page.form_status !== 'DRAFT') return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const payloadTargets: ComparisonSetupTargetDto[] = targets.map((target) => ({
      transaction_no: target.transactionNo.trim(), transaction_date: target.transactionDate,
      transaction_total_price: target.transactionTotalPrice.trim(), normal_land_unit_price: target.normalLandUnitPrice.trim(),
      weight: target.weight.trim(), source_notes: target.sourceNotes.trim(), subject_address: target.subjectAddress.trim() || null,
      land_area_sqm: target.landAreaSqm.trim() || null,
    }))
    const created = await valuationApi.createComparisonSetup(props.caseId, {
      report_id: props.reportId, benchmark_land_id: benchmarkLandId.value, targets: payloadTargets, notes: notes.value.trim() || null,
    })
    existingAnalysisId.value = created.comparison_analysis_id
    notice.value = `比較分析已建立並寫入正式 F02 / F02-RF，共 ${created.targets.length} 筆比較標的。`
    await loadContext()
    emit('changed')
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    busy.value = false
  }
}

async function applyExisting(): Promise<void> {
  if (!enabled.value || !existingAnalysisId.value || busy.value || props.page.form_status !== 'DRAFT') return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const applied = await valuationApi.applyComparisonSetup(props.caseId, {
      report_id: props.reportId, comparison_analysis_id: existingAnalysisId.value,
    })
    notice.value = `已套用既有比較分析，共 ${applied.targets.length} 筆比較標的。`
    emit('changed')
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    busy.value = false
  }
}

watch(() => [props.caseId, props.reportId, props.page.version_no, props.page.data] as const, () => {
  enabled.value = props.page.data.comparison_workflow_enabled !== false
  syncTargetCount()
  void loadContext()
}, { immediate: true, deep: true })
watch(targetCount, syncTargetCount)
</script>

<template>
  <section class="comparison-setup" data-testid="comparison-setup" tabindex="-1" aria-labelledby="comparison-setup-title">
    <header class="comparison-setup__header">
      <div>
        <p>STRUCTURED COMPARISON</p>
        <h3 id="comparison-setup-title">比較法設定</h3>
        <span>比準地、交易案例與權重由正式後端流程建立，不需要輸入資料庫 UUID 或修改 raw JSON。</span>
      </div>
      <label class="comparison-setup__toggle">
        <input :checked="enabled" type="checkbox" data-testid="comparison-workflow-enabled" :disabled="busy || page.form_status !== 'DRAFT'" @change="setEnabled(($event.target as HTMLInputElement).checked)">
        <span>啟用比較分析</span>
      </label>
    </header>
    <p class="comparison-setup__rule-note">正式規則版本由伺服器依案件類型、行政區、土地使用與有效日期自動選用；一般使用者不需手動輸入 rule version ID。</p>
    <p v-if="loading" class="comparison-setup__muted">正在載入比較分析資料…</p>
    <p v-if="error" class="comparison-setup__error" role="alert">{{ error }}</p>
    <p v-if="notice" class="comparison-setup__notice" role="status">{{ notice }}</p>

    <template v-if="!loading && context">
      <div v-if="!enabled" class="comparison-setup__disabled" data-testid="comparison-disabled-note">本報告目前不使用比較標的。正式計算仍由伺服器執行，且不會要求比準地、比較分析或比較標的。</div>
      <template v-else>
        <section class="comparison-setup__existing" aria-labelledby="existing-comparison-title">
          <div><strong id="existing-comparison-title">套用既有分析</strong><span>{{ currentAnalysisId ? '目前正式頁面已連結一組比較分析。' : '若此案件已有可用分析，可直接套用到目前報告版本。' }}</span></div>
          <select v-model="existingAnalysisId" data-testid="comparison-existing-analysis"><option value="">請選擇既有分析</option><option v-for="analysis in context.analyses" :key="analysis.comparison_analysis_id" :value="analysis.comparison_analysis_id">{{ analysis.label }} · {{ analysis.analysis_status }}</option></select>
          <button type="button" data-testid="apply-comparison-setup" :disabled="busy || !existingAnalysisId || page.form_status !== 'DRAFT'" @click="applyExisting">套用既有分析</button>
        </section>

        <form class="comparison-setup__form" @submit.prevent="createSetup">
          <div class="comparison-setup__base-grid">
            <label><span>比準地 *</span><select v-model="benchmarkLandId" data-testid="comparison-benchmark-land" required><option value="">請選擇比準地</option><option v-for="benchmark in context.benchmark_lands" :key="benchmark.benchmark_land_id" :value="benchmark.benchmark_land_id">{{ benchmark.label }}</option></select></label>
            <label><span>比較案例數 *</span><select v-model.number="targetCount" data-testid="comparison-target-count"><option :value="1">1 筆</option><option :value="2">2 筆</option><option :value="3">3 筆</option></select></label>
            <label class="comparison-setup__wide"><span>分析備註</span><input v-model="notes" maxlength="3000" type="text" placeholder="例如：交易案例篩選與來源說明"></label>
          </div>
          <div class="comparison-setup__targets">
            <fieldset v-for="(target, index) in targets" :key="index">
              <legend>比較案例 {{ index + 1 }}</legend>
              <div class="comparison-setup__target-grid">
                <label><span>交易編號 *</span><input v-model.trim="target.transactionNo" :data-testid="`comparison-transaction-no-${index}`" maxlength="30" required></label>
                <label><span>交易日期 *</span><input v-model="target.transactionDate" :data-testid="`comparison-transaction-date-${index}`" type="date" required></label>
                <label><span>交易總價 *</span><input v-model.trim="target.transactionTotalPrice" :data-testid="`comparison-total-price-${index}`" inputmode="decimal" required></label>
                <label><span>正常土地單價 *</span><input v-model.trim="target.normalLandUnitPrice" :data-testid="`comparison-unit-price-${index}`" inputmode="decimal" required></label>
                <label><span>權重 *</span><input v-model.trim="target.weight" :data-testid="`comparison-weight-${index}`" inputmode="decimal" placeholder="例如 0.5" required></label>
                <label><span>土地面積 m²</span><input v-model.trim="target.landAreaSqm" inputmode="decimal"></label>
                <label class="comparison-setup__wide"><span>地址</span><input v-model.trim="target.subjectAddress" maxlength="300"></label>
                <label class="comparison-setup__wide"><span>來源說明 *</span><textarea v-model.trim="target.sourceNotes" :data-testid="`comparison-source-notes-${index}`" maxlength="1000" rows="2" required /></label>
              </div>
            </fieldset>
          </div>
          <footer class="comparison-setup__footer">
            <div :data-valid="weightsValid ? 'true' : 'false'"><strong>權重合計 {{ weightTotal.toFixed(6) }}</strong><span>{{ weightsValid ? '符合 1.000000' : '所有權重須大於 0、最多 1，且合計必須等於 1' }}</span></div>
            <button type="submit" data-testid="create-comparison-setup" :disabled="busy || !createReady || page.form_status !== 'DRAFT'">{{ busy ? '處理中…' : '建立比較分析並套用' }}</button>
          </footer>
        </form>
      </template>
    </template>
  </section>
</template>

<style scoped>
.comparison-setup { display:grid; gap:14px; margin-bottom:14px; padding:16px; border:1px solid var(--app-line); border-radius:var(--app-radius-sm); background:rgba(246,250,255,.78); }
.comparison-setup__header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.comparison-setup__header p { margin:0 0 4px; color:#2e5984; font-size:9px; font-weight:900; letter-spacing:.13em; }
.comparison-setup__header h3 { margin:0; color:var(--app-ink); font-size:17px; }
.comparison-setup__header div > span { display:block; max-width:680px; margin-top:5px; color:var(--app-muted); font-size:11px; line-height:1.55; }
.comparison-setup__toggle { display:flex; align-items:center; gap:7px; min-height:38px; padding:7px 10px; border:1px solid var(--app-line); border-radius:8px; background:#fff; color:var(--app-ink-soft); font-size:11px; font-weight:900; white-space:nowrap; }
.comparison-setup__toggle input { width:16px; height:16px; }
.comparison-setup__rule-note,.comparison-setup__disabled { margin:0; padding:10px 12px; border-radius:8px; color:#2e5984; background:#edf4fb; font-size:11px; line-height:1.6; }
.comparison-setup__disabled { color:var(--app-ink-soft); background:#f7f8fb; }
.comparison-setup__muted { margin:0; color:var(--app-muted); font-size:11px; }
.comparison-setup__error,.comparison-setup__notice { margin:0; padding:9px 11px; border-radius:8px; font-size:11px; line-height:1.55; }
.comparison-setup__error { color:#a44334; background:#fff0ed; }.comparison-setup__notice { color:var(--app-green); background:rgba(59,129,102,.08); }
.comparison-setup__existing { display:grid; grid-template-columns:minmax(190px,1fr) minmax(220px,1fr) auto; align-items:end; gap:10px; padding:12px; border:1px solid var(--app-line); border-radius:9px; background:rgba(255,255,255,.72); }
.comparison-setup__existing > div { display:grid; gap:3px; }.comparison-setup__existing strong { color:var(--app-ink); font-size:12px; }.comparison-setup__existing span { color:var(--app-muted); font-size:10px; }
.comparison-setup__existing select,.comparison-setup__existing button,.comparison-setup input,.comparison-setup select,.comparison-setup textarea { min-height:40px; padding:7px 9px; border:1px solid var(--app-line); border-radius:8px; color:var(--app-ink); background:#fff; font:inherit; font-size:11px; }
.comparison-setup button { cursor:pointer; font-weight:900; }.comparison-setup button:disabled { cursor:not-allowed; opacity:.5; }
.comparison-setup__form { display:grid; gap:12px; }.comparison-setup__base-grid,.comparison-setup__target-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
.comparison-setup label { display:grid; gap:5px; color:var(--app-ink-soft); font-size:10px; font-weight:800; }.comparison-setup__wide { grid-column:1 / -1; }
.comparison-setup__targets { display:grid; gap:10px; }.comparison-setup fieldset { margin:0; padding:12px; border:1px solid var(--app-line); border-radius:9px; background:rgba(255,255,255,.76); }.comparison-setup legend { padding:0 6px; color:var(--app-ink); font-size:11px; font-weight:900; }.comparison-setup textarea { resize:vertical; }
.comparison-setup__footer { display:flex; align-items:center; justify-content:space-between; gap:14px; padding-top:12px; border-top:1px solid var(--app-line); }.comparison-setup__footer > div { display:grid; gap:3px; }.comparison-setup__footer strong { color:var(--app-ink); font-size:12px; }.comparison-setup__footer span { color:var(--app-muted); font-size:10px; }.comparison-setup__footer [data-valid="false"] strong { color:#a44334; }
.comparison-setup__footer button,.comparison-setup__existing button { min-height:40px; padding:8px 12px; border:1px solid var(--app-accent); border-radius:8px; color:#fff; background:var(--app-accent); }
@media (max-width:760px) { .comparison-setup__header,.comparison-setup__footer { align-items:stretch; flex-direction:column; }.comparison-setup__toggle { justify-content:flex-start; }.comparison-setup__existing,.comparison-setup__base-grid,.comparison-setup__target-grid { grid-template-columns:1fr; }.comparison-setup__wide { grid-column:auto; }.comparison-setup__footer button,.comparison-setup__existing button { width:100%; } }
</style>