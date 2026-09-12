<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import StatusBadge from '../../../components/common/StatusBadge.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { historyApi, safeHistoryErrorMessage, sanitizeHistorySearchParams } from '../history.api'
import {
  HISTORY_NEW_TAIPEI_CITY_CODE,
  HISTORY_NEW_TAIPEI_DISTRICTS,
  historyCanonicalDistrictCode,
  historyLocationLabel,
} from '../history.location'
import { mapHistoryCaseSummary, mapHistoryPermissions } from '../history.mappers'
import { historyScopeForRoles } from '../../../router/roleAccess'
import { useAuthStore } from '../../../stores/auth.store'
import { formatDateZhTw } from '../../../utils/formatters'
import type {
  HistoryCaseModel,
  HistoryDateField,
  HistoryResultCode,
  HistorySearchParams,
  HistorySortField,
  HistorySortOrder,
} from '../history.types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const rows = ref<HistoryCaseModel[]>([])
const total = ref(0)
const permissions = ref({ canViewValuation: false, canViewReview: false })
const loading = ref(false)
const error = ref('')
const filterError = ref('')
const advancedOpen = ref(false)
const loadSerial = ref(0)
let activeController: AbortController | null = null
const historyScope = computed(() => historyScopeForRoles(authStore.roles))

const form = reactive<{
  keyword: string
  districtCode: string
  sectionName: string
  result: HistoryResultCode | ''
  dateField: HistoryDateField
  dateFrom: string
  dateTo: string
  sort: HistorySortField
  order: HistorySortOrder
}>({
  keyword: '',
  districtCode: '',
  sectionName: '',
  result: '',
  dateField: 'updated_at',
  dateFrom: '',
  dateTo: '',
  sort: 'updated_at',
  order: 'desc',
})

function queryString(...names: string[]): string {
  for (const name of names) {
    const value = route.query[name]
    if (typeof value === 'string' && value) return value
  }
  return ''
}

function queryNumber(...names: string[]): number | null {
  const value = Number.parseInt(queryString(...names), 10)
  return Number.isFinite(value) && value >= 0 ? value : null
}

const pageSize = computed(() => {
  const value = queryNumber('pageSize', 'limit')
  return value && value >= 1 && value <= 100 ? value : 20
})

const offset = computed(() => {
  const explicit = queryNumber('offset')
  if (explicit !== null) return explicit
  const page = queryNumber('page')
  return page && page > 0 ? (page - 1) * pageSize.value : 0
})

const page = computed(() => Math.floor(offset.value / pageSize.value) + 1)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const advancedFilterCount = computed(() => [
  form.districtCode,
  form.sectionName,
  form.result,
  form.dateFrom,
  form.dateTo,
  form.dateField !== 'updated_at' ? form.dateField : '',
].filter(Boolean).length)

function routeHasAdvancedFilters(): boolean {
  return [
    'districtCode', 'district_code', 'sectionName', 'section_name',
    'result', 'dateField', 'date_field', 'dateFrom', 'date_from', 'dateTo', 'date_to',
  ].some((name) => Boolean(queryString(name)))
}

function routeSearchParams(): HistorySearchParams {
  const dateField = queryString('dateField', 'date_field')
  const sort = queryString('sort')
  const order = queryString('order')
  return {
    keyword: queryString('keyword') || undefined,
    cityCode: HISTORY_NEW_TAIPEI_CITY_CODE,
    districtCode: historyCanonicalDistrictCode(queryString('districtCode', 'district_code')) || undefined,
    sectionName: queryString('sectionName', 'section_name') || undefined,
    result: (queryString('result') || undefined) as HistoryResultCode | undefined,
    dateField: (dateField || undefined) as HistoryDateField | undefined,
    dateFrom: queryString('dateFrom', 'date_from') || undefined,
    dateTo: queryString('dateTo', 'date_to') || undefined,
    sort: (sort || undefined) as HistorySortField | undefined,
    order: (order || undefined) as HistorySortOrder | undefined,
    offset: offset.value,
    limit: pageSize.value,
  }
}

type ActiveFilterKey = 'districtCode' | 'sectionName' | 'result' | 'dateRange'

