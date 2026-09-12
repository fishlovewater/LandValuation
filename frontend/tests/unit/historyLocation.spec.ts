import { describe, expect, it } from 'vitest'
import {
  historyCanonicalDistrictCode,
  historyDistrictLabel,
  historyLocationLabel,
} from '../../src/modules/history/history.location'

describe('history location labels', () => {
  it('normalizes legacy New Taipei district codes to the current official code', () => {
    expect(historyCanonicalDistrictCode('3101')).toBe('65000010')
    expect(historyCanonicalDistrictCode('3104')).toBe('65000030')
  })

  it('renders current and legacy codes as the same user-facing district name', () => {
    expect(historyDistrictLabel('3102')).toBe('三重區')
    expect(historyDistrictLabel('65000020')).toBe('三重區')
    expect(historyLocationLabel('31', '3102')).toBe('新北市 三重區')
    expect(historyLocationLabel('65000000', '65000020')).toBe('新北市 三重區')
    expect(historyLocationLabel('NWT', '65000020')).toBe('新北市 三重區')
  })

  it('does not expose an unknown engineering district code to users', () => {
    expect(historyDistrictLabel('F01')).toBe('')
    expect(historyLocationLabel('65000000', 'F01')).toBe('新北市 · 行政區資料待確認')
  })
})