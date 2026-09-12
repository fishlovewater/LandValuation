export const REVIEW_PENDING_STATUSES = new Set([
  'RECEIVED',
  'PREPROCESSING',
  'READY_FOR_REVIEW',
])

export const REVIEW_IN_PROGRESS_STATUSES = new Set([
  'ANALYZING',
  'REVIEW_REQUIRED',
  'EXPERT_REVIEW',
])

export const REVIEW_LIMITED_STATUSES = new Set([
  'PENDING_MATERIALS',
  'RETURNED_FOR_REVISION',
  'SUPPLEMENT_REQUIRED',
])

export const REVIEW_COMPLETED_STATUSES = new Set([
  'APPROVED',
  'REVIEW_COMPLETED',
])

export const REVIEW_EXTERNAL_INPUT_MUTATION_STATUSES = new Set([
  'RECEIVED',
  'PREPROCESSING',
  'PENDING_MATERIALS',
  'READY_FOR_REVIEW',
  'RETURNED_FOR_REVISION',
  'SUPPLEMENT_REQUIRED',
])

export type ReviewInteractionMode = 'EDITABLE' | 'LIMITED' | 'READ_ONLY'

export function reviewInteractionMode(status: string): ReviewInteractionMode {
  if (REVIEW_PENDING_STATUSES.has(status) || REVIEW_IN_PROGRESS_STATUSES.has(status)) return 'EDITABLE'
  if (REVIEW_LIMITED_STATUSES.has(status)) return 'LIMITED'
  return 'READ_ONLY'
}

export function canMutateExternalReviewInput(status: string): boolean {
  return REVIEW_EXTERNAL_INPUT_MUTATION_STATUSES.has(status)
}

export function reviewInteractionCopy(status: string): { title: string; description: string } {
  if (reviewInteractionMode(status) === 'LIMITED') {
    if (status === 'RETURNED_FOR_REVISION') {
      return {
        title: '待補正｜審查內容唯讀',
        description: '目前等待修正版回件；既有審查判定不可再修改。收到新版後仍可執行登記回件與新版重檢。',
      }
    }
    return {
      title: '待補件｜審查內容唯讀',
      description: '目前等待必要資料補齊；既有審查內容不可修改，只保留補件與重新檢核所需操作。',
    }
  }
  if (REVIEW_COMPLETED_STATUSES.has(status)) {
    return {
      title: '案件已完成｜唯讀模式',
      description: '審查結果已定案，僅能查閱證據、歷程與產出報告，不可再變更審查內容。',
    }
  }
  if (reviewInteractionMode(status) === 'READ_ONLY') {
    return {
      title: '唯讀模式',
      description: `案件狀態 ${status || 'UNKNOWN'} 不屬於目前可操作的正式審查流程，系統已採安全鎖定。`,
    }
  }
  return {
    title: '可進行審查',
    description: '案件目前位於待審或審查中階段，可依權限執行相應審查操作。',
  }
}