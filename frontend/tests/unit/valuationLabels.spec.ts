import { describe, expect, it } from 'vitest'
import {
  valuationCaseTypeLabel,
  valuationLandUseLabel,
} from '../../src/modules/valuation/valuation.labels'

describe('valuation labels', () => {
  it('translates stored case type codes without altering readable values', () => {
    expect(valuationCaseTypeLabel('LAND')).toBe('土地徵收補償市價查估')
    expect(valuationCaseTypeLabel('LAND_ACQUISITION')).toBe('土地徵收補償市價查估')
    expect(valuationCaseTypeLabel('土地徵收補償市價查估')).toBe('土地徵收補償市價查估')
    expect(valuationCaseTypeLabel('UNKNOWN_CASE')).toBe('其他估價案件')
  })

  it('translates stored land-use codes for user-facing case metadata', () => {
    expect(valuationLandUseLabel('COMMERCIAL')).toBe('商業用地')
    expect(valuationLandUseLabel('RESIDENTIAL')).toBe('住宅用地')
    expect(valuationLandUseLabel('自訂用途')).toBe('自訂用途')
    expect(valuationLandUseLabel('UNKNOWN_USE')).toBe('其他用途')
  })
})