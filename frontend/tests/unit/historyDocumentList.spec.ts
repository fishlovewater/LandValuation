import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DocumentList from '../../src/modules/history/components/DocumentList.vue'
import type { HistoryDocumentModel } from '../../src/modules/history/history.types'

function document(overrides: Partial<HistoryDocumentModel>): HistoryDocumentModel {
  return {
    documentId: 'doc-default',
    caseId: 'case-1',
    documentGroupId: 'group-1',
    documentType: 'generated-report',
    documentTypeLabel: '正式報告',
    sourceModule: 'valuation',
    sourceModuleLabel: '估價作業',
    fileName: '估價報告.pdf',
    contentType: 'application/pdf',
    contentTypeLabel: 'PDF 文件',
    createdAt: '2026-09-01T08:00:00+08:00',
    versionNo: 1,
    isActive: true,
    fileSizeBytes: 1024,
    checksumSha256: 'checksum',
    downloadAvailable: true,
    ...overrides,
  }
}

describe('History DocumentList', () => {
  it('groups document versions and distinguishes the current file from historical versions', () => {
    const wrapper = mount(DocumentList, {
      props: {
        documents: [
          document({ documentId: 'doc-v1', versionNo: 1, isActive: false }),
          document({ documentId: 'doc-v2', versionNo: 2, isActive: true, fileName: '估價報告-v2.pdf' }),
        ],
      },
    })

    expect(wrapper.text()).toContain('1 份目前文件 · 1 個歷史版本')
    expect(wrapper.text()).toContain('估價作業文件')
    expect(wrapper.text()).toContain('估價報告-v2.pdf')
    expect(wrapper.text()).toContain('第 2 版')
    expect(wrapper.text()).toContain('目前版本')
    expect(wrapper.text()).toContain('歷史版本 1 個')
    expect(wrapper.get('[data-testid="history-preview-doc-v2"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="history-preview-doc-v1"]').exists()).toBe(true)
  })

  it('emits the exact selected document version for preview and download', async () => {
    const current = document({ documentId: 'doc-v2', versionNo: 2, isActive: true })
    const old = document({ documentId: 'doc-v1', versionNo: 1, isActive: false })
    const wrapper = mount(DocumentList, { props: { documents: [old, current] } })

    await wrapper.get('[data-testid="history-preview-doc-v1"]').trigger('click')
    await wrapper.get('[data-testid="history-download-doc-v2"]').trigger('click')

    expect(wrapper.emitted('preview')?.[0]?.[0]).toEqual(old)
    expect(wrapper.emitted('download')?.[0]?.[0]).toEqual(current)
  })
})