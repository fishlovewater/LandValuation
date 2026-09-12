import { isAxiosError } from 'axios'
import { ForbiddenError, http } from '../../api/http'
import type { DocumentTextPreviewDto } from '../../types/documentPreview'
import type { SpreadsheetPreviewDto } from '../../types/spreadsheet'
import type {
  AutomatedConfirmRequestDto,
  AutomatedWorkflowResponseDto,
  BenchmarkLandCreateDto,
  BenchmarkLandResponseDto,
  CalculationRequestDto,
  CalculationResponseDto,
  CaseBootstrapResponseDto,
  CaseCreateDto,
  CaseResponseDto,
  CaseWorkspaceUpdateDto,
  ComparisonSetupApplyDto,
  ComparisonSetupContextDto,
  ComparisonSetupCreateDto,
  ComparisonSetupResponseDto,
  DocumentCategory,
  DocumentResponseDto,
  F03DraftResponseDto,
  F03DraftUpdateDto,
  FormalReportRequestDto,
  FormalReportResponseDto,
  FormalCalculationRequestDto,
  FormalCalculationResponseDto,
  FormalWorkflowStatusResponseDto,
  FormalValidationResponseDto,
  TemplateExportResponseDto,
  FormRequirementResponseDto,
  FormCreateDto,
  FormResponseDto,
  ExtractionResponseDto,
  ManualFieldValuesRequestDto,
  ParcelBatchImportRequestDto,
  ParcelBatchImportResponseDto,
  ParcelCreateDto,
  ParcelImportPreviewDto,
  ParcelResponseDto,
  ParcelUpdateDto,
  ReportPageCode,
  ReportPageResponseDto,
  ReportPackageCreateDto,
  ReportPackageResponseDto,
  ReportProgressResponseDto,
  ReportRequestDto,
  ReportResponseDto,
  SubmitForReviewCommandDto,
  SubmitForReviewResultDto,
  ValuationReviewHandoffDto,
  ValidationRequestDto,
  ValidationResponseDto,
  ValuationLocationDto,
} from './valuation.types'

export interface ListCasesParams {
  caseStatus?: string
  offset?: number
  limit?: number
}

function requestIdFallback(): string {
  const segment = () => Math.floor(Math.random() * 0xffffffff).toString(16).padStart(8, '0')
  const random = `${segment()}${segment()}`
  return `${random.slice(0, 8)}-${random.slice(0, 4)}-4${random.slice(0, 3)}-8${random.slice(0, 3)}-${random.slice(0, 12)}`
}

export function createValuationRequestId(): string {
  const cryptoApi = globalThis.crypto
  return typeof cryptoApi?.randomUUID === 'function' ? cryptoApi.randomUUID() : requestIdFallback()
}

export function isDefinitiveValuationError(error: unknown): boolean {
  return error instanceof ForbiddenError || (isAxiosError(error) && Boolean(error.response))
}

