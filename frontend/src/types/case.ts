export interface CaseIdentity {
  caseId: string
  caseNo: string
  reviewId?: string
}

export interface CaseSummary extends CaseIdentity {
  name: string
  district?: string
  status: string
  updatedAt: string
}
