import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EvidenceViewer from '../../src/modules/review/components/EvidenceViewer.vue'
import { reviewApi } from '../../src/modules/review/review.api'

vi.mock('../../src/modules/review/review.api', () => ({
  reviewApi: { getDocumentContent: vi.fn() },
  safeReviewErrorMessage: () => '無法載入證據',
}))

describe('EvidenceViewer', () => {
  beforeEach(() => {
    vi.mocked(reviewApi.getDocumentContent).mockResolvedValue(new Blob(['%PDF-1.7']))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:evidence')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  })

  it('updates the actual PDF page when the selected finding changes page in the same document', async () => {
    const wrapper = mount(EvidenceViewer, {
      props: {
        reviewId: 'review-1',
        pageNumber: 3,
        document: {
          documentId: 'document-1',
          documentType: 'original',
          documentTypeLabel: '原始查估文件',
          filename: 'report.pdf',
          mimeType: 'application/pdf',
          mimeTypeLabel: 'PDF 文件',
          versionNo: 1,
          isActive: true,
          uploadedAt: '2026-09-07T01:00:00Z',
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="evidence-pdf"]').attributes('src')).toBe('blob:evidence#page=3')
    expect(vi.mocked(reviewApi.getDocumentContent)).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ pageNumber: 7 })
    await flushPromises()
    expect(wrapper.get('[data-testid="evidence-pdf"]').attributes('src')).toBe('blob:evidence#page=7')
    expect(vi.mocked(reviewApi.getDocumentContent)).toHaveBeenCalledTimes(1)
  })
})