const resultLabels: Record<HistoryResultCode, string> = {
  PASSED: '審查通過',
  CORRECTION: '補正中',
  RETURNED: '已退回',
  SUPPLEMENT_REQUIRED: '待補件',
  IN_PROGRESS: '處理中',
}

const appliedParams = computed(() => sanitizeHistorySearchParams(routeSearchParams(), authStore.roles))
const activeFilterChips = computed<Array<{ key: ActiveFilterKey; label: string }>>(() => {
  const params = appliedParams.value
  const chips: Array<{ key: ActiveFilterKey; label: string }> = []
  if (params.districtCode) {
    const district = HISTORY_NEW_TAIPEI_DISTRICTS.find((item) => item.code === params.districtCode)
    chips.push({ key: 'districtCode', label: district?.name ?? '指定行政區' })
  }
  if (params.sectionName) chips.push({ key: 'sectionName', label: `地段：${params.sectionName}` })
  if (params.result) chips.push({ key: 'result', label: resultLabels[params.result] })
  if (params.dateFrom || params.dateTo) {
    const fieldLabel = params.dateField === 'received_at'
      ? '審查收件'
      : params.dateField === 'completed_at'
        ? '審查完成'
        : '最後更新'
    chips.push({
      key: 'dateRange',
      label: `${fieldLabel}：${params.dateFrom || '不限'} ～ ${params.dateTo || '不限'}`,
    })
  }
  return chips
})
const hasAppliedCriteria = computed(() => Boolean(appliedParams.value.keyword) || activeFilterChips.value.length > 0)

function syncFormFromRoute(): void {
  const params = sanitizeHistorySearchParams(routeSearchParams(), authStore.roles)
  form.keyword = params.keyword ?? ''
  form.districtCode = historyCanonicalDistrictCode(params.districtCode) || ''
  form.sectionName = params.sectionName ?? ''
  form.result = params.result ?? ''
  form.dateField = params.dateField ?? 'updated_at'
  form.dateFrom = params.dateFrom ?? ''
  form.dateTo = params.dateTo ?? ''
  form.sort = params.sort ?? 'updated_at'
  form.order = params.order === 'asc' ? 'asc' : 'desc'
}

function currentStringQuery(): Record<string, string> {
  const allowed = new Set([
    'keyword', 'districtCode', 'district_code',
    'sectionName', 'section_name', 'result', 'dateField', 'date_field',
    'dateFrom', 'date_from', 'dateTo', 'date_to', 'sort', 'order',
    'page', 'pageSize', 'offset', 'limit',
  ])
  return Object.fromEntries(
    Object.entries(route.query)
      .map(([key, value]) => [key, Array.isArray(value) ? value[0] ?? '' : value ?? ''])
      .filter(([key, value]) => allowed.has(key) && value),
  )
}

function setQueryValue(query: Record<string, string>, key: string, value: string, aliases: string[] = []): void {
  aliases.forEach((alias) => delete query[alias])
  if (value) query[key] = value
  else delete query[key]
}

function routeQueryFromForm(): Record<string, string> {
  const query = currentStringQuery()
  setQueryValue(query, 'keyword', form.keyword.trim())
  setQueryValue(query, 'districtCode', form.districtCode.trim(), ['district_code'])
  setQueryValue(query, 'sectionName', form.sectionName.trim(), ['section_name'])
  setQueryValue(query, 'result', form.result)
  setQueryValue(query, 'dateFrom', form.dateFrom, ['date_from'])
  setQueryValue(query, 'dateTo', form.dateTo, ['date_to'])
  setQueryValue(query, 'dateField', form.dateField === 'updated_at' ? '' : form.dateField, ['date_field'])
  setQueryValue(query, 'sort', form.sort === 'updated_at' ? '' : form.sort)
  setQueryValue(query, 'order', form.order === 'desc' ? '' : form.order)
  return query
}

function apiParams(): HistorySearchParams {
  return sanitizeHistorySearchParams(routeSearchParams(), authStore.roles)
}

