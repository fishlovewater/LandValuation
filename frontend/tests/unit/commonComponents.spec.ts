import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import CaseTable from '../../src/components/common/CaseTable.vue'
import ConfirmDialog from '../../src/components/common/ConfirmDialog.vue'
import EmptyState from '../../src/components/common/EmptyState.vue'
import ErrorState from '../../src/components/common/ErrorState.vue'
import LoadingSkeleton from '../../src/components/common/LoadingSkeleton.vue'
import RiskBadge from '../../src/components/common/RiskBadge.vue'
import StatusBadge from '../../src/components/common/StatusBadge.vue'
import type { CaseSummary } from '../../src/types/case'
import { riskLabel, statusLabel } from '../../src/utils/enumLabels'
import { formatDateZhTw } from '../../src/utils/formatters'

const cases: CaseSummary[] = [
  {
    caseId: 'case-001',
    caseNo: 'NTPC-001',
    name: '板橋區文化路一段',
    district: '板橋區',
    status: 'READY_FOR_REVIEW',
    updatedAt: '2026-09-07T08:30:00+08:00',
  },
]

describe('shared enum and display helpers', () => {
  it('uses a safe label for unknown status values while preserving diagnostics', () => {
    expect(statusLabel('UNRECOGNIZED')).toBe('未知狀態')

    const wrapper = mount(StatusBadge, { props: { status: 'UNRECOGNIZED' } })
    const badge = wrapper.get('[data-status]')
    expect(badge.text()).toContain('未知狀態')
    expect(badge.attributes('data-status-value')).toBe('UNRECOGNIZED')
    expect(badge.attributes('title')).toContain('UNRECOGNIZED')
  })

  it('renders risk meaning as both icon and text instead of color alone', () => {
    expect(riskLabel('HIGH')).toBe('高風險')

    const wrapper = mount(RiskBadge, { props: { risk: 'HIGH' } })
    const badge = wrapper.get('[data-risk="high"]')
    expect(badge.text()).toContain('高風險')
    expect(badge.get('svg').attributes('aria-hidden')).toBe('true')
    expect(badge.attributes('aria-label')).toContain('高風險')
  })

  it('formats ISO dates for zh-TW without changing the source value', () => {
    const iso = '2026-09-07T08:30:00+08:00'
    expect(formatDateZhTw(iso)).toContain('2026')
    expect(formatDateZhTw(iso)).not.toBe(iso)
    expect(formatDateZhTw('not-a-date')).toBe('—')
  })
})

describe('page-state components', () => {
  it('exposes an accessible loading region without a glass data surface', () => {
    const wrapper = mount(LoadingSkeleton, { props: { rows: 2 } })
    const region = wrapper.get('[role="status"]')
    expect(region.attributes('aria-busy')).toBe('true')
    expect(wrapper.findAll('.loading-skeleton__row')).toHaveLength(2)
    expect(wrapper.find('[data-lg]').exists()).toBe(false)
  })

  it('offers an empty-state action and a retry event for errors', async () => {
    const empty = mount(EmptyState, {
      props: { title: '沒有案件', actionLabel: '建立案件' },
    })
    await empty.get('button').trigger('click')
    expect(empty.emitted('action')).toHaveLength(1)

    const error = mount(ErrorState, {
      props: { message: '暫時無法載入案件', retryLabel: '重新載入' },
    })
    expect(error.text()).toContain('暫時無法載入案件')
    await error.get('button').trigger('click')
    expect(error.emitted('retry')).toHaveLength(1)
  })
})

describe('CaseTable', () => {
  it('renders server-provided rows and emits URL-compatible sort and page requests', async () => {
    const wrapper = mount(CaseTable, {
      props: {
        cases,
        total: 21,
        page: 1,
        pageSize: 10,
        sortBy: 'updatedAt',
        sortDirection: 'desc',
      },
    })

    expect(wrapper.get('table').attributes('aria-label')).toBe('案件列表')
    expect(wrapper.get('tbody tr').text()).toContain('NTPC-001')
    expect(wrapper.find('[data-lg]').exists()).toBe(false)

    await wrapper.get('[data-sort="updatedAt"]').trigger('click')
    expect(wrapper.emitted('sort-change')?.[0]?.[0]).toEqual({
      sortBy: 'updatedAt',
      sortDirection: 'asc',
    })
    expect(wrapper.emitted('query-change')?.[0]?.[0]).toMatchObject({
      sortBy: 'updatedAt',
      sortDirection: 'asc',
    })

    await wrapper.get('[data-page="2"]').trigger('click')
    expect(wrapper.emitted('page-change')?.[0]?.[0]).toEqual({
      page: 2,
      pageSize: 10,
    })
  })

  it('emits filters without filtering the supplied server result in the browser', async () => {
    const wrapper = mount(CaseTable, {
      props: {
        cases,
        total: 1,
        filters: { status: 'READY_FOR_REVIEW' },
        filterOptions: {
          status: [
            { value: '', label: '全部狀態' },
            { value: 'READY_FOR_REVIEW', label: '待審查' },
          ],
        },
      },
    })

    const select = wrapper.get('select[name="status"]')
    await select.setValue('READY_FOR_REVIEW')
    expect(wrapper.emitted('filter-change')?.[0]?.[0]).toEqual({
      status: 'READY_FOR_REVIEW',
    })
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })

  it('uses ascending order for the first sort request and its URL query', async () => {
    const wrapper = mount(CaseTable, { props: { cases } })

    await wrapper.get('[data-sort="caseNo"]').trigger('click')

    expect(wrapper.emitted('sort-change')?.[0]?.[0]).toEqual({
      sortBy: 'caseNo',
      sortDirection: 'asc',
    })
    expect(wrapper.emitted('query-change')?.[0]?.[0]).toMatchObject({
      sortBy: 'caseNo',
      sortDirection: 'asc',
    })
  })
})

describe('ConfirmDialog', () => {
  it('traps focus through GlassModal, closes on Escape, and restores the trigger', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()

    const wrapper = mount(ConfirmDialog, {
      attachTo: document.body,
      props: { open: false, title: '送出案件', message: '確定要送出嗎？' },
    })
    await wrapper.setProps({ open: true })
    await nextTick()

    expect(wrapper.get('[role="alertdialog"]').attributes('aria-modal')).toBe('true')
    const close = wrapper.get('.lg-modal__close').element
    const confirm = wrapper.get('button[data-confirm]').element
    confirm.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(close)
    close.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }))
    expect(document.activeElement).toBe(confirm)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)

    await wrapper.setProps({ open: false })
    await nextTick()
    expect(document.activeElement).toBe(trigger)
    wrapper.unmount()
    trigger.remove()
  })

  it('gives each instance a unique message id linked by aria-describedby', async () => {
    const host = mount({
      components: { ConfirmDialog },
      template: `
        <div>
          <ConfirmDialog :open="true" title="第一個確認" message="第一個訊息" />
          <ConfirmDialog :open="true" title="第二個確認" message="第二個訊息" />
        </div>
      `,
    })
    await nextTick()

    const dialogs = host.findAll('[role="alertdialog"]')
    const describedBy = dialogs.map((dialog) => dialog.attributes('aria-describedby'))
    expect(new Set(describedBy).size).toBe(2)
    for (const id of describedBy) {
      expect(id).toBeTruthy()
      expect(host.find(`#${id}`).exists()).toBe(true)
    }

    host.unmount()
  })
})
