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

  it('submits explicit extraction candidate decisions through the automated confirmation contract', async () => {
    const caseId = '11111111-1111-4111-8111-111111111111'
    const payload = {
      confirmations: [
        {
          document_id: '22222222-2222-4222-8222-222222222222',
          extracted_field_id: '33333333-3333-4333-8333-333333333333',
          decision: 'CONFIRM' as const,
          corrected_value: '125000',
        },
        {
          document_id: '22222222-2222-4222-8222-222222222222',
          extracted_field_id: '44444444-4444-4444-8444-444444444444',
          decision: 'REJECT' as const,
        },
      ],
      confirm_apply: true as const,
    }
    let captured: Record<string, unknown> | null = null

    http.defaults.adapter = vi.fn(async (config) => {
      expect(config.method).toBe('post')
      expect(config.url).toBe(`/valuation/cases/${caseId}/auto-workflow/confirm`)
      captured = JSON.parse(String(config.data)) as Record<string, unknown>
      return response({ candidates: [], pending_candidate_count: 0 } as never, config)
    }) as unknown as typeof originalAdapter

    await valuationApi.confirmWorkflowCandidates(caseId, payload)
    expect(captured).toEqual(payload)
  })

  it('uses the existing parcel and benchmark-land backend contracts without inventing client-only fields', async () => {
    const caseId = '11111111-1111-4111-8111-111111111111'
    const parcelId = '22222222-2222-4222-8222-222222222222'
    const requests: Array<{ method?: string; url?: string; body?: unknown }> = []
    http.defaults.adapter = vi.fn(async (config) => {
      requests.push({
        method: config.method,
        url: config.url,
        body: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
      })
      return response([] as never, config)
    }) as unknown as typeof originalAdapter

    await valuationApi.listParcels(caseId)
    await valuationApi.createParcel(caseId, {
      district_code: '65000030',
      section_name: '安康段',
      land_no: '123-4',
      area_sqm: '100.5',
    })
    await valuationApi.updateParcel(caseId, parcelId, { area_sqm: '101.0' })
    await valuationApi.createBenchmarkLand(caseId, {
      parcel_id: parcelId,
      benchmark_land_no: 'B-001',
      price_zone_no: 'Z-01',
    })

    expect(requests).toEqual([
      { method: 'get', url: `/valuation/cases/${caseId}/parcels`, body: undefined },
      {
        method: 'post',
        url: `/valuation/cases/${caseId}/parcels`,
        body: {
          district_code: '65000030',
          section_name: '安康段',
          land_no: '123-4',
          area_sqm: '100.5',
        },
      },
      { method: 'patch', url: `/valuation/cases/${caseId}/parcels/${parcelId}`, body: { area_sqm: '101.0' } },
      {
        method: 'post',
        url: `/valuation/cases/${caseId}/benchmark-lands`,
        body: { parcel_id: parcelId, benchmark_land_no: 'B-001', price_zone_no: 'Z-01' },
      },
    ])
  })

  it('starts document extraction on the selected server document', async () => {
    const caseId = '11111111-1111-4111-8111-111111111111'
    const documentId = '22222222-2222-4222-8222-222222222222'
    http.defaults.adapter = vi.fn(async (config) => {
      expect(config.method).toBe('post')
      expect(config.url).toBe(`/valuation/cases/${caseId}/documents/${documentId}/extract`)
      expect(config.data).toBeUndefined()
      return response({ candidates: [] } as never, config)
    }) as unknown as typeof originalAdapter

    await valuationApi.startDocumentExtraction(caseId, documentId)
  })
})