async function loadData(): Promise<void> {
  const serial = ++loadSerial.value
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  error.value = ''
  try {
    const result = await historyApi.listCases(apiParams(), controller.signal, authStore.roles)
    if (serial !== loadSerial.value) return
    rows.value = result.items.map((item) => mapHistoryCaseSummary(item, result.permissions))
    total.value = result.total
    permissions.value = mapHistoryPermissions(result.permissions)
  } catch (caught: unknown) {
    if (serial === loadSerial.value && !controller.signal.aborted) error.value = safeHistoryErrorMessage(caught)
  } finally {
    if (serial === loadSerial.value) loading.value = false
  }
}

async function applySearch(): Promise<void> {
  if (form.dateFrom && form.dateTo && form.dateFrom > form.dateTo) {
    filterError.value = '日期起日不可晚於日期迄日，請重新選擇日期範圍。'
    advancedOpen.value = true
    return
  }
  filterError.value = ''
  const query = routeQueryFromForm()
  delete query.page
  delete query.offset
  await router.replace({ query })
}

async function resetSearch(): Promise<void> {
  filterError.value = ''
  Object.assign(form, {
    keyword: '',
    districtCode: '',
    sectionName: '',
    result: '',
    dateField: 'updated_at',
    dateFrom: '',
    dateTo: '',
    sort: 'updated_at',
    order: 'desc',
  })
  advancedOpen.value = false
  await router.replace({ query: {} })
}

async function removeFilter(key: ActiveFilterKey): Promise<void> {
  if (key === 'districtCode') form.districtCode = ''
  if (key === 'sectionName') form.sectionName = ''
  if (key === 'result') form.result = ''
  if (key === 'dateRange') {
    form.dateField = 'updated_at'
    form.dateFrom = ''
    form.dateTo = ''
  }
  await applySearch()
}

async function applySort(): Promise<void> {
  const query = currentStringQuery()
  setQueryValue(query, 'sort', form.sort === 'updated_at' ? '' : form.sort)
  setQueryValue(query, 'order', form.order === 'desc' ? '' : form.order)
  delete query.page
  delete query.offset
  await router.replace({ query })
}

function setPage(nextPage: number): void {
  if (nextPage < 1 || nextPage > pageCount.value || nextPage === page.value) return
  const query = currentStringQuery()
  delete query.offset
  delete query.limit
  query.page = String(nextPage)
  query.pageSize = String(pageSize.value)
  void router.replace({ query })
}

function openCase(item: HistoryCaseModel): void {
  void router.push({ name: 'history-case', params: { caseId: item.caseId }, query: currentStringQuery() })
}

function formatPermissionText(): string {
  const labels = []
  if (permissions.value.canViewValuation) labels.push('估價資料')
  if (permissions.value.canViewReview) labels.push('審查資料')
  return labels.length ? `目前可查看：${labels.join('、')}` : '目前帳號沒有可查看的子系統資料'
}

watch(() => route.fullPath, () => {
  syncFormFromRoute()
  if (routeHasAdvancedFilters()) advancedOpen.value = true
  void loadData()
})

onMounted(() => {
  syncFormFromRoute()
  advancedOpen.value = routeHasAdvancedFilters()
  void loadData()
})

onBeforeUnmount(() => activeController?.abort())
</script>

