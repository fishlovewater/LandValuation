import type { RouteRecordRaw } from 'vue-router'
import ReviewDashboardView from './views/ReviewDashboardView.vue'

export const reviewRoutes: RouteRecordRaw[] = [
  { path:'review/dashboard', component:ReviewDashboardView, meta:{ requiresAuth:true, permission:'review.execute' } },
]