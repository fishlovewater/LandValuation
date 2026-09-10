<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { useAuthStore } from '../../../stores/auth.store'
import { statusLabel } from '../../../utils/enumLabels'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import {
  mapBenchmarkLandResponse,
  mapCalculationResponse,
  mapCaseResponse,
  mapDocumentResponse,
  mapF03DraftResponse,
  mapF03Update,
  mapFormResponse,
  mapReportResponse,
  mapValidationResponse,
  selectAuthoritativeF02,
  sourceForCalculatedValue,
} from '../valuation.mappers'
import {
  resetValuationFlow,
  valuationFlowState,
  type DocumentCategory,
  type F03EditableValues,
  type ValuationFormModel,
} from '../valuation.types'
import ValuationStepNavigator from '../components/ValuationStepNavigator.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const flow = valuationFlowState
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const uploading = ref(false)
const dirty = ref(false)
const error = ref('')
const notice = ref('')
const uploadCategory = ref<DocumentCategory>('original')
const uploadFile = ref<File | null>(null)

const draft = reactive<F03EditableValues>({
  benchmarkLandId: null,
  comparisonAnalysisId: null,
  valuationBaseDate: null,
  comparisonPrice: null,
  comparisonWeight: null,
  incomePrice: null,
  incomeWeight: null,
  marketPeriodStart: null,
  marketPeriodEnd: null,
  marketCondition: null,
  selectionScopeReason: null,
  decisionReason: null,
})

const caseId = computed(() => String(route.params.caseId ?? ''))
const f03Form = computed<ValuationFormModel | null>(
  () => flow.forms.find((form) => form.formCode === 'F03') ?? null,
)
const calculatedSource = sourceForCalculatedValue()
const canUpload = computed(() => auth.permissions.includes('document.upload'))
let activeCaseToken = 0

function emptyDraft(): F03EditableValues {
  return {
    benchmarkLandId: null,
    comparisonAnalysisId: null,
    valuationBaseDate: null,
    comparisonPrice: null,
    comparisonWeight: null,
    incomePrice: null,
    incomeWeight: null,
    marketPeriodStart: null,
    marketPeriodEnd: null,
    marketCondition: null,
    selectionScopeReason: null,
    decisionReason: null,
  }
}

function isCurrentCase(token: number, requestedCaseId: string): boolean {
  return token === activeCaseToken && requestedCaseId === caseId.value
}

function copyDraft(): void {
  if (!flow.f03) return
  Object.assign(draft, flow.f03.editable)
  dirty.value = false
}

async function loadF03(form: ValuationFormModel, token: number, requestedCaseId: string): Promise<void> {
  const dto = await valuationApi.getF03(requestedCaseId, form.formInstanceId)
  if (!isCurrentCase(token, requestedCaseId)) return
  flow.f03 = mapF03DraftResponse(dto, form.sourceDocumentId, form.formInstanceId)
  copyDraft()
}

async function loadData(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = ++activeCaseToken
  resetValuationFlow()
  Object.assign(draft, emptyDraft())
  dirty.value = false
  saving.value = false
  running.value = false
  error.value = ''
  notice.value = ''

  if (!requestedCaseId) {
    error.value = '找不到案件識別資訊，請從估價案件清單重新進入。'
    loading.value = false
    return
  }

  loading.value = true
  try {
    const [caseDto, formDtos, benchmarkDtos, documentDtos, reportProgressDto] = await Promise.all([
      valuationApi.getCase(requestedCaseId),
      valuationApi.listForms(requestedCaseId),
      valuationApi.listBenchmarkLands(requestedCaseId),
      valuationApi.listDocuments(requestedCaseId),
      valuationApi.getReportProgress(requestedCaseId),
    ])
    if (!isCurrentCase(token, requestedCaseId)) return

    const forms = formDtos.map(mapFormResponse)
    const form = forms.find((item) => item.formCode === 'F03')
    const documents = documentDtos.map(mapDocumentResponse)
    const authoritative = selectAuthoritativeF02(forms, documents, reportProgressDto)

    flow.case = mapCaseResponse(caseDto)
    flow.forms = forms
    flow.benchmarks = benchmarkDtos.map(mapBenchmarkLandResponse)
    flow.documents = documents
    flow.authoritativeF02 = authoritative.form
    flow.completeReport = authoritative.completeReport
    flow.reportPackageId = authoritative.reportPackageId
    if (form) {
      try {
        await loadF03(form, token, requestedCaseId)
      } catch {
        if (isCurrentCase(token, requestedCaseId)) {
          notice.value = 'F03 表單已建立，但正式估價草稿尚未初始化；可先上傳來源文件並補齊宗地／比準地資料。'
        }
      }
    } else {
      notice.value = '目前案件尚未建立 F03 估價表；可先補齊來源文件，再建立需要的估價表。'
    }
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) loading.value = false
  }
}