export const valuationApi = {
  async getWorkflowReview(caseId: string): Promise<AutomatedWorkflowResponseDto> {
    const response = await http.get<AutomatedWorkflowResponseDto>(
      `/valuation/cases/${caseId}/auto-workflow/review`,
    )
    return response.data
  },

  async confirmWorkflowCandidates(
    caseId: string,
    payload: AutomatedConfirmRequestDto,
  ): Promise<AutomatedWorkflowResponseDto> {
    const response = await http.post<AutomatedWorkflowResponseDto>(
      `/valuation/cases/${caseId}/auto-workflow/confirm`,
      payload,
    )
    return response.data
  },

  async saveWorkflowManualFields(
    caseId: string,
    payload: ManualFieldValuesRequestDto,
  ): Promise<AutomatedWorkflowResponseDto> {
    const response = await http.post<AutomatedWorkflowResponseDto>(
      `/valuation/cases/${caseId}/auto-workflow/manual-fields`,
      payload,
    )
    return response.data
  },

  async getReviewHandoff(caseId: string): Promise<ValuationReviewHandoffDto> {
    const response = await http.get<ValuationReviewHandoffDto>(
      `/valuation/cases/${caseId}/review-handoff`,
    )
    return response.data
  },

  async getFormTypes(): Promise<FormRequirementResponseDto[]> {
    const response = await http.get<FormRequirementResponseDto[]>('/valuation/form-types')
    return response.data
  },

  async listCases(params: ListCasesParams = {}): Promise<CaseResponseDto[]> {
    const response = await http.get<CaseResponseDto[]>('/valuation/cases', {
      params: {
        case_status: params.caseStatus,
        offset: params.offset ?? 0,
        limit: params.limit ?? 50,
      },
    })
    return response.data
  },

  async createCase(payload: CaseCreateDto): Promise<CaseResponseDto> {
    const response = await http.post<CaseResponseDto>('/valuation/cases', payload)
    return response.data
  },

  async bootstrapCase(payload: CaseCreateDto): Promise<CaseBootstrapResponseDto> {
    const response = await http.post<CaseBootstrapResponseDto>('/valuation/cases/bootstrap', payload)
    return response.data
  },

  async getCase(caseId: string): Promise<CaseResponseDto> {
    const response = await http.get<CaseResponseDto>(`/valuation/cases/${caseId}`)
    return response.data
  },

  async updateCaseWorkspace(
    caseId: string,
    payload: CaseWorkspaceUpdateDto,
  ): Promise<CaseResponseDto> {
    const response = await http.patch<CaseResponseDto>(
      `/valuation/cases/${caseId}/workspace`,
      payload,
    )
    return response.data
  },

  async listParcels(caseId: string): Promise<ParcelResponseDto[]> {
    const response = await http.get<ParcelResponseDto[]>(`/valuation/cases/${caseId}/parcels`)
    return response.data
  },

  async createParcel(caseId: string, payload: ParcelCreateDto): Promise<ParcelResponseDto> {
    const response = await http.post<ParcelResponseDto>(`/valuation/cases/${caseId}/parcels`, payload)
    return response.data
  },

  async updateParcel(
    caseId: string,
    parcelId: string,
    payload: ParcelUpdateDto,
  ): Promise<ParcelResponseDto> {
    const response = await http.patch<ParcelResponseDto>(
      `/valuation/cases/${caseId}/parcels/${parcelId}`,
      payload,
    )
    return response.data
  },

  async listForms(caseId: string): Promise<FormResponseDto[]> {
    const response = await http.get<FormResponseDto[]>(`/valuation/cases/${caseId}/forms`)
    return response.data
  },

  async createForm(caseId: string, payload: FormCreateDto): Promise<FormResponseDto> {
    const response = await http.post<FormResponseDto>(`/valuation/cases/${caseId}/forms`, {
      ...payload,
      form_content: {},
    })
    return response.data
  },

  async getForm(caseId: string, formId: string): Promise<FormResponseDto> {
    const response = await http.get<FormResponseDto>(`/valuation/cases/${caseId}/forms/${formId}`)
    return response.data
  },

  async getF03(caseId: string, formId: string): Promise<F03DraftResponseDto> {
    const response = await http.get<F03DraftResponseDto>(
      `/valuation/cases/${caseId}/forms/${formId}/f03`,
    )
    return response.data
  },

  async updateF03(caseId: string, formId: string, payload: F03DraftUpdateDto): Promise<F03DraftResponseDto> {
    const response = await http.patch<F03DraftResponseDto>(
      `/valuation/cases/${caseId}/forms/${formId}/f03`,
      payload,
    )
    return response.data
  },

  async submitForm(caseId: string, formId: string): Promise<FormResponseDto> {
    const response = await http.post<FormResponseDto>(
      `/valuation/cases/${caseId}/forms/${formId}/submit`,
    )
    return response.data
  },

  async listBenchmarkLands(caseId: string): Promise<BenchmarkLandResponseDto[]> {
    const response = await http.get<BenchmarkLandResponseDto[]>(
      `/valuation/cases/${caseId}/benchmark-lands`,
    )
    return response.data
  },

  async createBenchmarkLand(
    caseId: string,
    payload: BenchmarkLandCreateDto,
  ): Promise<BenchmarkLandResponseDto> {
    const response = await http.post<BenchmarkLandResponseDto>(
      `/valuation/cases/${caseId}/benchmark-lands`,
      payload,
    )
    return response.data
  },

  async getComparisonSetup(caseId: string): Promise<ComparisonSetupContextDto> {
    const response = await http.get<ComparisonSetupContextDto>(
      `/valuation/cases/${caseId}/comparison-setup`,
    )
    return response.data
  },

  async createComparisonSetup(
    caseId: string,
    payload: ComparisonSetupCreateDto,
  ): Promise<ComparisonSetupResponseDto> {
    const response = await http.post<ComparisonSetupResponseDto>(
      `/valuation/cases/${caseId}/comparison-setup`,
      payload,
    )
    return response.data
  },

  async applyComparisonSetup(
    caseId: string,
    payload: ComparisonSetupApplyDto,
  ): Promise<ComparisonSetupResponseDto> {
    const response = await http.post<ComparisonSetupResponseDto>(
      `/valuation/cases/${caseId}/comparison-setup/apply`,
      payload,
    )
    return response.data
  },

  async listLocations(caseId: string): Promise<ValuationLocationDto[]> {
    const response = await http.get<ValuationLocationDto[]>(`/valuation/cases/${caseId}/locations`)
    return response.data
  },

  async createLocation(caseId: string, payload: { label: string; address?: string | null }): Promise<ValuationLocationDto> {
    const response = await http.post<ValuationLocationDto>(`/valuation/cases/${caseId}/locations`, payload)
    return response.data
  },

  async setBenchmarkLocation(caseId: string, locationId: string): Promise<ValuationLocationDto> {
    const response = await http.post<ValuationLocationDto>(`/valuation/cases/${caseId}/locations/${locationId}/set-benchmark`)
    return response.data
  },

  async archiveLocation(caseId: string, locationId: string): Promise<ValuationLocationDto> {
    const response = await http.post<ValuationLocationDto>(`/valuation/cases/${caseId}/locations/${locationId}/archive`)
    return response.data
  },

  async listDocuments(caseId: string): Promise<DocumentResponseDto[]> {
    const response = await http.get<DocumentResponseDto[]>(
      `/valuation/cases/${caseId}/documents`,
    )
    return response.data
  },

  async uploadDocument(
    caseId: string,
    category: DocumentCategory,
    file: File,
    locationId?: string | null,
  ): Promise<DocumentResponseDto> {
    const body = new FormData()
    body.append('category', category)
    body.append('file', file)
    if (locationId) body.append('location_id', locationId)
    const response = await http.post<DocumentResponseDto>(`/valuation/cases/${caseId}/documents`, body, {
      headers: { 'Content-Type': undefined },
    })
    return response.data
  },

  async deleteDocument(caseId: string, documentId: string): Promise<void> {
    await http.delete(`/valuation/cases/${caseId}/documents/${documentId}`)
  },

  async reclassifyDocument(
    caseId: string,
    documentId: string,
    category: DocumentCategory,
  ): Promise<DocumentResponseDto> {
    const response = await http.patch<DocumentResponseDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/category`,
      { category },
    )
    return response.data
  },

  async downloadDocument(caseId: string, documentId: string): Promise<Blob> {
    const response = await http.get<Blob>(
      `/valuation/cases/${caseId}/documents/${documentId}/download`,
      { responseType: 'blob' },
    )
    return response.data
  },

  async previewSpreadsheet(caseId: string, documentId: string): Promise<SpreadsheetPreviewDto> {
    const response = await http.get<SpreadsheetPreviewDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/spreadsheet-preview`,
    )
    return response.data
  },

  async previewParcelImport(caseId: string, documentId: string): Promise<ParcelImportPreviewDto> {
    const response = await http.get<ParcelImportPreviewDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/parcel-import-preview`,
    )
    return response.data
  },

  async importParcelsFromDocument(
    caseId: string,
    documentId: string,
    payload: ParcelBatchImportRequestDto,
  ): Promise<ParcelBatchImportResponseDto> {
    const response = await http.post<ParcelBatchImportResponseDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/parcel-import`,
      payload,
    )
    return response.data
  },

  async previewTextDocument(caseId: string, documentId: string): Promise<DocumentTextPreviewDto> {
    const response = await http.get<DocumentTextPreviewDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/text-preview`,
    )
    return response.data
  },

  async startDocumentExtraction(caseId: string, documentId: string): Promise<ExtractionResponseDto> {
    const response = await http.post<ExtractionResponseDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/extract`,
    )
    return response.data
  },

  async getDocumentExtraction(caseId: string, documentId: string): Promise<ExtractionResponseDto> {
    const response = await http.get<ExtractionResponseDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/extraction`,
    )
    return response.data
  },

  async analyzeDocumentFields(
    caseId: string,
    documentId: string,
    formCode: 'S01' | 'F01' | 'F02' | 'F02-RF' | 'F03' | 'F04',
  ): Promise<ExtractionResponseDto> {
    const response = await http.post<ExtractionResponseDto>(
      `/valuation/cases/${caseId}/documents/${documentId}/extraction/analyze-fields`,
      { form_code: formCode },
    )
    return response.data
  },

  async getReportProgress(caseId: string): Promise<ReportProgressResponseDto> {
    const response = await http.get<ReportProgressResponseDto>(
      `/valuation/cases/${caseId}/report-progress`,
    )
    return response.data
  },

  async createReportPackage(
    caseId: string,
    payload: ReportPackageCreateDto,
  ): Promise<ReportPackageResponseDto> {
    const response = await http.post<ReportPackageResponseDto>(
      `/valuation/cases/${caseId}/report-packages`,
      payload,
    )
    return response.data
  },

  async getReportPage(
    caseId: string,
    reportId: string,
    pageCode: ReportPageCode,
  ): Promise<ReportPageResponseDto> {
    const response = await http.get<ReportPageResponseDto>(
      `/valuation/cases/${caseId}/reports/${reportId}/pages/${pageCode}`,
    )
    return response.data
  },

  async updateReportPage(
    caseId: string,
    reportId: string,
    pageCode: ReportPageCode,
    payload: Record<string, unknown>,
  ): Promise<ReportPageResponseDto> {
    const response = await http.patch<ReportPageResponseDto>(
      `/valuation/cases/${caseId}/reports/${reportId}/pages/${pageCode}`,
      payload,
    )
    return response.data
  },

  async calculateFormalReport(
    caseId: string,
    reportId: string,
    payload: FormalCalculationRequestDto,
  ): Promise<FormalCalculationResponseDto> {
    const response = await http.post<FormalCalculationResponseDto>(
      `/valuation/cases/${caseId}/reports/${reportId}/formal-calculation`,
      payload,
    )
    return response.data
  },

  async getFormalStatus(caseId: string, reportId: string): Promise<FormalWorkflowStatusResponseDto> {
    const response = await http.get<FormalWorkflowStatusResponseDto>(
      `/valuation/cases/${caseId}/reports/${reportId}/formal-status`,
    )
    return response.data
  },

  async calculate(caseId: string, payload: CalculationRequestDto): Promise<CalculationResponseDto> {
    const response = await http.post<CalculationResponseDto>(
      `/valuation/cases/${caseId}/calculations`,
      payload,
    )
    return response.data
  },

  async validate(caseId: string, payload: ValidationRequestDto): Promise<ValidationResponseDto> {
    const response = await http.post<ValidationResponseDto>(
      `/valuation/cases/${caseId}/validations`,
      payload,
    )
    return response.data
  },

  async getValidation(caseId: string, validationRunId: string): Promise<ValidationResponseDto> {
    const response = await http.get<ValidationResponseDto>(
      `/valuation/cases/${caseId}/validations/${validationRunId}`,
    )
    return response.data
  },

  async generateReport(caseId: string, payload: ReportRequestDto): Promise<ReportResponseDto> {
    const response = await http.post<ReportResponseDto>(`/valuation/cases/${caseId}/reports`, payload)
    return response.data
  },

  async formalValidate(caseId: string, reportId: string): Promise<FormalValidationResponseDto> {
    const response = await http.post<FormalValidationResponseDto>(
      `/valuation/cases/${caseId}/reports/${reportId}/formal-validation`,
    )
    return response.data
  },

  async generateTemplateExports(caseId: string, reportId: string): Promise<TemplateExportResponseDto[]> {
    const response = await http.post<TemplateExportResponseDto[]>(
      `/valuation/cases/${caseId}/reports/${reportId}/template-exports`,
    )
    return response.data
  },

  async generateFormalPdf(
    caseId: string,
    reportId: string,
    payload: FormalReportRequestDto,
    requestId?: string,
  ): Promise<FormalReportResponseDto> {
    const response = await http.post<FormalReportResponseDto>(
      `/valuation/cases/${caseId}/reports/${reportId}/formal-pdf`,
      payload,
      requestId ? { headers: { 'X-Request-ID': requestId } } : undefined,
    )
    return response.data
  },

  async downloadFormalWorkbook(caseId: string, reportId: string): Promise<Blob> {
    const response = await http.get<Blob>(
      `/valuation/cases/${caseId}/reports/${reportId}/formal-xlsx/download`,
      { responseType: 'blob' },
    )
    return response.data
  },

  async submitForReview(
    caseId: string,
    payload: SubmitForReviewCommandDto,
  ): Promise<SubmitForReviewResultDto> {
    const response = await http.post<SubmitForReviewResultDto>(
      `/valuation/cases/${caseId}/submit-for-review`,
      payload,
    )
    return response.data
  },
}

export function safeValuationErrorMessage(error: unknown): string {
  if (error instanceof ForbiddenError) return error.message
  if (isAxiosError(error)) {
    const status = error.response?.status
    const body = error.response?.data as {
      error?: { code?: unknown; message?: unknown; details?: unknown }
      detail?: unknown
    } | undefined
    const code = typeof body?.error?.code === 'string' ? body.error.code : undefined
    const serverMessage = typeof body?.error?.message === 'string'
      ? body.error.message.trim()
      : typeof body?.detail === 'string'
        ? body.detail.trim()
        : ''
    if (status === 413 && code === 'PREVIEW_TOO_LARGE') {
      return '文件檔案過大，請下載原始文件查看完整內容。'
    }
    if (status === 415 && code === 'PREVIEW_NOT_SUPPORTED') {
      return '此文件格式目前不支援內嵌預覽，請下載原始文件查看。'
    }
    if (status === 404) return '找不到目前案件或估價資料，請重新整理後再試。'
    // API errors are business-rule feedback intended for the appraiser.  Do
    // not conceal a 4xx/5xx response behind a generic retry message: include
    // the stable code so the UI, support logs, and user can identify the exact
    // missing prerequisite or invalid value.
    if (serverMessage) return code ? `［${code}］${serverMessage}` : serverMessage
    if (code) return `［${code}］估價服務無法完成此操作。`
  }
  return '估價服務目前無法完成此操作，請稍後再試。'
}
