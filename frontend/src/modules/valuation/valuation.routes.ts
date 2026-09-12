import type { RouteRecordRaw } from 'vue-router'
import { VALUATION_ROLES } from '../../router/roleAccess'

const lazyDashboard = () => import('./views/ValuationDashboardView.vue')
const lazyPrepare = () => import('./views/ValuationPrepareView.vue')
const lazySubmit = () => import('./views/ValuationSubmitView.vue')

const prepareMeta = {
  requiresAuth: true,
  roles: [...VALUATION_ROLES],
  permissions: ['case.read', 'valuation.read', 'valuation.update', 'document.download'],
  subsystem: '估價作業',
}

const submitMeta = {
  requiresAuth: true,
  roles: [...VALUATION_ROLES],
  permissions: ['case.read', 'valuation.read', 'valuation.submit_review', 'valuation.update', 'document.download'],
  subsystem: '估價作業',
}

export const valuationRoutes: readonly RouteRecordRaw[] = [
  {
    path: 'valuation/dashboard',
    name: 'valuation-dashboard',
    component: lazyDashboard,
    meta: {
      requiresAuth: true,
      roles: [...VALUATION_ROLES],
      permissions: ['case.read', 'valuation.read'],
      title: '估價作業',
      subsystem: '估價作業',
      description: '查看目前可用的估價案件與下一個作業動作。',
    },
  },
  {
    path: 'valuation/cases/:caseId',
    name: 'valuation-case',
    component: lazyPrepare,
    props: { stage: 'case' },
    meta: {
      ...prepareMeta,
      title: '案件基本資料',
      description: '確認案件基本資料後開始估價流程。',
    },
  },
  {
    path: 'valuation/cases/:caseId/documents',
    name: 'valuation-documents',
    component: lazyPrepare,
    props: { stage: 'documents' },
    meta: {
      ...prepareMeta,
      title: '文件與辨識',
      description: '上傳、預覽並辨識估價來源文件。',
    },
  },
  {
    path: 'valuation/cases/:caseId/ai-review',
    name: 'valuation-ai-review',
    component: lazyPrepare,
    props: { stage: 'ai-review' },
    meta: {
      ...prepareMeta,
      title: 'AI 結果確認',
      description: '人工確認智能辨識結果與原文件證據。',
    },
  },
  {
    path: 'valuation/cases/:caseId/data',
    name: 'valuation-data',
    component: lazyPrepare,
    props: { stage: 'data' },
    meta: {
      ...prepareMeta,
      title: '資料補齊',
      description: '補齊宗地、比準地與正式估價欄位。',
    },
  },
  {
    path: 'valuation/cases/:caseId/calculation',
    name: 'valuation-calculation',
    component: lazyPrepare,
    props: { stage: 'calculation' },
    meta: {
      ...prepareMeta,
      title: '計算與檢核',
      description: '執行正式計算並處理檢核結果。',
    },
  },
  {
    path: 'valuation/cases/:caseId/report',
    name: 'valuation-report',
    component: lazySubmit,
    meta: {
      ...submitMeta,
      title: '查估書與送審',
      description: '確認正式查估書、輸出文件並送交審查。',
    },
  },
  {
    path: 'valuation/cases/:caseId/prepare',
    name: 'valuation-prepare',
    component: lazyPrepare,
    meta: {
      ...prepareMeta,
      title: '準備估價資料',
      description: '確認案件來源、文件與正式估價資料。',
    },
  },
  {
    path: 'valuation/cases/:caseId/submit',
    name: 'valuation-submit',
    component: lazySubmit,
    meta: {
      ...submitMeta,
      title: '送審確認',
      description: '確認檢核與完整送審 PDF 後送交審查。',
    },
  },
]
