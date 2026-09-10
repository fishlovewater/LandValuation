import { riskLabel, severityLabel, statusLabel } from '../../utils/enumLabels'
import type * as T from './review.types'

export function normalizeScalar(value: unknown): string | undefined {
  if (value == null) return undefined
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (typeof value === 'object' && 'toString' in value) return String(value)
  return undefined
}

export function mapReviewCase(dto: T.WorkbenchCaseDto): T.ReviewCaseSummary {
  return {
    reviewId:dto.review_id, caseId:dto.case_id, caseNo:dto.case_no, title:dto.title,
    district:dto.district ?? undefined, status:dto.status, statusLabel:statusLabel(dto.status),
    riskLevel:dto.overall_risk_level ?? undefined, riskLabel:riskLabel(dto.overall_risk_level),
    missingItemCount:dto.missing_item_count, receivedAt:dto.received_at ?? undefined, updatedAt:dto.updated_at,
    raw:{ status:dto.status, riskLevel:dto.overall_risk_level ?? undefined },
  }
}

export function mapWorkbenchDetail(dto: T.WorkbenchDetailDto): T.ReviewCaseDetail {
  const base = mapReviewCase(dto.case)
  return {
    ...base,
    documents:dto.documents.map((d) => ({ documentId:d.document_id, documentGroupId:d.document_group_id, versionNo:d.version_no, documentType:d.document_type, filename:d.original_filename, mimeType:d.mime_type, fileSizeBytes:d.file_size_bytes, uploadedAt:d.uploaded_at, contentAvailable:d.content_available })),
    runs:dto.runs.map((r) => ({ runId:r.validation_run_id, caseId:r.case_id, triggerType:r.trigger_type, status:r.status, ruleVersionId:r.rule_version_id ?? undefined, createdAt:r.created_at, completedAt:r.completed_at ?? undefined })),
    findings:dto.latest_findings.map((f) => ({ findingId:f.finding_id, ruleId:f.rule_id, fieldName:f.field_name ?? undefined, severity:f.severity, severityLabel:severityLabel(f.severity), findingType:f.finding_type, message:f.message, sourceValue:normalizeScalar(f.source_value), recalculatedValue:normalizeScalar(f.recalculated_value), differenceValue:normalizeScalar(f.difference_value), status:f.status, aiExplanation:f.ai_explanation ?? undefined })),
    riskSummary:dto.latest_risk_summary ? { riskSummaryId:dto.latest_risk_summary.risk_summary_id, runId:dto.latest_risk_summary.validation_run_id, riskLevel:dto.latest_risk_summary.overall_risk_level, riskLabel:riskLabel(dto.latest_risk_summary.overall_risk_level), totalFindings:dto.latest_risk_summary.total_findings, criticalCount:dto.latest_risk_summary.critical_count, warningCount:dto.latest_risk_summary.warning_count, infoCount:dto.latest_risk_summary.info_count, aiSummary:dto.latest_risk_summary.ai_summary ?? undefined } : undefined,
  }
}