<template>
  <section class="history-search" data-testid="history-search">
    <PageHeader eyebrow="案件歷史" title="案件查詢" />

    <section v-liquid-glass data-lg class="history-search__search-panel lg">
      <form class="history-search__form" data-testid="history-search-form" @submit.prevent="applySearch">
        <div class="history-search__primary-search">
          <label class="history-search__keyword-field">
            <span class="history-search__visually-hidden">關鍵字</span>
            <div class="history-search__search-input-wrap">
              <span aria-hidden="true">⌕</span>
              <input v-model="form.keyword" data-testid="history-keyword" type="search" placeholder="搜尋案件編號、案件名稱或地號" autocomplete="off">
            </div>
          </label>
          <button type="submit" class="history-search__submit" data-testid="history-search-submit" @click.prevent="applySearch">搜尋案件</button>
        </div>

        <div class="history-search__secondary-actions">
          <button
            type="button"
            class="history-search__advanced-toggle"
            data-testid="history-advanced-toggle"
            :aria-expanded="advancedOpen ? 'true' : 'false'"
            aria-controls="history-advanced-filters"
            @click="advancedOpen = !advancedOpen"
          >
            {{ advancedOpen ? '收合篩選' : '進階篩選' }}
            <span v-if="advancedFilterCount">{{ advancedFilterCount }}</span>
          </button>
          <div v-if="activeFilterChips.length" class="history-search__filter-chips" aria-label="目前篩選條件">
            <button
              v-for="chip in activeFilterChips"
              :key="chip.key"
              type="button"
              class="history-search__filter-chip"
              :aria-label="`移除篩選：${chip.label}`"
              @click="removeFilter(chip.key)"
            >
              {{ chip.label }}
              <span aria-hidden="true">×</span>
            </button>
          </div>
          <button v-if="hasAppliedCriteria" type="button" class="history-search__reset" data-testid="history-search-reset" @click="resetSearch">清除全部</button>
        </div>

        <div
          id="history-advanced-filters"
          v-show="advancedOpen"
          class="history-search__advanced"
          data-testid="history-advanced-filters"
        >
          <div class="history-search__advanced-heading">
            <strong>進階篩選</strong>
            <span>需要縮小範圍時，再依行政區、地段、歷程結果或日期篩選。</span>
          </div>
          <div class="history-search__fields">
            <label>
              <span>行政區</span>
              <select v-model="form.districtCode" data-testid="history-district-code">
                <option value="">全部行政區</option>
                <option v-for="district in HISTORY_NEW_TAIPEI_DISTRICTS" :key="district.code" :value="district.code">
                  {{ district.name }}
                </option>
              </select>
            </label>
            <label>
              <span>地段</span>
              <input v-model="form.sectionName" data-testid="history-section-name" type="text" maxlength="100" placeholder="例如：文化段">
            </label>
            <label>
              <span>歷程結果</span>
              <select v-model="form.result" data-testid="history-result">
                <option value="">全部結果</option>
                <option v-if="historyScope.review" value="PASSED">審查通過</option>
                <option value="CORRECTION">補正中</option>
                <option v-if="historyScope.review" value="RETURNED">已退回</option>
                <option v-if="historyScope.review" value="SUPPLEMENT_REQUIRED">待補件</option>
                <option value="IN_PROGRESS">處理中</option>
              </select>
            </label>
            <label>
              <span>日期欄位</span>
              <select v-model="form.dateField" data-testid="history-date-field">
                <option value="updated_at">最後更新</option>
                <option v-if="historyScope.review" value="received_at">審查收件</option>
                <option v-if="historyScope.review" value="completed_at">審查完成</option>
              </select>
            </label>
            <label>
              <span>日期起日</span>
              <input v-model="form.dateFrom" data-testid="history-date-from" type="date">
            </label>
            <label>
              <span>日期迄日</span>
              <input v-model="form.dateTo" data-testid="history-date-to" type="date">
            </label>
          </div>
          <div class="history-search__advanced-actions">
            <button type="button" class="history-search__apply-filters" @click="applySearch">套用篩選</button>
          </div>
        </div>
        <p v-if="filterError" class="history-search__filter-error" role="alert">{{ filterError }}</p>
      </form>
    </section>

    <section class="history-search__results" aria-labelledby="history-results-title">
      <div class="history-search__results-heading">
        <div class="history-search__results-title">
          <div>
            <h2 id="history-results-title">案件結果</h2>
            <div class="history-search__results-meta">
              <span class="history-search__total" aria-live="polite">共 {{ total }} 筆</span>
              <span class="history-search__permission">
                <span class="history-search__permission-dot" aria-hidden="true"></span>
                {{ formatPermissionText() }}
              </span>
            </div>
          </div>
        </div>
        <div class="history-search__sort-controls" aria-label="排序方式">
          <label>
            <span>排序</span>
            <select v-model="form.sort" data-testid="history-sort" @change="applySort">
              <option value="updated_at">最後更新</option>
              <option v-if="historyScope.review" value="received_at">審查收件</option>
              <option v-if="historyScope.review" value="risk_level">風險等級</option>
            </select>
          </label>
          <label>
            <span class="history-search__visually-hidden">排序方向</span>
            <select v-model="form.order" data-testid="history-order" aria-label="排序方向" @change="applySort">
              <option value="desc">新到舊</option>
              <option value="asc">舊到新</option>
            </select>
          </label>
        </div>
      </div>

      <LoadingSkeleton v-if="loading && !rows.length" :rows="5" label="案件歷程載入中" />
      <ErrorState v-else-if="error && !rows.length" :message="error" @retry="loadData" />
      <EmptyState
        v-else-if="!rows.length"
        :title="hasAppliedCriteria ? '找不到符合條件的案件' : '搜尋案件'"
        :description="hasAppliedCriteria
          ? '請確認關鍵字是否正確，或移除部分篩選條件後再試一次。'
          : '輸入案件編號、案件名稱或地號開始查詢；需要時可使用進階篩選縮小範圍。'"
        :action-label="hasAppliedCriteria ? '清除搜尋條件' : undefined"
        @action="resetSearch"
      />
      <template v-else>
        <p v-if="error" class="history-search__inline-error" role="alert">{{ error }}</p>
        <div class="history-search__case-list" role="list" :aria-busy="loading ? 'true' : 'false'">
          <article
            v-for="item in rows"
            :key="item.caseId"
            class="history-search__case-row"
            role="listitem"
            :data-testid="`history-case-row-${item.caseId}`"
          >
            <div class="history-search__case-primary">
              <div class="history-search__case-heading">
                <span class="history-search__case-no">{{ item.caseNo }}</span>
                <StatusBadge :status="item.historyResultCode" />
              </div>
              <button type="button" class="history-search__case-link" @click="openCase(item)">{{ item.name }}</button>
              <div class="history-search__case-meta">
                <span>{{ historyLocationLabel(item.cityCode, item.districtCode) }}</span>
                <span>基準日 {{ formatDateZhTw(item.valuationBaseDate) }}</span>
                <span :title="item.updatedAt">更新 {{ formatDateZhTw(item.updatedAt) }}</span>
              </div>
            </div>

            <button type="button" class="history-search__detail" :data-testid="`history-open-${item.caseId}`" @click="openCase(item)">
              查看案件
              <span aria-hidden="true">→</span>
            </button>
          </article>
        </div>
        <nav v-if="pageCount > 1" class="history-search__pagination" aria-label="案件歷程分頁">
          <button type="button" data-testid="history-page-previous" :disabled="page <= 1" @click="setPage(page - 1)">上一頁</button>
          <span>第 {{ page }} / {{ pageCount }} 頁</span>
          <button type="button" data-testid="history-page-next" :disabled="page >= pageCount" @click="setPage(page + 1)">下一頁</button>
        </nav>
      </template>
    </section>
  </section>
