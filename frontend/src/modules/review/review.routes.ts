import type { RouteRecordRaw } from 'vue-router'
import ReviewDashboardView from './views/ReviewDashboardView.vue'
import ReviewWorkbenchView from './views/ReviewWorkbenchView.vue'
import ReviewResultView from './views/ReviewResultView.vue'

export const reviewRoutes: RouteRecordRaw[] = [
  { path:'review/dashboard', component:ReviewDashboardView, meta:{ requiresAuth:true, permission:'review.execute' } },
  { path:'review/cases/:reviewId', component:ReviewWorkbenchView, meta:{ requiresAuth:true, permission:'review.execute' } },
  { path:'review/cases/:reviewId/result', component:ReviewResultView, meta:{ requiresAuth:true, permission:'review.execute' } },
]