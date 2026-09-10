<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import CaseTable from '../../../components/common/CaseTable.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { useAuthStore } from '../../../stores/auth.store'
import { safeValuationErrorMessage, valuationApi } from '../valuation.api'
import { mapCaseResponse } from '../valuation.mappers'
import { resetValuationFlow } from '../valuation.types'
import type { FormCode, FormRequirementResponseDto, ValuationCaseModel } from '../valuation.types'
import ValuationStepNavigator from '../components/ValuationStepNavigator.vue'

const router = useRouter()
const auth = useAuthStore()
const cases = ref<ValuationCaseModel[]>([])
const formTypes = ref<FormRequirementResponseDto[]>([])
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const notice = ref('')
const createOpen = ref(false)
const firstCase = computed(() => cases.value[0] ?? null)
const canCreate = computed(() => auth.permissions.includes('case.create') && auth.permissions.includes('valuation.update'))
const createDraft = reactive({
  caseNo: '',
  title: '',
  caseType: '',
  requestingAgency: '',
  valuationBaseDate: '',
  cityCode: '',
  districtCode: '',
  landUseType: '',
  formCode: 'F03' as FormCode,
})
const selectedRequirement = computed(() => formTypes.value.find((item) => item.form_type === createDraft.formCode) ?? null)

async function loadCases(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const caseDtos = await valuationApi.listCases({ offset: 0, limit: 50 })
    cases.value = caseDtos.map(mapCaseResponse)
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    loading.value = false
  }

  try {
    formTypes.value = await valuationApi.getFormTypes()
  } catch {
    formTypes.value = []
  }
}

function resetCreateDraft(): void {
  Object.assign(createDraft, {
    caseNo: '', title: '', caseType: '', requestingAgency: '', valuationBaseDate: '',
    cityCode: '', districtCode: '', landUseType: '', formCode: 'F03' as FormCode,
  })
}

async function createCase(): Promise<void> {
  if (!canCreate.value || creating.value) return
  creating.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await valuationApi.createCase({
      case_no: createDraft.caseNo,
      case_title: createDraft.title,
      case_type: createDraft.caseType,
      requesting_agency: createDraft.requestingAgency || null,
      valuation_base_date: createDraft.valuationBaseDate,
      city_code: createDraft.cityCode,
      district_code: createDraft.districtCode,
      land_use_type: createDraft.landUseType || null,
    })
    await valuationApi.createForm(created.case_id, {
      form_code: createDraft.formCode,
      prepared_date: createDraft.valuationBaseDate,
    })
    createOpen.value = false
    resetCreateDraft()
    notice.value = `案件 ${created.case_no} 已建立，可進入案件上傳來源文件與補齊估價資料。`
    await loadCases()
  } catch (caught: unknown) {
    error.value = safeValuationErrorMessage(caught)
  } finally {
    creating.value = false
  }
}

async function openCase(caseId: string): Promise<void> {
  resetValuationFlow()
  await router.push({ name: 'valuation-prepare', params: { caseId } })
}

onMounted(() => {
  void loadCases()
})
</script>

<template>
  <div class="valuation-view">
    <ValuationStepNavigator :current-stage="1" />
    <PageHeader
      eyebrow="VALUATION WORKSPACE"
      title="估價作業"
      description="建立或接續估價案件，依表單需求完成文件、欄位、計算、檢核與正式送審。"
    >
      <template #actions>
        <button v-if="canCreate" class="solid-button solid-button--primary" type="button" data-testid="create-case" @click="createOpen = true">
          ＋ 新增案件
        </button>
      </template>
    </PageHeader>

    <p v-if="notice" class="dashboard-notice" role="status">{{ notice }}</p>
    <p v-if="error && cases.length" class="dashboard-error" role="alert">{{ error }}</p>

    <section v-liquid-glass data-lg class="valuation-surface lg" aria-labelledby="valuation-case-list-title">
      <div class="valuation-surface__heading">
        <div>
          <p class="valuation-eyebrow">案件與文件</p>
          <h2 id="valuation-case-list-title">最近可處理案件</h2>
        </div>
        <span class="source-marker" data-source-kind="automatic">來源：伺服器案件清單</span>
      </div>

      <CaseTable
        :cases="cases"
        :loading="loading"
        :error="error"
        empty-title="目前沒有可處理案件"
        empty-description="請確認目前帳號具備案件讀取權限，或稍後重新整理。"
        @retry="loadCases"
      />

      <div v-if="firstCase" class="next-action" data-testid="next-action">
        <div>
          <p class="valuation-eyebrow">下一步</p>
          <strong>{{ firstCase.caseNo }}｜{{ firstCase.name }}</strong>
          <p>開啟案件，確認來源資料與 F03 正式估價欄位。</p>
        </div>
        <button
          class="solid-button solid-button--primary"
          type="button"
          data-testid="case-open"
          @click="openCase(firstCase.caseId)"
        >
          繼續處理
        </button>
      </div>
    </section>

    <GlassModal
      :open="createOpen"
      id="valuation-create-case"
      title="新增估價案件"
      initial-focus="#valuation-case-no"
      @close="createOpen = false"
    >
      <form class="create-case-form" data-testid="create-case-form" @submit.prevent="createCase">
        <div class="create-case-grid">
          <label><span>案件編號 *</span><input id="valuation-case-no" v-model.trim="createDraft.caseNo" required maxlength="50" /></label>
          <label><span>案件名稱 *</span><input v-model.trim="createDraft.title" required maxlength="200" /></label>
          <label><span>案件類型 *</span><input v-model.trim="createDraft.caseType" required maxlength="50" placeholder="例如：徵收補償市價查估" /></label>
          <label><span>估價表類型 *</span>
            <select v-model="createDraft.formCode" required>
              <option v-for="item in formTypes" :key="item.form_type" :value="item.form_type">{{ item.form_type }}｜{{ item.form_name }}</option>
            </select>
          </label>
          <label><span>估價基準日 *</span><input v-model="createDraft.valuationBaseDate" type="date" required /></label>
          <label><span>申請機關</span><input v-model.trim="createDraft.requestingAgency" maxlength="200" /></label>
          <label><span>縣市代碼 *</span><input v-model.trim="createDraft.cityCode" required maxlength="20" /></label>
          <label><span>行政區代碼 *</span><input v-model.trim="createDraft.districtCode" required maxlength="20" /></label>
          <label class="create-case-grid__wide"><span>土地使用類型</span><input v-model.trim="createDraft.landUseType" maxlength="100" /></label>
        </div>

        <section v-if="selectedRequirement" class="requirement-preview" aria-label="所需資料清單">
          <div>
            <strong>{{ selectedRequirement.form_name }} 所需資料</strong>
            <span>依後端 form-types 契約顯示。</span>
          </div>
          <ul>
            <li v-for="field in selectedRequirement.required_fields" :key="`field-${field}`">欄位：{{ field }}</li>
            <li v-for="document in selectedRequirement.required_documents" :key="`doc-${document}`">文件：{{ document }}</li>
          </ul>
        </section>

        <div class="create-case-actions">
          <button class="solid-button" type="button" :disabled="creating" @click="createOpen = false">取消</button>
          <button class="solid-button solid-button--primary" type="submit" :disabled="creating">
            {{ creating ? '建立中…' : '建立案件與表單' }}
          </button>
        </div>
      </form>
    </GlassModal>
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
  background: color-mix(in srgb, var(--app-paper-strong) 82%, transparent);
  box-shadow: var(--app-shadow-soft);
}

