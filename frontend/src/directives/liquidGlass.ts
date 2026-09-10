import type { Directive } from 'vue'
import type { LiquidGlassHandle } from '../types/liquid-glass'

const mountedHandles = new WeakMap<HTMLElement, LiquidGlassHandle>()

export const liquidGlass: Directive<HTMLElement> = {
  mounted(element, binding) {
    if (binding.value === false) return
    const handle = window.LiquidGlass?.attach(element)
    if (handle && typeof handle.destroy === 'function') mountedHandles.set(element, handle)
  },
  unmounted(element) {
    const handle = mountedHandles.get(element)
    if (!handle) return
    mountedHandles.delete(element)
    handle.destroy()
  },
}

export default liquidGlass
