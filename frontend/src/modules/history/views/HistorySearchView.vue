<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import RiskBadge from '../../../components/common/RiskBadge.vue'
import StatusBadge from '../../../components/common/StatusBadge.vue'
import { liquidGlass as vLiquidGlass } from '../../../directives/liquidGlass'
import { historyApi, safeHistoryErrorMessage, sanitizeHistorySearchParams } from '../history.api'
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
const advancedOpen = ref(false)
const loadSerial = ref(0)
let activeController: AbortController | null = null
const historyScope = computed(() => historyScopeForRoles(authStore.roles))

const form = reactive<{
  keyword: string
  cityCode: string
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
  cityCode: '',
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
  form.cityCode,
  form.districtCode,
  form.sectionName,
  form.dateFrom,
  form.dateTo,
  form.dateField !== 'updated_at' ? form.dateField : '',
  form.sort !== 'updated_at' ? form.sort : '',
  form.order !== 'desc' ? form.order : '',
].filter(Boolean).length)

function routeHasAdvancedFilters(): boolean {
  return [
    'cityCode', 'city_code', 'districtCode', 'district_code', 'sectionName', 'section_name',
    'dateField', 'date_field', 'dateFrom', 'date_from', 'dateTo', 'date_to', 'sort', 'order',
  ].some((name) => Boolean(queryString(name)))
}

