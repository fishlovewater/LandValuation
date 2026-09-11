import { defineConfig } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const base = new URL(baseURL)
const devPort = base.port || (base.protocol === 'https:' ? '443' : '80')

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  timeout: 300_000,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL,
    // Login credentials are entered in the real browser; never retain a trace.
    trace: 'off',
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${devPort}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
})
