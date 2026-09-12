import { describe, expect, it } from 'vitest'
import {
  analysisProviderLabel,
  extractedFieldStatusLabel,
  extractionStatusLabel,
  VALUATION_CASE_TYPE,
  valuationCaseTypeLabel,
  valuationFieldLabel,
  valuationLandUseLabel,
} from '../../src/modules/valuation/valuation.labels'

describe('valuation labels', () => {
  it('translates stored case type codes without altering readable values', () => {
    expect(VALUATION_CASE_TYPE).toBe('LAND')
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

  it('keeps internal valuation field names out of user-facing labels', () => {
    expect(valuationFieldLabel('parcel_area')).toBe('宗地面積')
    expect(valuationFieldLabel('transaction_total_price')).toBe('交易總價')
    expect(valuationFieldLabel('valuation_base_date')).toBe('估價基準日')
    expect(valuationFieldLabel('FUTURE_ENGINEERING_FIELD')).toBe('其他估價欄位')
  })

  it('translates extraction and candidate status codes with safe fallbacks', () => {
    expect(extractionStatusLabel('COMPLETED')).toBe('辨識完成')
    expect(extractionStatusLabel('RUNNING')).toBe('辨識處理中')
    expect(extractionStatusLabel('FUTURE_STATUS')).toBe('處理狀態待確認')
    expect(extractedFieldStatusLabel('NEEDS_CONFIRMATION')).toBe('待確認')
    expect(extractedFieldStatusLabel('FUTURE_STATUS')).toBe('已處理')
  })

  it('translates analysis providers without exposing implementation names', () => {
    expect(analysisProviderLabel('LOCAL_OCR')).toBe('文件文字辨識')
    expect(analysisProviderLabel('local_pdf')).toBe('文件文字辨識')
    expect(analysisProviderLabel('ollama')).toBe('智能欄位分析')
    expect(analysisProviderLabel('future_provider')).toBe('系統辨識')
  })
})