</template>

<style scoped>
.history-search { padding: 0 28px 36px; }
.history-search h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 22px; }
.history-search__visually-hidden { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.history-search button:focus-visible,
.history-search input:focus-visible,
.history-search select:focus-visible { outline:3px solid color-mix(in srgb, var(--app-accent) 30%, white); outline-offset:2px; }

.history-search__search-panel { border:1px solid rgba(255,255,255,.84); border-radius:14px; background:rgba(250,252,255,.82); box-shadow:0 10px 28px rgba(35,56,78,.08); }
.history-search__form { padding:16px; }
.history-search__primary-search { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; }
.history-search__keyword-field { min-width:0; }
.history-search__search-input-wrap { display:flex; min-height:48px; align-items:center; gap:9px; padding:0 13px; border:1px solid var(--app-line); border-radius:10px; background:#fff; }
.history-search__search-input-wrap > span { color:var(--app-muted); font-size:19px; transform:rotate(-12deg); }
.history-search__search-input-wrap input { width:100%; min-width:0; min-height:44px; flex:1; padding:0; border:0 !important; outline:0 !important; color:var(--app-ink); background:transparent !important; box-shadow:none !important; font-size:13px; }
.history-search__search-input-wrap:focus-within { border-color:var(--app-accent); box-shadow:0 0 0 3px color-mix(in srgb, var(--app-accent) 18%, white); }
.history-search__submit { min-width:116px; min-height:48px; padding:8px 18px; border:1px solid var(--app-accent); border-radius:10px; color:#fff8f2; background:var(--app-accent); cursor:pointer; font-size:12px; font-weight:900; }
.history-search__submit:hover { background:var(--app-accent-deep); }

.history-search__secondary-actions { display:flex; min-height:34px; align-items:center; flex-wrap:wrap; gap:7px; margin-top:9px; }
.history-search__advanced-toggle { display:inline-flex; min-height:34px; align-items:center; gap:6px; padding:5px 9px; border:0; border-radius:7px; color:var(--app-primary-deep); background:transparent; cursor:pointer; font-size:11px; font-weight:850; }
.history-search__advanced-toggle:hover { background:var(--app-primary-soft); }
.history-search__advanced-toggle span { display:inline-grid; min-width:18px; height:18px; place-items:center; border-radius:999px; color:#fff; background:var(--app-primary); font-size:9px; }
.history-search__filter-chips { display:flex; min-width:0; flex:1; flex-wrap:wrap; gap:6px; }
.history-search__filter-chip { display:inline-flex; min-height:30px; align-items:center; gap:6px; padding:4px 8px; border:1px solid #cfdae7; border-radius:999px; color:#315777; background:#f4f8fc; cursor:pointer; font-size:10px; font-weight:800; }
.history-search__filter-chip:hover { border-color:var(--app-primary); background:#edf4fb; }
.history-search__filter-chip span { font-size:14px; line-height:1; }
.history-search__reset { min-height:32px; padding:4px 7px; border:0; border-radius:6px; color:var(--app-muted); background:transparent; cursor:pointer; font-size:10px; font-weight:800; }
.history-search__reset:hover { color:var(--app-accent-deep); background:#fff4ed; }

.history-search__advanced { margin-top:10px; padding:14px; border:1px solid var(--app-line); border-radius:10px; background:rgba(255,255,255,.62); }
.history-search__advanced-heading { display:flex; align-items:baseline; gap:8px; }
.history-search__advanced-heading strong { color:var(--app-ink); font-size:11px; }
.history-search__advanced-heading span { color:var(--app-muted); font-size:10px; }
.history-search__fields { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:11px; margin-top:12px; }
.history-search__fields label { display:grid; gap:5px; color:var(--app-ink-soft); font-size:10px; font-weight:850; }
.history-search__fields input,
.history-search__fields select { width:100%; min-height:42px; padding:8px 10px; border:1px solid var(--app-line); border-radius:8px; color:var(--app-ink); background:#fff; font-size:12px; }
.history-search__fields input:focus,
.history-search__fields select:focus { border-color:var(--app-accent); }
.history-search__advanced-actions { display:flex; justify-content:flex-end; margin-top:11px; }
.history-search__apply-filters { min-height:38px; padding:7px 13px; border:1px solid #c6d4e3; border-radius:8px; color:var(--app-primary-deep); background:#fff; cursor:pointer; font-size:11px; font-weight:850; }
.history-search__apply-filters:hover { border-color:var(--app-primary); background:var(--app-primary-soft); }
.history-search__filter-error { margin:10px 0 0; padding:9px 11px; border:1px solid #ebc7c5; border-radius:8px; color:#963b36; background:#fff6f5; font-size:11px; font-weight:700; }

.history-search__results { margin-top:28px; }
.history-search__results-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:18px; padding:0 2px 10px; border-bottom:1px solid var(--app-line); }
.history-search__results-title { min-width:0; }
.history-search__results-meta { display:flex; align-items:center; flex-wrap:wrap; gap:10px; margin-top:5px; }
.history-search__total { color:var(--app-muted); font-size:11px; font-weight:700; }
.history-search__permission { display:inline-flex; align-items:center; gap:6px; color:var(--app-muted); font-size:10px; font-weight:750; }
.history-search__permission-dot { width:6px; height:6px; flex:0 0 6px; border-radius:999px; background:var(--app-green); }
.history-search__sort-controls { display:flex; align-items:flex-end; gap:7px; }
.history-search__sort-controls label { display:grid; gap:4px; color:var(--app-muted); font-size:9px; font-weight:850; }
.history-search__sort-controls select { min-height:38px; padding:6px 28px 6px 9px; border:1px solid var(--app-line); border-radius:8px; color:var(--app-ink-soft); background:#fff; font-size:11px; }
.history-search__inline-error { margin:12px 0 0; color:#ac3c37; font-size:12px; }

.history-search__case-list { display:grid; gap:9px; margin-top:12px; }
.history-search__case-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:18px; padding:15px 16px; border:1px solid var(--app-line); border-radius:10px; background:var(--app-paper-strong); transition:border-color .18s ease, box-shadow .18s ease, transform .18s ease; }
.history-search__case-row:hover { border-color:color-mix(in srgb, var(--app-primary) 34%, var(--app-line)); box-shadow:0 7px 20px rgba(35,56,78,.07); transform:translateY(-1px); }
.history-search__case-primary { display:grid; min-width:0; gap:5px; }
.history-search__case-heading { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.history-search__case-no { color:var(--app-muted); font-size:10px; font-weight:900; letter-spacing:.06em; }
.history-search__case-link { width:max-content; max-width:100%; padding:0; overflow:hidden; border:0; color:var(--app-ink); background:transparent; cursor:pointer; font-size:13px; font-weight:850; text-align:left; text-overflow:ellipsis; white-space:nowrap; }
.history-search__case-link:hover { color:var(--app-accent-deep); text-decoration:underline; }
.history-search__case-meta { display:flex; min-width:0; flex-wrap:wrap; gap:4px 0; margin-top:2px; color:var(--app-muted); font-size:10px; }
.history-search__case-meta span { display:inline-flex; align-items:center; }
.history-search__case-meta span + span::before { content:'·'; margin:0 7px; color:#a7b1bd; }
.history-search__detail { display:inline-flex; min-height:40px; align-items:center; justify-content:center; gap:7px; padding:7px 12px; border:1px solid var(--app-line); border-radius:8px; color:var(--app-ink-soft); background:#fff; cursor:pointer; font-size:11px; font-weight:850; white-space:nowrap; }
.history-search__detail:hover { border-color:var(--app-accent); color:var(--app-accent-deep); }
.history-search__detail span { color:var(--app-accent); font-size:14px; }
.history-search__pagination { display:flex; align-items:center; justify-content:flex-end; gap:10px; margin-top:14px; color:var(--app-muted); font-size:11px; }
.history-search__pagination button { min-width:74px; min-height:40px; padding:7px 11px; border:1px solid var(--app-line); border-radius:8px; color:var(--app-ink-soft); background:#fff; cursor:pointer; font-size:11px; font-weight:850; }
.history-search__pagination button:hover:not(:disabled) { border-color:var(--app-accent); color:var(--app-accent-deep); }
.history-search__pagination button:disabled { cursor:not-allowed; opacity:.45; }

@media (max-width: 900px) {
  .history-search__fields { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .history-search__results-heading { align-items:flex-start; flex-direction:column; }
}

@media (max-width: 700px) {
  .history-search { padding-inline:14px; }
  .history-search__primary-search { grid-template-columns:1fr; }
  .history-search__submit { width:100%; }
  .history-search__secondary-actions { align-items:stretch; }
  .history-search__filter-chips { flex-basis:100%; order:3; }
  .history-search__reset { margin-left:auto; }
  .history-search__sort-controls { width:100%; }
  .history-search__sort-controls label:first-child { flex:1; }
  .history-search__sort-controls select { width:100%; }
  .history-search__case-row { grid-template-columns:1fr; gap:11px; }
  .history-search__detail { justify-self:stretch; }
}

@media (max-width: 460px) {
  .history-search__fields { grid-template-columns:1fr; }
  .history-search__advanced-heading { align-items:flex-start; flex-direction:column; gap:3px; }
  .history-search__results-meta { align-items:flex-start; flex-direction:column; gap:5px; }
  .history-search__sort-controls { display:grid; grid-template-columns:1fr 1fr; }
  .history-search__case-link { width:100%; white-space:normal; }
}
</style>
