export interface ApiCapabilities {
  auth: boolean
  valuation: boolean
  review: boolean
  history: boolean
  assistant: boolean
}

export const DEMO_REQUIRED_CAPABILITIES: Readonly<ApiCapabilities> = {
  auth: true,
  valuation: true,
  review: true,
  history: true,
  assistant: true,
}
