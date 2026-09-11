import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DocumentTextPreview from '../../src/components/common/DocumentTextPreview.vue'
import SpreadsheetPreview from '../../src/components/common/SpreadsheetPreview.vue'
import ValuationIssueDrawer from '../../src/modules/valuation/components/ValuationIssueDrawer.vue'
import ValuationStepNavigator from '../../src/modules/valuation/components/ValuationStepNavigator.vue'

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
