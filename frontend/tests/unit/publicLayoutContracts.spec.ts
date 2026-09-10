import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const fixturePath = resolve(import.meta.dirname, '../e2e/public-layout.spec.ts')

describe('authenticated mobile shell fixture contract', () => {
  it('mocks the empty History cases page with the composed API path and query', () => {
    const source = readFileSync(fixturePath, 'utf8')

    expect(source).toContain("await page.route('**/api/v1/history/cases?offset=0&limit=20',")
    expect(source).toContain("status: 200")
    expect(source).toContain("contentType: 'application/json'")
    expect(source).toContain('items: [],')
    expect(source).toContain('total: 0,')
    expect(source).toContain('offset: 0,')
    expect(source).toContain('limit: 20,')
    expect(source).toContain('can_view_valuation: true,')
    expect(source).toContain('can_view_review: false,')
  })
})
