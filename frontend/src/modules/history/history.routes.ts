import type { RouteRecordRaw } from 'vue-router'
import { HISTORY_ROLES } from '../../router/roleAccess'

const lazySearch = () => import('./views/HistorySearchView.vue')
const lazyCase = () => import('./views/HistoryCaseView.vue')

const historyMeta = {
  requiresAuth: true,
  roles: [...HISTORY_ROLES],
}

export const historyRoutes: readonly RouteRecordRaw[] = [
  {
    path: 'history/search',
    name: 'history-search',
    component: lazySearch,
    meta: {
      ...historyMeta,
      title: '案件歷程',
      subsystem: '案件歷程',
      description: '在授權範圍內搜尋案件與文件歷程。',
    },
  },
  {
    path: 'history/cases/:caseId',
    name: 'history-case',
    component: lazyCase,
    meta: {
      ...historyMeta,
      title: '案件歷程明細',
      subsystem: '案件歷程',
      description: '查看案件的授權資料、文件與時間軸。',
    },
  },
]
