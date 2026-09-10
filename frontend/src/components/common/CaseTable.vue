<script setup lang="ts">
import { computed } from 'vue'
import EmptyState from './EmptyState.vue'
import ErrorState from './ErrorState.vue'
import LoadingSkeleton from './LoadingSkeleton.vue'
import StatusBadge from './StatusBadge.vue'
import type { CaseSummary } from '../../types/case'
import { formatDateZhTw } from '../../utils/formatters'

type SortDirection = 'asc' | 'desc'
type FilterOption = string | { value: string; label: string }
type FilterValues = Record<string, string | undefined>

const props = withDefaults(
  defineProps<{
    cases?: CaseSummary[]
    items?: CaseSummary[]
    total?: number
    page?: number
    pageSize?: number
    sortBy?: string
    sortDirection?: SortDirection
    filters?: FilterValues
    filterOptions?: Record<string, FilterOption[]>
    loading?: boolean
    error?: string
    emptyTitle?: string
    emptyDescription?: string
    rowTestIdPrefix?: string
  }>(),
  {
    cases: undefined,
    items: undefined,
    total: undefined,
    page: 1,
    pageSize: 20,
    sortBy: undefined,
    sortDirection: 'desc',
    filters: () => ({}),
    filterOptions: () => ({}),
    loading: false,
    error: undefined,
    emptyTitle: '目前沒有案件',
    emptyDescription: '符合目前條件的案件會顯示在這裡。',
    rowTestIdPrefix: 'case-row',
  },
)

const emit = defineEmits<{
  'page-change': [value: { page: number; pageSize: number }]
  'sort-change': [value: { sortBy: string; sortDirection: SortDirection }]
  'filter-change': [value: FilterValues]
  'query-change': [value: Record<string, string>]
  select: [value: CaseSummary]
  retry: []
}>()

const rows = computed(() => props.cases ?? props.items ?? [])
const totalRows = computed(() => props.total ?? rows.value.length)
const pageCount = computed(() => Math.max(1, Math.ceil(totalRows.value / Math.max(1, props.pageSize))))
const pageNumbers = computed(() => Array.from({ length: pageCount.value }, (_, index) => index + 1))
const hasRows = computed(() => rows.value.length > 0)

function normalizeFilterOption(option: FilterOption): { value: string; label: string } {
  return typeof option === 'string' ? { value: option, label: option } : option
}

function filterValue(name: string): string {
  return props.filters?.[name] ?? ''
}

function updateFilter(name: string, value: string): void {
  const nextFilters: FilterValues = { ...props.filters }
  if (value) nextFilters[name] = value
  else delete nextFilters[name]
  emit('filter-change', nextFilters)
  const filterQuery = Object.fromEntries(
    Object.keys(props.filterOptions).map((filterName) => [filterName, nextFilters[filterName] ?? '']),
  )
  emitQuery({ ...filterQuery, page: String(props.page), pageSize: String(props.pageSize) })
}

function emitQuery(
  overrides: Record<string, string>,
  sortState: { sortBy?: string; sortDirection?: SortDirection } = {},
): void {
  const query: Record<string, string> = { ...overrides }
  const sortBy = sortState.sortBy ?? props.sortBy
  const sortDirection = sortState.sortDirection ?? props.sortDirection
  if (sortBy) query.sortBy = sortBy
  if (sortDirection) query.sortDirection = sortDirection
  emit('query-change', query)
}

function toggleSort(column: string): void {
  const sortDirection: SortDirection =
    props.sortBy === column && props.sortDirection === 'asc' ? 'desc' : 'asc'
  const payload = { sortBy: column, sortDirection }
  emit('sort-change', payload)
  emitQuery(
    { sortBy: column, sortDirection, page: String(props.page), pageSize: String(props.pageSize) },
    payload,
  )
}

function goToPage(page: number): void {
  if (page < 1 || page > pageCount.value || page === props.page) return
  emit('page-change', { page, pageSize: props.pageSize })
  emitQuery({ page: String(page), pageSize: String(props.pageSize) })
}

function ariaSort(column: string): 'none' | 'ascending' | 'descending' {
  if (props.sortBy !== column) return 'none'
  return props.sortDirection === 'asc' ? 'ascending' : 'descending'
}

function selectRow(row: CaseSummary): void {
  emit('select', row)
}
</script>