function routeSearchParams(): HistorySearchParams {
  const dateField = queryString('dateField', 'date_field')
  const sort = queryString('sort')
  const order = queryString('order')
  return {
    keyword: queryString('keyword') || undefined,
    cityCode: queryString('cityCode', 'city_code') || undefined,
    districtCode: queryString('districtCode', 'district_code') || undefined,
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

function syncFormFromRoute(): void {
  const params = sanitizeHistorySearchParams(routeSearchParams(), authStore.roles)
  form.keyword = params.keyword ?? ''
  form.cityCode = params.cityCode ?? ''
  form.districtCode = params.districtCode ?? ''
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
    'keyword', 'cityCode', 'city_code', 'districtCode', 'district_code',
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
  setQueryValue(query, 'cityCode', form.cityCode.trim(), ['city_code'])
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
  await router.replace({ query: routeQueryFromForm() })
}

async function resetSearch(): Promise<void> {
  Object.assign(form, {
    keyword: '',
    cityCode: '',
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
  if (permissions.value.canViewValuation) labels.push('估價')
  if (permissions.value.canViewReview) labels.push('審查')
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
    <PageHeader
      eyebrow="CASE HISTORY"
      title="案件歷程"
      description="以伺服器支援的條件搜尋案件、結構化資料與授權文件歷程。"
    >
      <template #actions>
        <span class="history-search__permission">{{ formatPermissionText() }}</span>
      </template>
    </PageHeader>

    <form v-liquid-glass data-lg class="history-search__form lg" data-testid="history-search-form" @submit.prevent="applySearch">
      <div class="history-search__form-heading">
        <div>
          <p class="history-search__eyebrow">SUPPORTED SEARCH</p>
          <h2>搜尋條件</h2>
        </div>
        <div class="history-search__form-tools">
          <button
            type="button"
            class="history-search__advanced-toggle"
            data-testid="history-advanced-toggle"
            :aria-expanded="advancedOpen ? 'true' : 'false'"
            aria-controls="history-advanced-filters"
            @click="advancedOpen = !advancedOpen"
          >
            {{ advancedOpen ? '收合進階篩選' : '進階篩選' }}
            <span v-if="advancedFilterCount">{{ advancedFilterCount }}</span>
          </button>
          <button type="button" class="history-search__reset" data-testid="history-search-reset" @click="resetSearch">清除條件</button>
        </div>
      </div>
      <div class="history-search__quick-fields">
        <label>
          <span>關鍵字</span>
          <input v-model="form.keyword" data-testid="history-keyword" type="search" placeholder="案件編號、案件名稱或地號" autocomplete="off">
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
      </div>
      <div
        id="history-advanced-filters"
        v-show="advancedOpen"
        class="history-search__advanced"
        data-testid="history-advanced-filters"
      >
        <div class="history-search__advanced-heading">
          <strong>進階篩選</strong>
          <span>需要縮小地區、日期或排序條件時再使用。</span>
        </div>
        <div class="history-search__fields">
        <label>
          <span>縣市代碼</span>
          <input v-model="form.cityCode" data-testid="history-city-code" type="text" inputmode="numeric" maxlength="20">
        </label>
        <label>
          <span>行政區代碼</span>
          <input v-model="form.districtCode" data-testid="history-district-code" type="text" inputmode="numeric" maxlength="20">
        </label>
        <label>
          <span>段名</span>
          <input v-model="form.sectionName" data-testid="history-section-name" type="text" maxlength="100">
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
        <label>
          <span>排序欄位</span>
          <select v-model="form.sort" data-testid="history-sort">
            <option value="updated_at">最後更新</option>
            <option v-if="historyScope.review" value="received_at">審查收件</option>
            <option v-if="historyScope.review" value="risk_level">風險等級</option>
          </select>
        </label>
        <label>
          <span>排序方向</span>
          <select v-model="form.order" data-testid="history-order">
            <option value="desc">新到舊</option>
            <option value="asc">舊到新</option>
          </select>
        </label>
        </div>
      </div>
      <div class="history-search__actions">
        <p>可直接輸入案件編號或名稱搜尋；需要地區、日期或排序時再開啟進階篩選。</p>
        <button type="submit" class="history-search__submit" data-testid="history-search-submit" @click.prevent="applySearch">搜尋案件</button>
      </div>
    </form>

    <section v-liquid-glass data-lg class="history-search__results lg" aria-labelledby="history-results-title">
      <div class="history-search__results-heading">
        <div>
          <p class="history-search__eyebrow">CASE RECORDS</p>
          <h2 id="history-results-title">案件清單</h2>
        </div>
        <span class="history-search__total">共 {{ total }} 件 · 第 {{ page }} / {{ pageCount }} 頁</span>
      </div>

      <LoadingSkeleton v-if="loading && !rows.length" :rows="5" label="案件歷程載入中" />
      <ErrorState v-else-if="error && !rows.length" :message="error" @retry="loadData" />
      <EmptyState v-else-if="!rows.length" title="目前沒有符合條件的案件" description="調整搜尋條件後，符合授權範圍的案件會顯示在這裡。" />
      <template v-else>
        <p v-if="error" class="history-search__inline-error" role="alert">{{ error }}</p>
        <div class="history-search__table-wrap">
          <table class="history-search__table" aria-label="案件歷程清單" :aria-busy="loading ? 'true' : 'false'">
            <thead>
              <tr>
                <th scope="col">案件編號</th>
                <th scope="col">案件名稱</th>
                <th scope="col">行政區</th>
                <th scope="col">歷程結果</th>
                <th scope="col">可查看資料</th>
                <th scope="col">最後更新</th>
                <th scope="col"><span class="sr-only">操作</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in rows" :key="item.caseId" :data-testid="`history-case-row-${item.caseId}`">
                <th scope="row">{{ item.caseNo }}</th>
                <td>
                  <button type="button" class="history-search__case-link" @click="openCase(item)">{{ item.name }}</button>
                  <div class="history-search__case-meta">
                    <span v-if="item.hasStructuredData">有結構化資料</span>
                    <span v-if="!item.hasDocumentMetadata">尚無文件 metadata</span>
                  </div>
                </td>
                <td>{{ item.district || '—' }}</td>
                <td>
                  <StatusBadge :status="item.historyResultCode" />
                  <small class="history-search__status-note">{{ item.historyResultLabel }}</small>
                </td>
                <td>
                  <div class="history-search__modules">
                    <span v-for="module in item.visibleModules" :key="module">{{ module === 'valuation' ? '估價' : module === 'review' ? '審查' : module }}</span>
                    <span v-if="!item.visibleModules.length">—</span>
                  </div>
                  <RiskBadge v-if="item.riskLevelCode" :risk="item.riskLevelCode" />
                </td>
                <td :title="item.updatedAt">{{ formatDateZhTw(item.updatedAt) }}</td>
                <td><button type="button" class="history-search__detail" :data-testid="`history-open-${item.caseId}`" @click="openCase(item)">查看明細</button></td>
              </tr>
            </tbody>
          </table>
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
.history-search { padding: 0 28px 34px; }
.history-search__permission { color: var(--app-muted); font-size: 12px; }
.history-search__form,
.history-search__results { margin-top: 13px; border: 1px solid rgba(255,255,255,.72); border-radius: var(--app-radius-md); background: rgba(248,250,252,.74); box-shadow: var(--app-shadow-soft); }
.history-search__form { padding: 19px; }
.history-search__form-heading,
.history-search__results-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.history-search__form-tools { display: flex; align-items: center; gap: 8px; }
.history-search__eyebrow { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 10px; font-weight: 900; letter-spacing: .15em; }
.history-search h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 24px; }
.history-search__reset,
.history-search__detail { min-height: 42px; padding: 8px 13px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__reset:hover,
.history-search__detail:hover { border-color: var(--app-accent); color: var(--app-accent-deep); }
.history-search__advanced-toggle { display: inline-flex; min-height: 42px; align-items: center; gap: 7px; padding: 8px 13px; border: 1px solid rgba(46,89,132,.2); border-radius: 8px; color: var(--app-primary-deep); background: var(--app-primary-soft); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__advanced-toggle:hover { border-color: var(--app-primary); }
.history-search__advanced-toggle span { display: inline-grid; min-width: 20px; height: 20px; place-items: center; border-radius: 999px; color: #fff; background: var(--app-primary); font-size: 9px; }
.history-search__quick-fields { display: grid; grid-template-columns: minmax(0, 2fr) minmax(180px, .8fr); gap: 11px; margin-top: 15px; }
.history-search__fields { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 11px; margin-top: 15px; }
.history-search__quick-fields label,
.history-search__fields label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.history-search__quick-fields input,
.history-search__quick-fields select,
.history-search__fields input,
.history-search__fields select { width: 100%; min-height: 44px; padding: 8px 10px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: var(--app-paper-strong); font-size: 12px; }
.history-search__quick-fields input:focus,
.history-search__quick-fields select:focus,
.history-search__fields input:focus,
.history-search__fields select:focus { border-color: var(--app-accent); outline: 3px solid color-mix(in srgb, var(--app-accent) 24%, white); outline-offset: 1px; }
.history-search__advanced { margin-top: 12px; padding: 13px; border: 1px solid var(--app-line); border-radius: 10px; background: rgba(255,255,255,.5); }
.history-search__advanced-heading { display: flex; align-items: baseline; gap: 8px; }
.history-search__advanced-heading strong { color: var(--app-ink); font-size: 11px; }
.history-search__advanced-heading span { color: var(--app-muted); font-size: 10px; }
.history-search__actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 14px; }
.history-search__actions p { margin: 0; color: var(--app-muted); font-size: 11px; line-height: 1.6; }
.history-search__submit { min-width: 120px; min-height: 44px; padding: 8px 15px; border: 1px solid var(--app-accent); border-radius: 8px; color: #fff8f2; background: var(--app-accent); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__submit:hover { background: var(--app-accent-deep); }
.history-search__results { padding: 18px; }
.history-search__total { color: var(--app-muted); font-size: 12px; }
.history-search__inline-error { margin: 12px 0 0; color: #ac3c37; font-size: 13px; }
.history-search__table-wrap { margin-top: 12px; overflow-x: auto; border: 1px solid var(--app-line); border-radius: var(--app-radius-sm); background: var(--app-paper-strong); }
.history-search__table { width: 100%; min-width: 940px; border-collapse: collapse; color: var(--app-ink); background: var(--app-paper-strong); font-size: 13px; }
.history-search__table th,
.history-search__table td { padding: 13px 14px; border-bottom: 1px solid var(--app-line); text-align: left; vertical-align: top; }
.history-search__table thead th { color: var(--app-ink-soft); background: #f5f7fb; font-size: 11px; white-space: nowrap; }
.history-search__table tbody tr:last-child th,
.history-search__table tbody tr:last-child td { border-bottom: 0; }
.history-search__table tbody tr:hover { background: #fbfcfe; }
.history-search__table tbody th { font-weight: 800; white-space: nowrap; }
.history-search__case-link { padding: 0; border: 0; color: var(--app-ink); background: transparent; cursor: pointer; font-size: 13px; font-weight: 800; text-align: left; }
.history-search__case-link:hover { color: var(--app-accent-deep); text-decoration: underline; }
.history-search__case-meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; color: var(--app-muted); font-size: 10px; }
.history-search__case-meta span { padding: 3px 6px; border-radius: 5px; background: #f1f3f6; }
.history-search__status-note { display: block; margin-top: 4px; color: var(--app-muted); font-size: 10px; }
.history-search__modules { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 6px; }
.history-search__modules span { padding: 4px 7px; border-radius: 5px; color: var(--app-blue); background: #edf4fb; font-size: 10px; font-weight: 800; }
.history-search__pagination { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 14px; color: var(--app-muted); font-size: 12px; }
.history-search__pagination button { min-width: 76px; min-height: 44px; padding: 8px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__pagination button:hover:not(:disabled) { border-color: var(--app-accent); color: var(--app-accent-deep); }
.history-search__pagination button:disabled { cursor: not-allowed; opacity: .5; }

@media (max-width: 1100px) {
  .history-search__fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 700px) {
  .history-search { padding-inline: 14px; }
  .history-search__quick-fields { grid-template-columns: 1fr; }
  .history-search__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .history-search__actions { align-items: stretch; flex-direction: column; }
  .history-search__submit { width: 100%; }
  .history-search__form-heading,
  .history-search__results-heading { align-items: flex-start; flex-direction: column; }
  .history-search__form-tools { width: 100%; }
  .history-search__form-tools button { flex: 1; }
}

@media (max-width: 460px) {
  .history-search__fields { grid-template-columns: 1fr; }
}
</style>
