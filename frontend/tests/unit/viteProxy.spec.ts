import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { loadConfigFromFile } from 'vite'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

describe('local API proxy', () => {
  it('proxies /api to the local FastAPI service without changing the path', async () => {
    const loaded = await loadConfigFromFile(
      { command: 'serve', mode: 'development' },
      resolve(frontendRoot, 'vite.config.ts'),
    )

    expect(loaded?.config.server?.proxy?.['/api']).toEqual({
      target: 'http://127.0.0.1:8000',
      changeOrigin: false,
    })
  })

  it('documents the same-origin local API base URL', () => {
    const envExample = readFileSync(resolve(frontendRoot, '.env.example'), 'utf8')
    expect(envExample).toMatch(/^VITE_API_BASE_URL=\/api\/v1$/m)
  })
})