<template>
  <div class="case-table">
    <div v-if="Object.keys(filterOptions).length" class="case-table__filters" aria-label="案件篩選">
      <label v-for="(options, name) in filterOptions" :key="name" class="case-table__filter">
        <span>{{ name === 'status' ? '案件狀態' : name === 'riskLevel' ? '風險等級' : name === 'statusGroup' ? '工作群組' : name }}</span>
        <select
          :name="name"
          :value="filterValue(name)"
          @change="updateFilter(name, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="option in options" :key="normalizeFilterOption(option).value" :value="normalizeFilterOption(option).value">
            {{ normalizeFilterOption(option).label }}
          </option>
        </select>
      </label>
    </div>

    <LoadingSkeleton v-if="loading" :rows="Math.min(pageSize, 8)" label="案件載入中" />
    <ErrorState v-else-if="error" :message="error" @retry="emit('retry')" />
    <EmptyState v-else-if="!hasRows" :title="emptyTitle" :description="emptyDescription" />

    <template v-else>
      <div class="case-table__scroll">
        <table class="case-table__table" aria-label="案件列表" :aria-busy="loading ? 'true' : 'false'">
          <thead>
            <tr>
              <th scope="col" :aria-sort="ariaSort('caseNo')">
                <button type="button" data-sort="caseNo" @click="toggleSort('caseNo')">案件編號</button>
              </th>
              <th scope="col" :aria-sort="ariaSort('name')">
                <button type="button" data-sort="name" @click="toggleSort('name')">案件名稱</button>
              </th>
              <th scope="col">行政區</th>
              <th scope="col" :aria-sort="ariaSort('status')">
                <button type="button" data-sort="status" @click="toggleSort('status')">狀態</button>
              </th>
              <th scope="col" :aria-sort="ariaSort('updatedAt')">
                <button type="button" data-sort="updatedAt" @click="toggleSort('updatedAt')">最後更新</button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.caseId"
              :data-testid="`${rowTestIdPrefix}-${row.reviewId ?? row.caseId}`"
              :class="{ 'case-table__row--selectable': Boolean(row.reviewId) }"
              :tabindex="row.reviewId ? 0 : undefined"
              @click="selectRow(row)"
              @keydown.enter="selectRow(row)"
              @keydown.space.prevent="selectRow(row)"
            >
              <th scope="row">{{ row.caseNo }}</th>
              <td>{{ row.name }}</td>
              <td>{{ row.district || '—' }}</td>
              <td><StatusBadge :status="row.status" /></td>
              <td :title="row.updatedAt">{{ formatDateZhTw(row.updatedAt) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <nav v-if="pageCount > 1" class="case-table__pagination" aria-label="案件列表分頁">
        <button
          type="button"
          class="case-table__page"
          data-page="previous"
          :disabled="page <= 1"
          aria-label="上一頁"
          @click="goToPage(page - 1)"
        >
          上一頁
        </button>
        <button
          v-for="pageNumber in pageNumbers"
          :key="pageNumber"
          type="button"
          class="case-table__page"
          :data-page="pageNumber"
          :aria-current="pageNumber === page ? 'page' : undefined"
          :class="{ 'case-table__page--current': pageNumber === page }"
          @click="goToPage(pageNumber)"
        >
          {{ pageNumber }}
        </button>
        <button
          type="button"
          class="case-table__page"
          data-page="next"
          :disabled="page >= pageCount"
          aria-label="下一頁"
          @click="goToPage(page + 1)"
        >
          下一頁
        </button>
      </nav>
    </template>
  </div>
</template>

<style scoped>
.case-table {
  display: grid;
  gap: 14px;
}

.case-table__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
}

.case-table__filter {
  display: grid;
  min-width: 180px;
  gap: 5px;
  color: var(--app-ink-soft);
  font-size: 12px;
  font-weight: 800;
}

.case-table__filter select {
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: var(--app-paper-strong);
}

.case-table__scroll {
  overflow-x: auto;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
}

.case-table__table {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
  color: var(--app-ink);
  background: var(--app-paper-strong);
  font-size: 14px;
}

.case-table__table th,
.case-table__table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--app-line);
  text-align: left;
  vertical-align: middle;
}

.case-table__table thead th {
  color: var(--app-ink-soft);
  background: #f5f7fb;
  font-size: 12px;
  white-space: nowrap;
}

.case-table__table tbody th { font-weight: 800; }
.case-table__table tbody tr:last-child th,
.case-table__table tbody tr:last-child td { border-bottom: 0; }
.case-table__table tbody tr:hover { background: #fbfcfe; }
.case-table__row--selectable { cursor: pointer; }
.case-table__row--selectable:focus-visible { outline: 3px solid color-mix(in srgb, var(--app-accent) 70%, white); outline-offset: -3px; }

.case-table__table thead button {
  min-height: 44px;
  margin: -10px -12px;
  padding: 10px 12px;
  border: 0;
  color: inherit;
  background: transparent;
  cursor: pointer;
  font-size: inherit;
  font-weight: inherit;
  text-align: left;
}

.case-table__pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.case-table__page {
  min-width: 44px;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.case-table__page:hover:not(:disabled),
.case-table__page--current {
  border-color: var(--app-accent);
  color: var(--app-accent-deep);
  background: var(--app-accent-soft);
}

.case-table__page:disabled { cursor: not-allowed; opacity: 0.5; }
</style>