.dashboard-notice,
.dashboard-error { margin: 0; padding: 12px 14px; border-radius: var(--app-radius-sm); font-size: 13px; }
.dashboard-notice { color: var(--app-green); background: rgba(59, 129, 102, .09); }
.dashboard-error { color: #a44334; background: rgba(255, 240, 237, .9); }

.create-case-form { display: grid; gap: 18px; min-width: min(720px, 72vw); }
.create-case-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; }
.create-case-grid label { display: grid; gap: 6px; color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.create-case-grid__wide { grid-column: 1 / -1; }
.create-case-grid input,
.create-case-grid select { min-height: 44px; padding: 9px 11px; border: 1px solid var(--app-line); border-radius: 10px; color: var(--app-ink); background: rgba(255,255,255,.8); font: inherit; }
.create-case-grid input:focus,
.create-case-grid select:focus { outline: 3px solid rgba(200, 91, 67, .16); border-color: var(--app-accent); }
.requirement-preview { display: grid; gap: 10px; padding: 14px; border: 1px solid rgba(46, 89, 132, .18); border-radius: 14px; background: rgba(237, 244, 251, .66); }
.requirement-preview div { display: grid; gap: 3px; }
.requirement-preview strong { color: var(--app-ink); }
.requirement-preview span { color: var(--app-muted); font-size: 11px; }
.requirement-preview ul { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.requirement-preview li { padding: 6px 9px; border-radius: 999px; color: var(--app-ink-soft); background: rgba(255,255,255,.76); font-size: 11px; }
.create-case-actions { display: flex; justify-content: flex-end; gap: 8px; }

.valuation-surface__heading,
.next-action {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.valuation-surface__heading {
  margin-bottom: 16px;
}

.valuation-surface h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.04em;
}

.valuation-eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.source-marker {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid rgba(59, 129, 102, 0.24);
  border-radius: var(--app-radius-pill);
  color: var(--app-green);
  background: rgba(59, 129, 102, 0.08);
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.next-action {
  align-items: center;
  margin-top: 18px;
  padding: 18px;
  border: 1px solid rgba(200, 91, 67, 0.18);
  border-radius: var(--app-radius-sm);
  background: #fffaf7;
}

.next-action strong {
  display: block;
  color: var(--app-ink);
  font-size: 15px;
}

.next-action p:last-child {
  margin: 5px 0 0;
  color: var(--app-ink-soft);
  font-size: 13px;
}

.solid-button {
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}

.solid-button--primary {
  border-color: var(--app-accent);
  color: #fff;
  background: var(--app-accent);
}

.solid-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

@media (max-width: 640px) {
  .valuation-view {
    padding: 18px 16px 28px;
  }

  .valuation-surface {
    padding: 16px;
  }

  .valuation-surface__heading,
  .next-action {
    align-items: flex-start;
    flex-direction: column;
  }

  .solid-button {
    width: 100%;
  }
  .create-case-form { min-width: 0; }
  .create-case-grid { grid-template-columns: 1fr; }
  .create-case-grid__wide { grid-column: auto; }
  .create-case-actions { flex-direction: column-reverse; }
}
</style>