function chooseUpload(event: Event): void {
  const input = event.target as HTMLInputElement
  uploadFile.value = input.files?.[0] ?? null
}

async function uploadSourceDocument(): Promise<void> {
  if (!flow.case || !uploadFile.value || !canUpload.value || uploading.value) return
  uploading.value = true
  error.value = ''
  notice.value = ''
  try {
    const uploaded = await valuationApi.uploadDocument(flow.case.caseId, uploadCategory.value, uploadFile.value)
    flow.documents = [mapDocumentResponse(uploaded), ...flow.documents.filter((item) => item.documentId !== uploaded.document_id)]
    notice.value = `${uploaded.original_filename} 已上傳完成，檔案版本與儲存狀態已由伺服器確認。`
    uploadFile.value = null
    const input = document.querySelector<HTMLInputElement>('#valuation-source-file')
    if (input) input.value = ''
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    uploading.value = false
  }
}

async function saveConfirmedFields(
  token = activeCaseToken,
  requestedCaseId = caseId.value,
): Promise<boolean> {
  const form = f03Form.value
  if (!form || !isCurrentCase(token, requestedCaseId)) return false

  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const updated = await valuationApi.updateF03(requestedCaseId, form.formInstanceId, mapF03Update(draft))
    if (!isCurrentCase(token, requestedCaseId)) return false
    flow.f03 = mapF03DraftResponse(updated, form.sourceDocumentId, form.formInstanceId)
    copyDraft()
    notice.value = '人工確認欄位已由伺服器儲存並重新載入。'
    return true
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return false
    error.value = safeValuationErrorMessage(caught)
    return false
  } finally {
    if (isCurrentCase(token, requestedCaseId)) saving.value = false
  }
}

function handleSave(): void {
  void saveConfirmedFields()
}

