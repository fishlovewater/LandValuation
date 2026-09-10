const STATUS_LABELS: Readonly<Record<string, string>> = {
  DRAFT: '草稿',
  PROCESSING: '處理中',
  REVIEWING: '審查中',
  CORRECTION: '補正中',
  COMPLETED: '已完成',
  ARCHIVED: '已封存',
  IN_REVIEW: '審查中',
  REVISION_REQUIRED: '需補正',
  REVIEW_COMPLETED: '審查完成',
  RECEIVED: '已收件',
  PREPROCESSING: '前處理中',
  PENDING_MATERIALS: '待補資料',
  READY_FOR_REVIEW: '待審查',
  ANALYZING: '分析中',
  REVIEW_REQUIRED: '需審查',
  RETURNED_FOR_REVISION: '退回補正',
  SUPPLEMENT_REQUIRED: '待補件',
  EXPERT_REVIEW: '專家審查',
  APPROVED: '已核准',
  REJECTED: '已退件',
  SUBMITTED: '已送出',
  PASSED: '審查通過',
  RETURNED: '已退回',
  IN_PROGRESS: '處理中',
  RUNNING: '執行中',
  FAILED: '執行失敗',
  READY: '可執行',
  CHECKED: '已檢核',
  FINAL: '已完成',
}

const RISK_LABELS: Readonly<Record<string, string>> = {
  LOW: '低風險',
  MEDIUM: '中風險',
  HIGH: '高風險',
  CRITICAL: '極高風險',
}

const DECISION_LABELS: Readonly<Record<string, string>> = {
  CONFIRMED_ISSUE: '確認問題',
  DISMISSED_FALSE_POSITIVE: '排除誤報',
  EXPERT_REVIEW: '轉交專家審查',
  ACCEPTED: '接受系統結果',
  PARTIALLY_ACCEPTED: '部分接受',
  REQUIRES_SUPPLEMENT: '要求補件',
  REJECTED: '駁回系統結果',
  RETURNED_FOR_REVISION: '退回補正',
  SUPPLEMENT_REQUIRED: '要求補件',
  APPROVED: '核准',
  REVIEW_COMPLETED: '完成審查',
}

function normalizeEnumValue(value: string | null | undefined): string {
  return typeof value === 'string' ? value.trim().toUpperCase() : ''
}

function lookupLabel(
  value: string | null | undefined,
  labels: Readonly<Record<string, string>>,
  fallback: string,
): string {
  return labels[normalizeEnumValue(value)] ?? fallback
}

export function statusLabel(value: string | null | undefined): string {
  return lookupLabel(value, STATUS_LABELS, '未知狀態')
}

export function riskLabel(value: string | null | undefined): string {
  return lookupLabel(value, RISK_LABELS, '未知風險')
}

export function decisionLabel(value: string | null | undefined): string {
  return lookupLabel(value, DECISION_LABELS, '未定義決定')
}

export function normalizedEnumValue(value: string | null | undefined): string {
  return normalizeEnumValue(value)
}

export function isKnownStatus(value: string | null | undefined): boolean {
  return Boolean(STATUS_LABELS[normalizeEnumValue(value)])
}

export function isKnownRisk(value: string | null | undefined): boolean {
  return Boolean(RISK_LABELS[normalizeEnumValue(value)])
}
