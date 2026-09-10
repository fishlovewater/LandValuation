export interface WorkbenchCaseDto { review_id:string; case_id:string; case_no:string; title:string; district:string|null; status:string; overall_risk_level:string|null; missing_item_count:number; received_at:string|null; updated_at:string }
export interface WorkbenchDocumentDto { document_id:string; document_group_id:string; version_no:number; document_type:string; original_filename:string; mime_type:string; file_size_bytes:number; uploaded_at:string; content_available:boolean }
export interface WorkbenchRunDto { validation_run_id:string; case_id:string; trigger_type:string; status:string; rule_version_id:string|null; created_at:string; completed_at:string|null }
export interface WorkbenchFindingDto { finding_id:string; rule_id:string; field_name:string|null; severity:string; finding_type:string; message:string; source_value:unknown; recalculated_value:unknown; difference_value:unknown; status:string; ai_explanation:string|null }
export interface WorkbenchRiskSummaryDto { risk_summary_id:string; validation_run_id:string; overall_risk_level:string; total_findings:number; critical_count:number; warning_count:number; info_count:number; ai_summary:string|null }
export interface WorkbenchDetailDto { case:WorkbenchCaseDto; documents:WorkbenchDocumentDto[]; runs:WorkbenchRunDto[]; latest_findings:WorkbenchFindingDto[]; latest_risk_summary:WorkbenchRiskSummaryDto|null }

export interface ReviewCaseSummary { reviewId:string; caseId:string; caseNo:string; title:string; district?:string; status:string; statusLabel:string; riskLevel?:string; riskLabel:string; missingItemCount:number; receivedAt?:string; updatedAt:string; raw:{status:string;riskLevel?:string} }
export interface ReviewDocument { documentId:string; documentGroupId:string; versionNo:number; documentType:string; filename:string; mimeType:string; fileSizeBytes:number; uploadedAt:string; contentAvailable:boolean }
export interface ReviewRun { runId:string; caseId:string; triggerType:string; status:string; ruleVersionId?:string; createdAt:string; completedAt?:string }
export interface FindingViewModel { findingId:string; ruleId:string; fieldName?:string; severity:string; severityLabel:string; findingType:string; message:string; sourceValue?:string; recalculatedValue?:string; differenceValue?:string; status:string; aiExplanation?:string }
export interface ReviewRiskSummary { riskSummaryId:string; runId:string; riskLevel:string; riskLabel:string; totalFindings:number; criticalCount:number; warningCount:number; infoCount:number; aiSummary?:string }
export interface ReviewCaseDetail extends ReviewCaseSummary { documents:ReviewDocument[]; runs:ReviewRun[]; findings:FindingViewModel[]; riskSummary?:ReviewRiskSummary }

export interface ReviewSummary { totalCount:number; pendingCount:number; inReviewCount:number; actionRequiredCount:number; completedCount:number; urgentCount:number }
export interface ReviewCaseQuery { q?:string; status?:string; riskLevel?:string; statusGroup?:string; limit?:number; offset?:number }
export interface ReviewCasePage { items:ReviewCaseSummary[]; total:number; limit:number; offset:number }