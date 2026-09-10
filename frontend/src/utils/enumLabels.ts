const STATUS: Record<string, string> = {
  RECEIVED: '已收件',
  PREPROCESSING: '前處理中',
  PENDING_MATERIALS: '待補資料',
  READY_FOR_REVIEW: '待審查',
  ANALYZING: '分析中',
  REVIEW_REQUIRED: '需人工審查',
  RETURNED_FOR_REVISION: '退回修正',
  SUPPLEMENT_REQUIRED: '要求補正',
  EXPERT_REVIEW: '專家審查',
  APPROVED: '已通過',
  REVIEW_COMPLETED: '審查完成',
}
const RISK: Record<string, string> = { LOW: '低風險', MEDIUM: '中風險', HIGH: '高風險', CRITICAL: '重大風險' }

export function statusLabel(value?: string | null): string { return value && STATUS[value] ? STATUS[value] : '未知狀態' }
export function riskLabel(value?: string | null): string { return value && RISK[value] ? RISK[value] : '未評估' }
export function severityLabel(value?: string | null): string {
  return ({ CRITICAL: '重大', ERROR: '錯誤', WARNING: '警告', INFO: '資訊' } as Record<string, string>)[value ?? ''] ?? '未知'
}