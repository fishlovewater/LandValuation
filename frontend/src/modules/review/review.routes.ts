import type { RouteRecordRaw } from 'vue-router'
import ReviewDashboardView from './views/ReviewDashboardView.vue'
import ReviewWorkbenchView from './views/ReviewWorkbenchView.vue'

export const reviewRoutes: RouteRecordRaw[] = [
  { path:'review/dashboard', component:ReviewDashboardView, meta:{ requiresAuth:true, permission:'review.execute' } },
  { path:'review/cases/:reviewId', component:ReviewWorkbenchView, meta:{ requiresAuth:true, permission:'review.execute' } },
]