import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DocumentTextPreview from '../../src/components/common/DocumentTextPreview.vue'
import SpreadsheetPreview from '../../src/components/common/SpreadsheetPreview.vue'
import ValuationFormalValidationPanel from '../../src/modules/valuation/components/ValuationFormalValidationPanel.vue'
import ValuationIssueDrawer from '../../src/modules/valuation/components/ValuationIssueDrawer.vue'
import ValuationReportArtifacts from '../../src/modules/valuation/components/ValuationReportArtifacts.vue'
import ValuationReportPackageWorkspace from '../../src/modules/valuation/components/ValuationReportPackageWorkspace.vue'
import ValuationStepNavigator from '../../src/modules/valuation/components/ValuationStepNavigator.vue'
import ValuationSubmitReadiness from '../../src/modules/valuation/components/ValuationSubmitReadiness.vue'
import ReviewActionBar from '../../src/modules/review/components/ReviewActionBar.vue'

describe('SpreadsheetPreview', () => {
  it('switches sheets and exposes truncated preview guidance', async () => {
    const wrapper = mount(SpreadsheetPreview, {
      props: {
        preview: {
          kind: 'spreadsheet',
          truncated: true,
          sheets: [
            {
              name: '基本資料',
              rows: [['欄位', '值'], ['估價基準日', '2026-09-11']],
              total_rows: 120,
              total_columns: 8,
              truncated: true,
            },
            {
              name: '附件',
              rows: [['名稱', '狀態'], ['地籍圖', true]],
              total_rows: 2,
              total_columns: 2,
              truncated: false,
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('120 列 × 8 欄')
    expect(wrapper.text()).toContain('僅顯示前段資料')
    expect(wrapper.text()).toContain('2026-09-11')

    await wrapper.findAll('[role="tab"]')[1].trigger('click')

    expect(wrapper.text()).toContain('附件')
    expect(wrapper.text()).toContain('地籍圖')
    expect(wrapper.text()).toContain('是')
    expect(wrapper.text()).not.toContain('僅顯示前段資料')
  })
})

describe('ValuationIssueDrawer', () => {
  it('renders the checklist inline and emits the selected workflow target', async () => {
    const wrapper = mount(ValuationIssueDrawer, {
      props: {
        items: [
          {
            id: 'formal-validation',
            title: '尚未完成正式檢核',
            detail: '完成查估書資料後執行正式檢核。',
            target: 'formal-validation',
            severity: 'pending',
          },
        ],
      },
    })

    expect(wrapper.get('[data-testid="valuation-issue-drawer"]').text()).toContain('待處理事項 1 項')
    expect(wrapper.get('[data-testid="valuation-issue-drawer"]').text()).toContain('尚未完成正式檢核')
    await wrapper.get('.issue-drawer__item > button').trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual(['formal-validation'])
  })
})

describe('ValuationSubmitReadiness', () => {
  it('keeps the current submit action explicit and emits the selected target', async () => {
    const steps = [
      { key: 'report-pages', title: '確認完整查估書', detail: '已完成', target: 'report-pages', state: 'done' as const },
      { key: 'formal-validation', title: '完成正式檢核', detail: '尚未執行', target: 'formal-validation', state: 'active' as const },
      { key: 'formal-pdf', title: '產生完整送審 PDF', detail: '待檢核', target: 'formal-pdf', state: 'pending' as const },
      { key: 'submission', title: '送出審查', detail: '待前置作業', target: 'submission', state: 'pending' as const },
    ]
    const wrapper = mount(ValuationSubmitReadiness, {
      props: {
        steps,
        currentStep: steps[1],
        completedStepCount: 1,
        submitted: false,
        readinessMessage: '請先執行正式檢核。',
      },
    })

    expect(wrapper.get('[data-testid="submit-next-action"]').text()).toContain('完成正式檢核')
    expect(wrapper.get('[data-testid="submit-readiness-steps"]').text()).toContain('完成 1 / 4')
    await wrapper.get('[data-testid="submit-next-action"] button').trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual(['formal-validation'])
  })
})

describe('ValuationReportPackageWorkspace', () => {
  it('keeps three-page confirmation, calculation, and validation as explicit gated actions', async () => {
    const wrapper = mount(ValuationReportPackageWorkspace, {
      props: {
        caseId: 'case-1',
        reportId: 'report-1',
        authoritativeF02: null,
        editors: {},
        activePageCode: 'S01',
        editorsLoading: false,
        editorSaving: null,
        editorNotice: '',
        confirmations: { s01: false, f02Rf: false, f02: false },
        pagesConfirmed: false,
        pageSaving: false,
        pageCalculating: false,
        pageValidating: false,
        pageSaved: false,
        pageCalculated: false,
      },
    })

    expect(wrapper.get('[data-testid="report-package-draft-flow"]').text()).toContain('完整查估書三頁確認')
    expect(wrapper.get('[data-testid="save-report-pages"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="run-formal-calculation"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="run-report-formal-validation"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="open-report-page-editors"]').trigger('click')
    expect(wrapper.emitted('loadEditors')).toHaveLength(1)

    await wrapper.get('[data-testid="report-page-s01-confirm"]').setValue(true)
    expect(wrapper.emitted('updateConfirmation')?.[0]).toEqual(['s01', true])
  })
})

describe('ValuationFormalValidationPanel', () => {
  it('requires explicit warning acknowledgement before formal PDF generation', async () => {
    const wrapper = mount(ValuationFormalValidationPanel, {
      props: {
        validation: {
          validationRunId: 'validation-1',
          caseId: 'case-1',
          reportId: 'report-1',
          runStatus: 'COMPLETED',
          passedCount: 8,
          warningCount: 1,
          failedCount: 0,
          canGenerateFormalReport: true,
          inputFingerprint: 'fingerprint-1',
          findings: [
            { code: 'F02_WARNING', severity: 'WARNING', message: '請確認比較資料。', fieldCode: 'comparison_targets' },
          ],
          completedAt: '2026-09-12T10:00:00+08:00',
        },
        formalWarningCodes: ['F02_WARNING'],
        acknowledgedWarningCodes: [],
        warningsAcknowledged: false,
        formalValidating: false,
        formalPdfGenerating: false,
        submitting: false,
        reportPackageReady: true,
        authoritativeF02Status: 'CHECKED',
      },
    })

    expect(wrapper.get('[data-testid="formal-validation-result"]').text()).toContain('警示 1')
    expect(wrapper.get('[data-testid="generate-formal-pdf"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="formal-warning-F02_WARNING"]').setValue(true)

    expect(wrapper.emitted('acknowledge')?.[0]).toEqual(['F02_WARNING', true])
  })
})

describe('ValuationReportArtifacts', () => {
  it('distinguishes the formal submission PDF from the traceability attachment', async () => {
    const wrapper = mount(ValuationReportArtifacts, {
      props: {
        formalReport: {
          documentId: 'formal-document',
          caseId: 'case-1',
          reportId: 'report-1',
          validationRunId: 'validation-1',
          filename: '完整送審.pdf',
          mimeType: 'application/pdf',
          versionNo: 2,
          fileSizeBytes: 2048,
          downloadPath: '/download/formal-document',
        },
        report: {
          documentId: 'f03-document',
          caseId: 'case-1',
          formInstanceId: 'form-1',
          validationRunId: 'validation-1',
          calculationId: 'calculation-1',
          filename: '比準地地價估計表.pdf',
          mimeType: 'application/pdf',
          versionNo: 1,
          fileSizeBytes: 1024,
        },
        downloadingDocumentId: null,
      },
    })

    expect(wrapper.text()).toContain('完整送審 PDF')
    expect(wrapper.text()).toContain('正式送審仍以完整送審 PDF 為主')
    await wrapper.get('[data-testid="download-formal-report"]').trigger('click')

    expect(wrapper.emitted('download')?.[0]).toEqual(['formal-document', '完整送審.pdf'])
  })
})

describe('ValuationStepNavigator', () => {
  it('shows the current workflow position and progress at a glance', () => {
    const wrapper = mount(ValuationStepNavigator, {
      props: { currentStep: 4 },
    })

    expect(wrapper.get('[data-testid="valuation-step-summary"]').text()).toContain('第 4 步 / 6')
    expect(wrapper.get('[data-testid="valuation-step-summary"]').text()).toContain('計算與檢核')
    expect(wrapper.get('[data-testid="valuation-step-summary"]').text()).toContain('67%')
  })
})

describe('DocumentTextPreview', () => {
  it('makes the DOCX preview boundary explicit and renders extracted text', () => {
    const wrapper = mount(DocumentTextPreview, {
      props: {
        preview: {
          kind: 'text',
          text: '土地估價報告\n\n[表格]\n欄位 | 值',
          truncated: true,
        },
      },
    })

    expect(wrapper.get('[data-testid="document-text-preview"]').text()).toContain('DOCX 文字預覽')
    expect(wrapper.text()).toContain('不還原 Word 原始版面')
    expect(wrapper.text()).toContain('完整內容請下載原始文件')
    expect(wrapper.get('pre').text()).toContain('土地估價報告')
    expect(wrapper.get('pre').text()).toContain('欄位 | 值')
  })
})

describe('ReviewActionBar', () => {
  it('highlights the current review action instead of keeping finalize primary during correction flow', () => {
    const draft = mount(ReviewActionBar, {
      props: {
        correctionStatus: 'DRAFT',
        canSendCorrection: true,
        canFinalize: true,
      },
    })

    expect(draft.get('[data-testid="send-correction"]').classes()).toContain('lg-btn--accent')
    expect(draft.get('[data-testid="finalize-review"]').classes()).not.toContain('lg-btn--accent')

    const regular = mount(ReviewActionBar, {
      props: {
        correctionStatus: null,
        canFinalize: true,
      },
    })
    expect(regular.get('[data-testid="finalize-review"]').classes()).toContain('lg-btn--accent')
  })
})