async function runValuation(): Promise<void> {
  const requestedCaseId = caseId.value
  const token = activeCaseToken
  const form = f03Form.value
  if (!form || !flow.f03 || !isCurrentCase(token, requestedCaseId)) return

  running.value = true
  error.value = ''
  notice.value = ''
  if (form.status === 'DRAFT') flow.calculation = null
  flow.validation = null
  flow.report = null
  try {
    if (dirty.value && !(await saveConfirmedFields(token, requestedCaseId))) return
    if (!isCurrentCase(token, requestedCaseId)) return

    let currentForm = f03Form.value
    if (!currentForm || !flow.f03) return

    if (currentForm.status !== 'DRAFT') {
      notice.value = '目前 F03 已不是草稿狀態，請重新載入案件後再執行。'
      return
    }

    const calculation = await valuationApi.calculate(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.calculation = mapCalculationResponse(calculation)
    flow.f03 = {
      ...flow.f03,
      benchmarkLandPrice: flow.calculation.result,
      source: sourceForCalculatedValue(),
    }

    const validation = await valuationApi.validate(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.validation = mapValidationResponse(validation)

    if (!flow.validation.canGenerateReport) {
      notice.value = '伺服器檢核回傳阻擋項目，請依結果補正後再執行。'
      return
    }

    const submitted = await valuationApi.submitForm(requestedCaseId, currentForm.formInstanceId)
    if (!isCurrentCase(token, requestedCaseId)) return
    const submittedForm = mapFormResponse(submitted)
    flow.forms = flow.forms.map((item) =>
      item.formInstanceId === submittedForm.formInstanceId ? submittedForm : item,
    )
    if (submittedForm.status !== 'READY') {
      notice.value = '伺服器未將 F03 轉為 READY，暫停正式輸出。'
      return
    }
    currentForm = f03Form.value
    if (!currentForm || !isCurrentCase(token, requestedCaseId)) return

    const report = await valuationApi.generateReport(requestedCaseId, {
      form_instance_id: currentForm.formInstanceId,
    })
    if (!isCurrentCase(token, requestedCaseId)) return
    flow.report = mapReportResponse(report)
    notice.value = '伺服器已完成計算、檢核、F03 提交與正式輸出。'
  } catch (caught: unknown) {
    if (!isCurrentCase(token, requestedCaseId)) return
    error.value = safeValuationErrorMessage(caught)
  } finally {
    if (isCurrentCase(token, requestedCaseId)) running.value = false
  }
}

function goToSubmit(): void {
  if (!flow.validation) return
  void router.push({ name: 'valuation-submit', params: { caseId: caseId.value } })
}

watch(caseId, () => {
  void loadData()
}, { immediate: true })
</script>

<template>
  <div class="valuation-view">
    <ValuationStepNavigator :current-stage="2" />
    <PageHeader
      eyebrow="CASE PREPARATION"
      title="確認估價資料"
      description="保留六步驟作業心智模型；Demo 僅編輯 API 明確支援的 F03 確認欄位。"
    />

    <LoadingSkeleton v-if="loading" :rows="7" label="案件估價資料載入中" />
    <ErrorState v-else-if="error && !flow.case" :message="error" @retry="loadData" />

    <template v-else-if="flow.case">
      <section v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="case-summary-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">案件與文件</p>
            <h2 id="case-summary-title">{{ flow.case.caseNo }}｜{{ flow.case.name }}</h2>
          </div>
          <span class="source-marker" data-source-kind="automatic">{{ flow.case.source.label }}</span>
        </div>
        <div class="summary-grid">
          <div><span>案件類型</span><strong>{{ flow.case.caseType }}</strong></div>
          <div><span>申請機關</span><strong>{{ flow.case.requestingAgency || '未提供' }}</strong></div>
          <div><span>估價基準日</span><strong>{{ flow.case.valuationBaseDate }}</strong></div>
          <div><span>行政區</span><strong>{{ flow.case.districtCode }}</strong></div>
        </div>
        <div class="form-list" aria-label="已發現估價表">
          <div v-for="form in flow.forms" :key="form.formInstanceId" class="form-list__item">
            <strong>{{ form.formCode }}</strong>
            <span>第 {{ form.versionNo }} 版｜{{ statusLabel(form.status) }}</span>
            <small>{{ form.source.label }}</small>
          </div>
        </div>
        <div class="document-workspace">
          <div class="document-workspace__heading">
            <div>
              <strong>來源文件</strong>
              <span>檔名、格式、版本與上傳狀態以後端文件紀錄為準。</span>
            </div>
            <span>{{ flow.documents.length }} 份</span>
          </div>
          <ul v-if="flow.documents.length" class="document-list">
            <li v-for="document in flow.documents" :key="document.documentId">
              <div><strong>{{ document.filename }}</strong><span>{{ document.documentType }} · v{{ document.versionNo }}</span></div>
              <span>{{ document.isActive ? '已上傳' : '非作用版本' }}</span>
            </li>
          </ul>
          <p v-else class="empty-copy">尚未上傳案件來源文件。</p>
          <form v-if="canUpload" class="upload-form" @submit.prevent="uploadSourceDocument">
            <label><span>文件類型</span>
              <select v-model="uploadCategory">
                <option value="original">原始文件</option>
                <option value="cadastral-map">地籍圖</option>
                <option value="land-register">土地登記資料</option>
                <option value="photos">照片</option>
                <option value="attachments">其他附件</option>
                <option value="map-section-sketch">地段示意圖</option>
                <option value="map-zoning">使用分區圖</option>
                <option value="map-land-value-section">地價區段圖</option>
              </select>
            </label>
            <label class="upload-form__file"><span>選擇檔案</span><input id="valuation-source-file" type="file" required @change="chooseUpload" /></label>
            <button class="solid-button" type="submit" :disabled="uploading || !uploadFile">
              {{ uploading ? '上傳中…' : '上傳文件' }}
            </button>
          </form>
        </div>
        <p class="source-note">來源證據：案件原始資料（由後端案件讀取結果提供）</p>
      </section>

      <section v-if="!flow.f03" v-liquid-glass data-lg class="valuation-surface setup-required lg" aria-labelledby="setup-required-title">
        <div>
          <p class="valuation-eyebrow">REQUIRED DATA</p>
          <h2 id="setup-required-title">估價資料尚未可計算</h2>
        </div>
        <p>系統不會以空值直接送出。請先完成必要來源文件、宗地與比準地資料；待後端建立 F03 正式草稿後，計算與檢核按鈕才會開放。</p>
      </section>

      <section v-if="flow.f03" v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="f03-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">F03 正式資料</p>
            <h2 id="f03-title">資料確認與正式採用值</h2>
          </div>
          <span class="source-marker" data-source-kind="human-confirmed">{{ flow.f03.source.label }}</span>
        </div>

        <div class="official-value" data-testid="official-value">
          <div>
            <span>基準地正式採用價格</span>
            <strong>{{ flow.f03.benchmarkLandPrice || '尚未由伺服器提供' }}</strong>
          </div>
          <span class="value-kind" data-value-kind="calculated" data-source-kind="calculated">{{ calculatedSource.label }}</span>
        </div>

        <form class="confirmed-form" @submit.prevent="handleSave">
          <div class="form-heading">
            <h3>人工確認欄位</h3>
            <span class="value-kind" data-value-kind="human-confirmed">可編輯欄位依 F03 PATCH 契約</span>
          </div>
          <div class="field-grid">
            <label>
              <span>基準地</span>
              <select
                v-model="draft.benchmarkLandId"
                data-value-kind="human-confirmed"
                @input="dirty = true"
              >
                <option :value="null">請選擇基準地</option>
                <option v-for="land in flow.benchmarks" :key="land.benchmarkLandId" :value="land.benchmarkLandId">
                  {{ land.benchmarkLandNo }}｜{{ land.priceZoneNo }}
                </option>
              </select>
            </label>
            <label>
              <span>估價基準日</span>
              <input v-model="draft.valuationBaseDate" type="date" @input="dirty = true" />
            </label>
            <label>
              <span>比較法價格（正式值）</span>
              <input
                v-model="draft.comparisonPrice"
                data-testid="f03-comparison-price"
                inputmode="decimal"
                @input="dirty = true"
              />
            </label>
            <label>
              <span>比較法權重</span>
              <input v-model="draft.comparisonWeight" inputmode="decimal" @input="dirty = true" />
            </label>
            <label>
              <span>收益法價格（正式值）</span>
              <input v-model="draft.incomePrice" inputmode="decimal" @input="dirty = true" />
            </label>
            <label>
              <span>收益法權重</span>
              <input v-model="draft.incomeWeight" inputmode="decimal" @input="dirty = true" />
            </label>
            <label>
              <span>市場期間起日</span>
              <input v-model="draft.marketPeriodStart" type="date" @input="dirty = true" />
            </label>
            <label>
              <span>市場期間迄日</span>
              <input v-model="draft.marketPeriodEnd" type="date" @input="dirty = true" />
            </label>
            <label class="field-grid__wide">
              <span>市場條件</span>
              <input v-model="draft.marketCondition" @input="dirty = true" />
            </label>
            <label class="field-grid__wide">
              <span>選擇範圍理由</span>
              <textarea v-model="draft.selectionScopeReason" rows="2" @input="dirty = true" />
            </label>
            <label class="field-grid__wide">
              <span>採用決策理由</span>
              <textarea v-model="draft.decisionReason" rows="2" @input="dirty = true" />
            </label>
          </div>
          <div class="action-row">
            <button class="solid-button" data-testid="save-confirmed-fields" type="submit" :disabled="saving">
              {{ saving ? '儲存中…' : '儲存確認欄位' }}
            </button>
            <button
              class="solid-button solid-button--primary"
              type="button"
              data-testid="run-valuation"
              :disabled="running || saving"
              @click="runValuation"
            >
              {{ running ? '伺服器處理中…' : '執行伺服器計算與檢核' }}
            </button>
          </div>
        </form>
      </section>

      <p v-if="notice" class="inline-notice" role="status">{{ notice }}</p>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>

      <section v-if="flow.validation" v-liquid-glass data-lg class="valuation-surface lg" data-testid="validation-results" aria-labelledby="validation-title">
        <div class="surface-heading">
          <div>
            <p class="valuation-eyebrow">SERVER VALIDATION</p>
            <h2 id="validation-title">伺服器檢核結果</h2>
          </div>
          <span class="value-kind" :data-validation-state="flow.validation.canGenerateReport ? 'ready' : 'blocked'">
            {{ flow.validation.canGenerateReport ? '可產生正式輸出' : '有伺服器阻擋項目' }}
          </span>
        </div>
        <div class="validation-counts">
          <span>通過 {{ flow.validation.passedCount }}</span>
          <span>警示 {{ flow.validation.warningCount }}</span>
          <span>錯誤 {{ flow.validation.failedCount }}</span>
        </div>
        <ul v-if="flow.validation.findings.length" class="finding-list">
          <li v-for="finding in flow.validation.findings" :key="finding.findingId" :data-severity="finding.severity">
            <strong>{{ finding.severity === 'ERROR' ? '阻擋' : '警示' }}｜{{ finding.ruleCode }}</strong>
            <span>{{ finding.message }}</span>
            <small>實際值：{{ finding.actualValue ?? '—' }}</small>
            <small>預期值（expected）：{{ finding.expectedValue ?? '—' }}</small>
          </li>
        </ul>
        <p v-else class="empty-copy">伺服器沒有回傳其他檢核訊息。</p>

        <div v-if="flow.calculation" class="calculation-result" data-testid="calculation-result" data-source-kind="calculated">
          <span>伺服器計算正式結果</span>
          <strong>{{ flow.calculation.result }} {{ flow.calculation.currencyCode }}</strong>
          <small>公式版本：{{ flow.calculation.formulaVersion }}</small>
        </div>
        <div v-if="flow.report" class="report-result" data-testid="report-result">
          <span>正式輸出</span>
          <strong>{{ flow.report.filename }}</strong>
          <small>第 {{ flow.report.versionNo }} 版｜{{ flow.report.fileSizeBytes }} bytes</small>
        </div>
        <button
          class="solid-button solid-button--primary"
          type="button"
          data-testid="go-to-submit"
          @click="goToSubmit"
        >
          前往送審確認
        </button>
      </section>
    </template>
  </div>
</template>

<style scoped>
.valuation-view {
  display: grid;
  gap: 18px;
  padding: 24px 28px 34px;
}

.valuation-surface {
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-paper-strong);
  box-shadow: var(--app-shadow-soft);
}

.surface-heading,
.form-heading,
.action-row,
.official-value,
.calculation-result,
.report-result {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.surface-heading { margin-bottom: 18px; }
.surface-heading h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; font-weight: 600; letter-spacing: -0.04em; }
.valuation-eyebrow { margin: 0 0 6px; color: var(--app-accent-deep); font-size: 11px; font-weight: 800; letter-spacing: 0.12em; }
.source-marker, .value-kind { display: inline-flex; min-height: 30px; align-items: center; padding: 5px 10px; border: 1px solid var(--app-line); border-radius: var(--app-radius-pill); color: var(--app-ink-soft); background: #f7f8fb; font-size: 11px; font-weight: 800; white-space: nowrap; }
.source-marker[data-source-kind="automatic"] { border-color: rgba(59, 129, 102, 0.24); color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.source-marker[data-source-kind="human-confirmed"] { border-color: rgba(200, 91, 67, 0.24); color: var(--app-accent-deep); background: rgba(200, 91, 67, 0.08); }
.value-kind[data-source-kind="calculated"] { border-color: rgba(46, 89, 132, 0.22); color: #2e5984; background: #edf4fb; }
.value-kind[data-value-kind="calculated"] { border-color: rgba(46, 89, 132, 0.22); color: #2e5984; background: #edf4fb; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.summary-grid div { display: grid; gap: 5px; padding: 13px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.form-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.form-list__item { display: grid; gap: 3px; padding: 10px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: #fff; font-size: 11px; }
.form-list__item strong { color: var(--app-ink); font-size: 12px; }
.form-list__item small { color: var(--app-muted); }
.document-workspace { display: grid; gap: 12px; margin-top: 16px; padding: 14px; border: 1px solid var(--app-line); border-radius: 14px; background: rgba(255,255,255,.55); }
.document-workspace__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.document-workspace__heading div { display: grid; gap: 3px; }
.document-workspace__heading strong { color: var(--app-ink); }
.document-workspace__heading span { color: var(--app-muted); font-size: 11px; }
.document-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.document-list li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 11px; border-radius: 10px; background: rgba(247,249,252,.84); }
.document-list li div { display: grid; gap: 2px; min-width: 0; }
.document-list li strong { overflow: hidden; color: var(--app-ink); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.document-list li span { color: var(--app-muted); font-size: 10px; }
.upload-form { display: grid; grid-template-columns: 180px minmax(0,1fr) auto; align-items: end; gap: 10px; }
.upload-form label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.upload-form select,
.upload-form input { min-height: 44px; padding: 8px 10px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink); background: rgba(255,255,255,.82); }
.setup-required { display: grid; gap: 10px; border-color: rgba(214,166,62,.28); background: rgba(255,250,240,.78); }
.setup-required h2 { margin: 0; color: var(--app-ink); }
.setup-required p:last-child { margin: 0; color: var(--app-ink-soft); line-height: 1.7; }
.summary-grid span, .official-value span, .calculation-result span, .report-result span { color: var(--app-muted); font-size: 11px; font-weight: 800; }
.summary-grid strong { color: var(--app-ink); font-size: 14px; }
.source-note { margin: 14px 0 0; color: var(--app-muted); font-size: 12px; }
.official-value { align-items: center; margin-bottom: 20px; padding: 16px; border: 1px solid rgba(46, 89, 132, 0.18); border-radius: var(--app-radius-sm); background: #f5f8fc; }
.official-value div { display: grid; gap: 6px; }
.official-value strong { color: #244d73; font-family: var(--app-font-display); font-size: 24px; font-weight: 600; }
.form-heading { align-items: center; margin-bottom: 12px; }
.form-heading h3 { margin: 0; color: var(--app-ink); font-size: 16px; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.field-grid label { display: grid; gap: 6px; color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.field-grid__wide { grid-column: 1 / -1; }
.field-grid input, .field-grid select, .field-grid textarea { width: 100%; min-height: 44px; padding: 9px 11px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: #fff; font: inherit; font-weight: 500; }
.field-grid textarea { min-height: 72px; resize: vertical; }
.field-grid input:focus, .field-grid select:focus, .field-grid textarea:focus { outline: 3px solid rgba(200, 91, 67, 0.18); border-color: var(--app-accent); }
.action-row { justify-content: flex-end; margin-top: 18px; }
.solid-button { min-height: 44px; padding: 10px 16px; border: 1px solid var(--app-line); border-radius: 9px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 13px; font-weight: 800; }
.solid-button--primary { border-color: var(--app-accent); color: #fff; background: var(--app-accent); }
.solid-button:disabled { cursor: not-allowed; opacity: 0.55; }
.inline-notice, .inline-error { margin: 0; padding: 12px 14px; border-radius: var(--app-radius-sm); font-size: 13px; }
.inline-notice { color: var(--app-green); background: rgba(59, 129, 102, 0.08); }
.inline-error { color: #a44334; background: #fff0ed; }
.validation-counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.validation-counts span { padding: 8px 11px; border-radius: 8px; color: var(--app-ink-soft); background: #f5f7fb; font-size: 12px; font-weight: 800; }
.finding-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.finding-list li { display: grid; gap: 4px; padding: 12px 14px; border-left: 4px solid #d6a63e; background: #fffaf0; color: var(--app-ink-soft); font-size: 13px; }
.finding-list li[data-severity="ERROR"] { border-left-color: #c85b43; background: #fff3f0; }
.finding-list strong { color: var(--app-ink); font-size: 12px; }
.empty-copy { margin: 0; color: var(--app-muted); font-size: 13px; }
.calculation-result, .report-result { align-items: center; margin-top: 14px; padding: 14px; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: #fbfcfe; }
.calculation-result strong, .report-result strong { margin-left: auto; color: var(--app-ink); font-size: 14px; }
.calculation-result small, .report-result small { color: var(--app-muted); font-size: 11px; }
.validation-results > .solid-button { margin-top: 18px; }

@media (max-width: 760px) {
  .valuation-view { padding: 18px 16px 28px; }
  .valuation-surface { padding: 16px; }
  .surface-heading, .official-value, .calculation-result, .report-result { align-items: flex-start; flex-direction: column; }
  .summary-grid, .field-grid { grid-template-columns: 1fr; }
  .upload-form { grid-template-columns: 1fr; }
  .field-grid__wide { grid-column: auto; }
  .form-heading, .action-row { align-items: stretch; flex-direction: column; }
  .solid-button { width: 100%; }
  .calculation-result strong, .report-result strong { margin-left: 0; }
}
</style>
