import { afterEach, describe, expect, it, vi } from 'vitest'
import { http } from '../../src/api/http'
import { valuationApi } from '../../src/modules/valuation/valuation.api'

function response<T>(data: T, config: Parameters<NonNullable<typeof http.defaults.adapter>>[0], status = 200) {
  return { data, status, statusText: 'OK', headers: {}, config }
}

describe('valuation API transport', () => {
  const originalAdapter = http.defaults.adapter

  afterEach(() => {
    http.defaults.adapter = originalAdapter
    vi.restoreAllMocks()
  })

  it('creates a case with only the backend CaseCreate contract fields', async () => {
    const payload = {
      case_no: 'NB-2026-0099',
      case_title: '契約測試案件',
      case_type: 'LAND_VALUATION',
      requesting_agency: '新北市政府',
      valuation_base_date: '2026-09-10',
      city_code: '65000',
      district_code: '65000030',
      land_use_type: '住宅區',
    }
    let captured: Record<string, unknown> | null = null

    http.defaults.adapter = vi.fn(async (config) => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/valuation/cases')
      captured = JSON.parse(String(config.data)) as Record<string, unknown>
      return response({ case_id: '11111111-1111-4111-8111-111111111111', ...payload } as never, config, 201)
    }) as unknown as typeof originalAdapter

    await valuationApi.createCase(payload)

    expect(captured).toEqual(payload)
    expect(captured).not.toHaveProperty('case_id')
    expect(captured).not.toHaveProperty('case_status')
  })

  it('creates a blank form by enforcing an empty form_content object', async () => {
    const caseId = '11111111-1111-4111-8111-111111111111'
    let captured: Record<string, unknown> | null = null

    http.defaults.adapter = vi.fn(async (config) => {
      expect(config.method).toBe('post')
      expect(config.url).toBe(`/valuation/cases/${caseId}/forms`)
      captured = JSON.parse(String(config.data)) as Record<string, unknown>
      return response({} as never, config, 201)
    }) as unknown as typeof originalAdapter

    await valuationApi.createForm(caseId, {
      form_code: 'F03',
      prepared_date: '2026-09-10',
    })

    expect(captured).toEqual({
      form_code: 'F03',
      prepared_date: '2026-09-10',
      form_content: {},
    })
  })

  it('uploads a source document as multipart form data with category and file', async () => {
    const caseId = '11111111-1111-4111-8111-111111111111'
    const file = new File(['pdf-body'], 'source.pdf', { type: 'application/pdf' })
    let capturedBody: FormData | null = null
    let capturedContentType: unknown

    http.defaults.adapter = vi.fn(async (config) => {
      expect(config.method).toBe('post')
      expect(config.url).toBe(`/valuation/cases/${caseId}/documents`)
      capturedBody = config.data as FormData
      capturedContentType = config.headers?.get?.('Content-Type') ?? config.headers?.['Content-Type']
      return response({ original_filename: file.name } as never, config, 201)
    }) as unknown as typeof originalAdapter

    await valuationApi.uploadDocument(caseId, 'original', file)

    expect(capturedBody).toBeInstanceOf(FormData)
    expect(capturedBody?.get('category')).toBe('original')
    const uploadedFile = capturedBody?.get('file')
    expect(uploadedFile).toBeInstanceOf(File)
    expect((uploadedFile as File).name).toBe('source.pdf')
    expect(String(capturedContentType ?? '')).not.toContain('application/json')
  })
})
