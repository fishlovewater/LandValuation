const STATUS: Record<string, string> = {
  RECEIVED: '待分派', ASSIGNED: '已分派', IN_REVIEW: '審查中', CORRECTION_REQUIRED: '待補正',
  RESUBMITTED: '已補正', APPROVED: '已通過', REJECTED: '未通過', CLOSED: '已結案',
}
const RISK: Record<string, string> = { LOW: '低風險', MEDIUM: '中風險', HIGH: '高風險', CRITICAL: '重大風險' }

export function statusLabel(value?: string | null): string { return value && STATUS[value] ? STATUS[value] : '未知狀態' }
export function riskLabel(value?: string | null): string { return value && RISK[value] ? RISK[value] : '未評估' }
export function severityLabel(value?: string | null): string {
  return ({ CRITICAL: '重大', ERROR: '錯誤', WARNING: '警告', INFO: '資訊' } as Record<string, string>)[value ?? ''] ?? '未知'
}