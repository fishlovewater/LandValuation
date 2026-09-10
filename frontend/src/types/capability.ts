export interface ApiCapability {
  key: string
  method: 'GET' | 'POST' | 'PATCH' | 'PUT'
  path: string
  permission?: string
  requestSchema: string
  responseSchema: string
  verifiedFrom: string
  status: 'verified' | 'blocked'
}

export interface ApiCapabilities {
  authLogin: boolean
  authMe: boolean
  reviewSummary: boolean
  reviewCases: boolean
  reviewDetail: boolean
  reviewStart: boolean
  reviewDecision: boolean
  reviewCompletion: boolean
  reviewReport: boolean
}

export const REVIEW_REQUIRED_CAPABILITIES: ApiCapabilities = {
  authLogin: true,
  authMe: true,
  reviewSummary: true,
  reviewCases: true,
  reviewDetail: true,
  reviewStart: true,
  reviewDecision: true,
  reviewCompletion: true,
  reviewReport: true,
}

export const REVIEW_CAPABILITY_MATRIX: ApiCapability[] = [
  {
    key: 'authLogin',
    method: 'POST',
    path: '/api/v1/auth/login',
    requestSchema: 'LoginRequest',
    responseSchema: 'TokenResponse',
    verifiedFrom: 'app/auth/router.py:13-17; app/auth/schemas.py:6-14',
    status: 'verified',
  },
  {
    key: 'authMe',
    method: 'GET',
    path: '/api/v1/auth/me',
    requestSchema: 'Bearer token',
    responseSchema: 'CurrentUserResponse',
    verifiedFrom: 'app/auth/router.py:20-29; app/auth/schemas.py:17-25',
    status: 'verified',
  },
  {
    key: 'reviewSummary',
    method: 'GET',
    path: '/api/v1/review/workbench/summary',
    permission: 'review.execute',
    requestSchema: 'none',
    responseSchema: 'WorkbenchSummaryRead',
    verifiedFrom: 'app/review/router.py:152-157; app/review/workbench_schemas.py:24-28',
    status: 'verified',
  },
  {
    key: 'reviewCases',
    method: 'GET',
    path: '/api/v1/review/workbench/cases',
    permission: 'review.execute',
    requestSchema: 'q, status, risk_level, status_group, limit, offset',
    responseSchema: 'WorkbenchCaseList',
    verifiedFrom: 'app/review/router.py:160-173; app/review/workbench_schemas.py:37-64',
    status: 'verified',
  },
  {
    key: 'reviewDetail',
    method: 'GET',
    path: '/api/v1/review/workbench/cases/{review_id}',
    permission: 'review.execute',
    requestSchema: 'review_id path parameter',
    responseSchema: 'WorkbenchCaseDetailRead',
    verifiedFrom: 'app/review/router.py:186-194; app/review/workbench_schemas.py:114-127',
    status: 'verified',
  },
  {
    key: 'reviewStart',
    method: 'POST',
    path: '/api/v1/review/workbench/cases/{review_id}/start',
    permission: 'review.execute',
    requestSchema: 'empty body',
    responseSchema: 'WorkbenchStartRead',
    verifiedFrom: 'app/review/router.py:251-259; app/review/workbench_schemas.py:147-154',
    status: 'verified',
  },
  {
    key: 'reviewDecision',
    method: 'POST',
    path: '/api/v1/review/findings/{finding_id}/triage',
    permission: 'review.decide',
    requestSchema: 'FindingTriageRequest',
    responseSchema: 'DecisionRead',
    verifiedFrom: 'app/review/router.py:458-475; app/review/schemas.py:227-247,265-277',
    status: 'verified',
  },
  {
    key: 'reviewCompletion',
    method: 'POST',
    path: '/api/v1/review/cases/{review_id}/complete-review',
    permission: 'review.decide',
    requestSchema: 'ReviewCompletionRequest',
    responseSchema: 'DecisionRead',
    verifiedFrom: 'app/review/router.py:630-645; app/review/schemas.py:326-337',
    status: 'verified',
  },
  {
    key: 'reviewReport',
    method: 'GET',
    path: '/api/v1/review/runs/{validation_run_id}/report',
    permission: 'review.execute',
    requestSchema: 'validation_run_id path parameter',
    responseSchema: 'ReviewReport',
    verifiedFrom: 'app/review/router.py:664-670; app/review/reports.py:134-144',
    status: 'verified',
  },
]