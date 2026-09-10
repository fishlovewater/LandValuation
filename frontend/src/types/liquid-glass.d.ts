export interface LiquidGlassHandle {
  destroy(): void
}

export interface LiquidGlassApi {
  init(config?: Record<string, unknown>): void
  attach(element: HTMLElement, options?: Record<string, unknown>): LiquidGlassHandle | void
  refresh?(): void
  reducedMotion?: boolean
  supported?: boolean
}

declare global {
  interface Window {
    LiquidGlass?: LiquidGlassApi
  }
}
