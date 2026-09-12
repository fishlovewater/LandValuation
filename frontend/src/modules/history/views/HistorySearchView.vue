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
  form.dateFrom,
  form.dateTo,
  form.dateField !== 'updated_at' ? form.dateField : '',
  form.sort !== 'updated_at' ? form.sort : '',
  form.order !== 'desc' ? form.order : '',
].filter(Boolean).length)

function routeHasAdvancedFilters(): boolean {
  return [
    'districtCode', 'district_code', 'sectionName', 'section_name',
    'dateField', 'date_field', 'dateFrom', 'date_from', 'dateTo', 'date_to', 'sort', 'order',
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
    <PageHeader
      eyebrow="案件歷史"
      title="案件查詢"
      description="先確認目前帳號的可查看範圍，再搜尋案件並進入案件資料或下載相關文件。"
    >
      <template #actions>
        <span class="history-search__permission">
          <span class="history-search__permission-dot" aria-hidden="true"></span>
          {{ formatPermissionText() }}
        </span>
      </template>
    </PageHeader>

    <ol class="history-search__flow" aria-label="案件歷史操作流程">
      <li class="is-complete">
        <span>1</span>
        <div><strong>確認權限</strong><small>依登入帳號自動判斷</small></div>
      </li>
      <li class="is-current">
        <span>2</span>
        <div><strong>搜尋案件</strong><small>輸入案件編號、名稱或地號</small></div>
      </li>
      <li>
        <span>3</span>
        <div><strong>查看資料 / 下載文件</strong><small>進入案件後查看授權內容</small></div>
      </li>
    </ol>

    <section v-liquid-glass data-lg class="history-search__workspace lg">
      <form class="history-search__form" data-testid="history-search-form" @submit.prevent="applySearch">
        <div class="history-search__form-heading">
          <div>
            <p class="history-search__eyebrow">案件搜尋</p>
            <h2>搜尋案件</h2>
            <p>先用關鍵字快速查找；需要縮小範圍時再開啟進階篩選。</p>
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
              {{ advancedOpen ? '收合篩選' : '進階篩選' }}
              <span v-if="advancedFilterCount">{{ advancedFilterCount }}</span>
            </button>
            <button type="button" class="history-search__reset" data-testid="history-search-reset" @click="resetSearch">清除</button>
          </div>
        </div>

        <div class="history-search__quick-fields">
          <label class="history-search__keyword-field">
            <span>關鍵字</span>
            <div class="history-search__search-input-wrap">
              <span aria-hidden="true">⌕</span>
              <input v-model="form.keyword" data-testid="history-keyword" type="search" placeholder="搜尋案件編號、案件名稱或地號" autocomplete="off">
            </div>
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
          <button type="submit" class="history-search__submit" data-testid="history-search-submit" @click.prevent="applySearch">搜尋案件</button>
        </div>

        <div
          id="history-advanced-filters"
          v-show="advancedOpen"
          class="history-search__advanced"
          data-testid="history-advanced-filters"
        >
          <div class="history-search__advanced-heading">
            <strong>進階篩選</strong>
            <span>查估範圍固定為新北市，可依行政區、地段、日期與排序縮小案件範圍。</span>
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
        <p v-if="filterError" class="history-search__filter-error" role="alert">{{ filterError }}</p>
      </form>

      <section class="history-search__results" aria-labelledby="history-results-title">
        <div class="history-search__results-heading">
          <div>
            <p class="history-search__eyebrow">案件列表</p>
            <h2 id="history-results-title">搜尋結果</h2>
          </div>
          <span class="history-search__total">共 {{ total }} 件 · 第 {{ page }} / {{ pageCount }} 頁</span>
        </div>

        <LoadingSkeleton v-if="loading && !rows.length" :rows="5" label="案件歷程載入中" />
        <ErrorState v-else-if="error && !rows.length" :message="error" @retry="loadData" />
        <EmptyState v-else-if="!rows.length" title="目前沒有符合條件的案件" description="調整搜尋條件後，符合授權範圍的案件會顯示在這裡。" />
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
                <span class="history-search__case-no">{{ item.caseNo }}</span>
                <button type="button" class="history-search__case-link" @click="openCase(item)">{{ item.name }}</button>
                <div class="history-search__case-meta">
                  <span>{{ historyLocationLabel(item.cityCode, item.districtCode) }}</span>
                  <span v-if="item.hasStructuredData">有案件資料</span>
                  <span v-if="!item.hasDocumentMetadata">尚無附件</span>
                </div>
              </div>

              <div class="history-search__case-status">
                <span class="history-search__column-label">歷程結果</span>
                <StatusBadge :status="item.historyResultCode" />
              </div>

              <div class="history-search__case-access">
                <span class="history-search__column-label">可查看資料</span>
                <div class="history-search__modules">
                  <span v-for="module in item.visibleModules" :key="module">{{ module === 'valuation' ? '估價資料' : module === 'review' ? '審查資料' : '案件資料' }}</span>
                  <span v-if="!item.visibleModules.length">—</span>
                </div>
                <RiskBadge v-if="item.riskLevelCode" :risk="item.riskLevelCode" />
              </div>

              <div class="history-search__case-updated">
                <span class="history-search__column-label">最後更新</span>
                <strong :title="item.updatedAt">{{ formatDateZhTw(item.updatedAt) }}</strong>
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
  </section>
</template>

<style scoped>
.history-search { padding: 0 28px 36px; }
.history-search__permission { display:inline-flex; align-items:center; gap:8px; padding:8px 11px; border:1px solid var(--app-line); border-radius:999px; color:var(--app-ink-soft); background:rgba(255,255,255,.78); font-size:11px; font-weight:800; }
.history-search__permission-dot { width:7px; height:7px; border-radius:999px; background:var(--app-green); box-shadow:0 0 0 4px color-mix(in srgb, var(--app-green) 12%, transparent); }
.history-search__flow { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0; margin:0 0 15px; padding:0; border:1px solid var(--app-line); border-radius:12px; overflow:hidden; background:rgba(255,255,255,.68); list-style:none; }
.history-search__flow li { position:relative; display:flex; align-items:center; gap:10px; min-width:0; padding:11px 15px; }
.history-search__flow li + li { border-left:1px solid var(--app-line); }
.history-search__flow li > span { display:grid; width:26px; height:26px; flex:0 0 26px; place-items:center; border:1px solid var(--app-line); border-radius:999px; color:var(--app-muted); background:#fff; font-size:10px; font-weight:900; }
.history-search__flow li div { display:grid; min-width:0; gap:2px; }
.history-search__flow strong { color:var(--app-ink-soft); font-size:11px; }
.history-search__flow small { overflow:hidden; color:var(--app-muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.history-search__flow .is-complete > span { border-color:#b8d8c6; color:#276345; background:#eef7f2; }
.history-search__flow .is-current { background:color-mix(in srgb, var(--app-primary-soft) 72%, white); }
.history-search__flow .is-current > span { border-color:var(--app-primary); color:#fff; background:var(--app-primary); }
.history-search__flow .is-current strong { color:var(--app-primary-deep); }
.history-search__workspace { overflow:hidden; border:1px solid rgba(255,255,255,.82); border-radius:var(--app-radius-md); background:rgba(248,250,252,.76); box-shadow:var(--app-shadow-soft); }
.history-search__form { padding:20px; }
.history-search__form-heading,
.history-search__results-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.history-search__form-tools { display: flex; align-items: center; gap: 8px; }
.history-search__eyebrow { margin: 0 0 5px; color: var(--app-accent-deep); font-size: 10px; font-weight: 900; letter-spacing: .15em; }
.history-search h2 { margin: 0; color: var(--app-ink); font-family: var(--app-font-display); font-size: 23px; }
.history-search__form-heading p:not(.history-search__eyebrow) { margin:5px 0 0; color:var(--app-muted); font-size:11px; }
.history-search__reset,
.history-search__detail { min-height: 42px; padding: 8px 13px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__reset:hover,
.history-search__detail:hover { border-color: var(--app-accent); color: var(--app-accent-deep); }
.history-search__advanced-toggle { display: inline-flex; min-height: 42px; align-items: center; gap: 7px; padding: 8px 13px; border: 1px solid rgba(46,89,132,.2); border-radius: 8px; color: var(--app-primary-deep); background: var(--app-primary-soft); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__advanced-toggle:hover { border-color: var(--app-primary); }
.history-search__advanced-toggle span { display: inline-grid; min-width: 20px; height: 20px; place-items: center; border-radius: 999px; color: #fff; background: var(--app-primary); font-size: 9px; }
.history-search__quick-fields { display: grid; grid-template-columns:minmax(0,1fr) minmax(170px,.28fr) auto; align-items:end; gap: 10px; margin-top: 16px; }
.history-search__fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 11px; margin-top: 13px; }
.history-search__quick-fields label,
.history-search__fields label { display: grid; gap: 5px; color: var(--app-ink-soft); font-size: 11px; font-weight: 800; }
.history-search__search-input-wrap { display:flex; min-height:46px; align-items:center; gap:8px; padding:0 11px; border:1px solid var(--app-line); border-radius:9px; background:var(--app-paper-strong); }
.history-search__search-input-wrap > span { color:var(--app-muted); font-size:18px; transform:rotate(-12deg); }
.history-search__search-input-wrap input { width:100%; min-width:0; min-height:42px; flex:1; padding:0; border:0 !important; outline:0 !important; background:transparent !important; box-shadow:none !important; }
.history-search__quick-fields select,
.history-search__fields input,
.history-search__fields select { width: 100%; min-height: 44px; padding: 8px 10px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: var(--app-paper-strong); font-size: 12px; }
.history-search__search-input-wrap:focus-within,
.history-search__quick-fields select:focus,
.history-search__fields input:focus,
.history-search__fields select:focus { border-color: var(--app-accent); outline: 3px solid color-mix(in srgb, var(--app-accent) 24%, white); outline-offset: 1px; }
.history-search__advanced { margin-top: 12px; padding: 13px; border: 1px solid var(--app-line); border-radius: 10px; background: rgba(255,255,255,.5); }
.history-search__advanced-heading { display: flex; align-items: baseline; gap: 8px; }
.history-search__advanced-heading strong { color: var(--app-ink); font-size: 11px; }
.history-search__advanced-heading span { color: var(--app-muted); font-size: 10px; }
.history-search__filter-error { margin:10px 0 0; padding:9px 11px; border:1px solid #ebc7c5; border-radius:8px; color:#963b36; background:#fff6f5; font-size:11px; font-weight:700; }
.history-search__submit { min-width: 112px; min-height: 46px; padding: 8px 15px; border: 1px solid var(--app-accent); border-radius: 9px; color: #fff8f2; background: var(--app-accent); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__submit:hover { background: var(--app-accent-deep); }
.history-search__results { padding:18px 20px 20px; border-top:1px solid var(--app-line); background:rgba(255,255,255,.48); }
.history-search__total { color: var(--app-muted); font-size: 12px; }
.history-search__inline-error { margin: 12px 0 0; color: #ac3c37; font-size: 13px; }
.history-search__case-list { display:grid; gap:8px; margin-top:12px; }
.history-search__case-row { display:grid; grid-template-columns:minmax(260px,1.7fr) minmax(115px,.55fr) minmax(150px,.7fr) minmax(115px,.55fr) auto; align-items:center; gap:14px; padding:13px 14px; border:1px solid var(--app-line); border-radius:10px; background:var(--app-paper-strong); transition:border-color .18s ease, box-shadow .18s ease, transform .18s ease; }
.history-search__case-row:hover { border-color:color-mix(in srgb, var(--app-primary) 34%, var(--app-line)); box-shadow:0 8px 22px rgba(35,56,78,.07); transform:translateY(-1px); }
.history-search__case-primary { display:grid; min-width:0; gap:4px; }
.history-search__case-no { color:var(--app-muted); font-size:10px; font-weight:900; letter-spacing:.06em; }
.history-search__case-link { padding: 0; border: 0; color: var(--app-ink); background: transparent; cursor: pointer; font-size: 13px; font-weight: 800; text-align: left; }
.history-search__case-link:hover { color: var(--app-accent-deep); text-decoration: underline; }
.history-search__case-meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; color: var(--app-muted); font-size: 10px; }
.history-search__case-meta span { padding: 3px 6px; border-radius: 5px; background: #f1f3f6; }
.history-search__case-status { display:grid; justify-items:start; gap:4px; }
.history-search__column-label { color:var(--app-muted); font-size:9px; font-weight:800; }
.history-search__case-access,
.history-search__case-updated { display:grid; gap:5px; }
.history-search__case-updated strong { color:var(--app-ink-soft); font-size:11px; }
.history-search__modules { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 6px; }
.history-search__modules span { padding: 4px 7px; border-radius: 5px; color: var(--app-blue); background: #edf4fb; font-size: 10px; font-weight: 800; }
.history-search__detail { display:inline-flex; align-items:center; gap:7px; justify-self:end; white-space:nowrap; }
.history-search__detail span { color:var(--app-accent); font-size:14px; }
.history-search__pagination { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 14px; color: var(--app-muted); font-size: 12px; }
.history-search__pagination button { min-width: 76px; min-height: 44px; padding: 8px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink-soft); background: var(--app-paper-strong); cursor: pointer; font-size: 12px; font-weight: 800; }
.history-search__pagination button:hover:not(:disabled) { border-color: var(--app-accent); color: var(--app-accent-deep); }
.history-search__pagination button:disabled { cursor: not-allowed; opacity: .5; }

@media (max-width: 1180px) {
  .history-search__case-row { grid-template-columns:minmax(240px,1.4fr) minmax(110px,.5fr) minmax(145px,.7fr) auto; }
  .history-search__case-updated { display:none; }
}

@media (max-width: 980px) {
  .history-search__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .history-search__case-row { grid-template-columns:minmax(220px,1.5fr) minmax(110px,.55fr) auto; }
  .history-search__case-access { display:none; }
}

@media (max-width: 700px) {
  .history-search { padding-inline: 14px; }
  .history-search__flow { grid-template-columns:1fr; }
  .history-search__flow li + li { border-top:1px solid var(--app-line); border-left:0; }
  .history-search__flow small { white-space:normal; }
  .history-search__quick-fields { grid-template-columns: 1fr; }
  .history-search__submit { width: 100%; }
  .history-search__form-heading,
  .history-search__results-heading { align-items: flex-start; flex-direction: column; }
  .history-search__form-tools { width: 100%; }
  .history-search__form-tools button { flex: 1; }
  .history-search__case-row { grid-template-columns:1fr auto; align-items:start; }
  .history-search__case-status { justify-self:end; }
  .history-search__detail { grid-column:1 / -1; justify-self:stretch; justify-content:center; }
}

@media (max-width: 460px) {
  .history-search__fields { grid-template-columns: 1fr; }
  .history-search__case-row { grid-template-columns:1fr; }
  .history-search__case-status { justify-self:start; }
}
</style>
