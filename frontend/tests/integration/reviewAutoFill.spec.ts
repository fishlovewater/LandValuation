import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExternalReviewIntake from '../../src/modules/review/components/ExternalReviewIntake.vue'
import { reviewApi } from '../../src/modules/review/review.api'

const document = { documentId: 'doc', documentType: 'original', versionNo: 1,
  mimeType: 'application/pdf', filename: 'report.pdf', isActive: true } as any
function extraction(status = 'NEEDS_CONFIRMATION', doc = 'doc'): any {
  return { extraction_id: 'extract', document_id: doc, extraction_status: 'COMPLETED',
    provider: 'LOCAL_PDF', page_count: 1,
    extraction_metadata: { review_intake: { uncertainties: { field: ['辨識信心不足'] } } },
    candidates: [{ extracted_field_id: 'field', form_code: 'F01', field_name: 'land_area',
      field_label: '土地面積', field_status: status, extracted_value: '123', confidence: '0.9',
      source_page: 1, source_text: '土地面積123' }] }
}
afterEach(() => vi.restoreAllMocks())

describe('review OCR to form workflow', () => {
  it('shows automatic fill and its persisted form without manual confirmation', async () => {
    vi.spyOn(reviewApi, 'getExternalDocumentExtraction').mockResolvedValue(extraction())
    vi.spyOn(reviewApi, 'startExternalDocumentExtraction').mockResolvedValue(extraction('AUTO_APPLIED'))
    vi.spyOn(reviewApi, 'getExternalDocumentForms').mockResolvedValue([{ form_instance_id: 'form', form_code: 'F01',
      form_name: '買賣實例調查估價表', version_no: 1,
      fields: [{ field_name: 'land_area', label: '土地面積', value: '123', origin: 'AUTO', source_page: 1 }] }])
    const confirm = vi.spyOn(reviewApi, 'confirmExternalDocumentExtraction')
    const wrapper = mount(ExternalReviewIntake, { props: { reviewId: 'review', documents: [document] } })
    await flushPromises()
    await wrapper.get('[data-testid="start-external-extraction"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('自動已填表')
    expect(wrapper.get('[data-testid="filled-review-forms"]').text()).toContain('123')
    expect(confirm).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('submits edited doubtful values in a batch and refreshes forms', async () => {
    vi.spyOn(reviewApi, 'getExternalDocumentExtraction').mockResolvedValue(extraction())
    const forms = vi.spyOn(reviewApi, 'getExternalDocumentForms').mockResolvedValue([])
    const confirm = vi.spyOn(reviewApi, 'confirmExternalDocumentExtraction').mockResolvedValue(extraction('APPLIED'))
    const wrapper = mount(ExternalReviewIntake, { props: { reviewId: 'review', documents: [document] } })
    await flushPromises()
    expect(wrapper.text()).toContain('辨識信心不足')
    await wrapper.get('input[aria-label="土地面積確認值"]').setValue('124')
    await wrapper.get('[data-testid="confirm-pending-fields"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('review', 'doc', [{ extracted_field_id: 'field', decision: 'CONFIRM', corrected_value: '124' }])
    expect(wrapper.text()).toContain('人工確認已填表')
    expect(forms).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('does not let a slow previous-document request overwrite the selected document', async () => {
    let release!: (result: any) => void
    vi.spyOn(reviewApi, 'getExternalDocumentExtraction').mockImplementation(async (_review, doc) =>
      doc === 'doc' ? new Promise(resolve => { release = resolve }) : extraction('AUTO_APPLIED', 'second'))
    vi.spyOn(reviewApi, 'getExternalDocumentForms').mockResolvedValue([])
    const wrapper = mount(ExternalReviewIntake, { props: { reviewId: 'review', documents: [document,
      { ...document, documentId: 'second', documentType: 'attachments' }] } })
    await flushPromises()
    await wrapper.get('[data-testid="external-document-second"]').trigger('click')
    await flushPromises()
    release(extraction())
    await flushPromises()
    expect(wrapper.text()).toContain('自動已填表')
    expect(wrapper.text()).not.toContain('辨識信心不足')
    wrapper.unmount()
  })
})
