import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ErrorState from '../../src/components/common/ErrorState.vue'
import RiskBadge from '../../src/components/common/RiskBadge.vue'

describe('common page states', () => {
  it('emits retry without rendering technical detail', async () => {
    const wrapper = mount(ErrorState, { props: { message: '暫時無法載入案件。' } })
    expect(wrapper.text()).toContain('暫時無法載入案件。')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('communicates risk with text and an aria label rather than color alone', () => {
    const wrapper = mount(RiskBadge, { props: { level: 'HIGH' } })
    expect(wrapper.text()).toContain('高風險')
    expect(wrapper.attributes('aria-label')).toContain('高風險')
  })
})