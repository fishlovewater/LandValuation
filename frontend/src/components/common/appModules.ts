import type { Component } from 'vue'
import {
  PhChartLineUp as ChartLineUp,
  PhClockCounterClockwise as History,
  PhFiles as Files,
  PhUserGear as UserGear,
} from '@phosphor-icons/vue'
import { HISTORY_ROLES, VALUATION_ROLES } from '../../router/roleAccess'

export interface AppModule {
  key: string
  label: string
  description: string
  path: string
  permission?: string
  roles?: readonly string[]
  icon: Component
}

export const APP_MODULES: readonly AppModule[] = [
  {
    key: 'valuation',
    label: '估價作業',
    description: '案件與估價資料',
    path: '/app/valuation/dashboard',
    permission: 'valuation.read',
    roles: VALUATION_ROLES,
    icon: ChartLineUp,
  },
  {
    key: 'review',
    label: '審查工作台',
    description: '疑點與審查決定',
    path: '/app/review/dashboard',
    permission: 'review.execute',
    icon: Files,
  },
  {
    key: 'history',
    label: '案件歷程',
    description: '案件與文件回看',
    path: '/app/history/search',
    roles: HISTORY_ROLES,
    icon: History,
  },
  {
    key: 'access-admin',
    label: '帳號申請管理',
    description: '核准或拒絕工作帳號申請',
    path: '/app/admin/access-requests',
    permission: 'auth.manage',
    icon: UserGear,
  },
]

export function authorizedModules(permissions: readonly string[], roles: readonly string[] = []): AppModule[] {
  const granted = new Set(permissions)
  return APP_MODULES.filter(
    (module) =>
      (!module.permission || granted.has(module.permission)) &&
      (!module.roles?.length || module.roles.some((role) => roles.includes(role))),
  )
}
