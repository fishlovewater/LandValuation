import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import GlassButton from '../../src/components/glass/GlassButton.vue'
import GlassCard from '../../src/components/glass/GlassCard.vue'
import GlassField from '../../src/components/glass/GlassField.vue'
import GlassModal from '../../src/components/glass/GlassModal.vue'

afterEach(() => {
  document.body.innerHTML = ''
  window.LiquidGlass = undefined
})

describe('GlassCard', () => {
  it('attaches a dynamic glass node once', () => {
    const attach = vi.fn()
    window.LiquidGlass = { init: vi.fn(), attach }
    mount(GlassCard, { slots: { default: '內容' } })
    expect(attach).toHaveBeenCalledTimes(1)
  })

  it('destroys the attached instance once when unmounted', () => {
    const destroy = vi.fn()
    const attach = vi.fn(() => ({ destroy }))
    window.LiquidGlass = { init: vi.fn(), attach }
    const wrapper = mount(GlassCard, { slots: { default: '內容' } })

    wrapper.unmount()
    wrapper.unmount()

    expect(attach).toHaveBeenCalledTimes(1)
    expect(destroy).toHaveBeenCalledTimes(1)
  })
})

describe('GlassButton', () => {
  it('keeps button semantics, disabled state, and UI-ToolBox classes', () => {
    window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
    const wrapper = mount(GlassButton, {
      attrs: { 'aria-label': '送出' },
      props: { disabled: true, variant: 'accent', pill: true },
      slots: { default: '送出' },
    })

    const button = wrapper.get('button')
    expect(button.attributes('type')).toBe('button')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-label')).toBe('送出')
    expect(button.classes()).toEqual(expect.arrayContaining(['lg', 'lg-btn', 'lg-btn--accent', 'lg-btn--pill']))
    expect(button.text()).toBe('送出')
  })

  it('preserves caller aria-disabled when enabled but overrides it when natively disabled', () => {
    window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
    const enabled = mount(GlassButton, { attrs: { 'aria-disabled': 'false' } })
    const disabled = mount(GlassButton, {
      attrs: { 'aria-disabled': 'false' },
      props: { disabled: true },
    })

    expect(enabled.get('button').attributes('aria-disabled')).toBe('false')
    expect(disabled.get('button').attributes('aria-disabled')).toBe('true')
  })
})

describe('GlassField', () => {
  it('connects its visible label and hint to the native input', () => {
    window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
    const wrapper = mount(GlassField, {
      props: { id: 'parcel-id', label: '地號', hint: '請輸入地號', invalid: true },
    })

    const input = wrapper.get('input')
    expect(wrapper.get('label').text()).toBe('地號')
    expect(wrapper.get('.lg-field__hint').attributes('id')).toBe('parcel-id-hint')
    expect(input.attributes('placeholder')).toBe(' ')
    expect(input.attributes('aria-describedby')).toBe('parcel-id-hint')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(wrapper.classes()).toEqual(expect.arrayContaining(['lg-field', 'lg-field--error']))
  })

  it('keeps solid fields readable without attaching Liquid Glass', () => {
    const attach = vi.fn()
    window.LiquidGlass = { init: vi.fn(), attach }
    const wrapper = mount(GlassField, {
      props: { id: 'solid-field', label: '帳號', surface: 'solid' },
    })

    const box = wrapper.get('.lg-field__box')
    expect(attach).not.toHaveBeenCalled()
    expect(box.classes()).toContain('lg-field__box--solid')
    expect(box.classes()).not.toContain('lg')
    expect(box.attributes('data-lg')).toBeUndefined()
    expect(wrapper.get('label[for="solid-field"]').text()).toBe('帳號')
  })
})

describe('GlassModal', () => {
  it('blocks the upstream Escape listener when closeOnEscape is disabled', async () => {
    const vendorEscape = vi.fn(() => {
      document.querySelector('.lg-modal')?.classList.remove('is-open')
    })
    document.addEventListener('keydown', vendorEscape)
    window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
    let wrapper: ReturnType<typeof mount> | undefined

    try {
      wrapper = mount(GlassModal, {
        attachTo: document.body,
        props: { open: false, closeOnEscape: false, title: '確認' },
      })
      await wrapper.setProps({ open: true })
      await nextTick()

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))

      expect(vendorEscape).not.toHaveBeenCalled()
      expect(wrapper.get('.lg-modal').classes()).toContain('is-open')
      expect(wrapper.emitted('close')).toBeUndefined()
    } finally {
      document.removeEventListener('keydown', vendorEscape)
      wrapper?.unmount()
    }
  })

  it('traps focus, emits close on Escape, and restores the trigger focus', async () => {
    window.LiquidGlass = { init: vi.fn(), attach: vi.fn() }
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    const wrapper = mount(GlassModal, {
      attachTo: document.body,
      props: { open: false, title: '確認' },
      slots: {
        default: '<button type="button">確定</button>',
      },
    })

    await wrapper.setProps({ open: true })
    await nextTick()
    const close = wrapper.get('.lg-modal__close').element
    const confirm = wrapper.get('.lg-modal__body button').element
    expect(document.activeElement).toBe(close)

    confirm.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(close)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)

    await wrapper.setProps({ open: false })
    await nextTick()
    expect(document.activeElement).toBe(trigger)
  })
})
