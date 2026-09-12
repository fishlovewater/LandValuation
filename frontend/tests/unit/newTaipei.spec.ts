import { describe, expect, it } from 'vitest'
import { NEW_TAIPEI_CITY_CODE, NEW_TAIPEI_DISTRICTS } from '../../src/modules/valuation/newTaipei'

describe('New Taipei valuation jurisdiction', () => {
  it('keeps the city fixed and exposes the 29 supported administrative districts', () => {
    expect(NEW_TAIPEI_CITY_CODE).toBe('65000000')
    expect(NEW_TAIPEI_DISTRICTS).toHaveLength(29)
    expect(new Set(NEW_TAIPEI_DISTRICTS.map((district) => district.code)).size).toBe(29)
    expect(NEW_TAIPEI_DISTRICTS[0]).toEqual({ code: '65000010', name: '板橋區' })
    expect(NEW_TAIPEI_DISTRICTS.at(-1)).toEqual({ code: '65000290', name: '烏來區' })
  })
})
