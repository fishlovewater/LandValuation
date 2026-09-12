import { userFieldLabel } from '../../utils/fieldLabels'

export const LAND_USE_OPTIONS = [
  { value: 'RESIDENTIAL', label: '住宅用地' },
  { value: 'COMMERCIAL', label: '商業用地' },
  { value: 'INDUSTRIAL', label: '工業用地' },
  { value: 'AGRICULTURAL', label: '農業用地' },
  { value: 'OTHER', label: '其他用途' },
] as const

export const VALUATION_CASE_TYPE = 'LAND' as const

const CASE_TYPE_LABELS: Readonly<Record<string, string>> = {
  LAND: '土地徵收補償市價查估',
  LAND_ACQUISITION: '土地徵收補償市價查估',
  VALUATION: '土地估價案件',
  EXTERNAL_REVIEW: '外部送審案件',
}

const LAND_USE_LABELS: Readonly<Record<string, string>> = Object.fromEntries(
  LAND_USE_OPTIONS.map((option) => [option.value, option.label]),
)

const VALUATION_FIELD_LABELS: Readonly<Record<string, string>> = {
  administrative_area: '行政區',
  area_sqm: '土地面積',
  benchmark_land_id: '比準地',
  benchmark_land_no: '比準地地號',
  benchmark_land_price: '比準地地價',
  benchmark_valuation_id: '比準地估價結果',
  comparison_analysis_id: '比較分析',
  comparison_price: '比準地比較價格',
  comparison_targets: '比較標的',
  comparison_weight: '比較價格權重',
  confirmed_factor_levels: '區域因素確認值',
  decision_reason: '決定理由',
  designated_use: '編定使用',
  income_price: '比準地收益價格',
  income_weight: '收益價格權重',
  land_area_sqm: '土地面積',
  land_no: '地號',
  land_use_zone: '使用分區',
  land_use_zone_category: '使用分區／使用地類別',
  location: '土地坐落',
  main_road_name: '區段內主要道路名稱',
  main_road_width_m: '區段內主要道路寬度',
  market_condition: '市場條件',
  market_period_end: '市場期間迄日',
  market_period_start: '市場期間起日',
  normal_land_unit_price: '正常土地單價',
  parcel_area: '宗地面積',
  parcel_id: '宗地',
  prepared_date: '製表日期',
  price_zone_no: '地價區段號',
  rule_version_id: '發布法規版本',
  section_name: '段名',
  selection_scope_reason: '選擇範圍理由',
  subsection_name: '小段',
  survey_date: '勘查日期',
  transaction_date: '交易日期',
  transaction_no: '實例編號',
  transaction_total_price: '交易總價',
  urban_plan_scope: '都市計畫內外',
  valuation_base_date: '估價基準日',
  zone_boundary_description: '區段範圍說明',
}

function normalizedFieldName(value: string): string {
  return value
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[.\-\s/]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .toLowerCase()
}

export function valuationCaseTypeLabel(value: string | null | undefined): string {
  const raw = value?.trim() ?? ''
  if (!raw) return '未提供'
  const normalized = raw.toUpperCase()
  if (CASE_TYPE_LABELS[normalized]) return CASE_TYPE_LABELS[normalized]
  if (/[^\x00-\x7F]/.test(raw)) return raw
  return '其他估價案件'
}

export function valuationLandUseLabel(value: string | null | undefined): string {
  const raw = value?.trim() ?? ''
  if (!raw) return '未提供'
  const normalized = raw.toUpperCase()
  if (LAND_USE_LABELS[normalized]) return LAND_USE_LABELS[normalized]
  if (/[^\x00-\x7F]/.test(raw)) return raw
  return '其他用途'
}

export function valuationFieldLabel(value: string | null | undefined): string {
  const raw = value?.trim() ?? ''
  if (!raw) return '其他估價欄位'
  const normalized = normalizedFieldName(raw)
  if (VALUATION_FIELD_LABELS[normalized]) return VALUATION_FIELD_LABELS[normalized]
  const generic = userFieldLabel(raw)
  return generic === '其他資料' ? '其他估價欄位' : generic
}

export function extractionStatusLabel(value: string | null | undefined): string {
  const normalized = value?.trim().toUpperCase() ?? ''
  return ({
    PENDING: '等待辨識',
    QUEUED: '等待辨識',
    RUNNING: '辨識處理中',
    PROCESSING: '辨識處理中',
    COMPLETED: '辨識完成',
    FAILED: '辨識失敗',
    CANCELLED: '已取消辨識',
  } as Readonly<Record<string, string>>)[normalized] ?? '處理狀態待確認'
}

export function extractedFieldStatusLabel(value: string | null | undefined): string {
  const normalized = value?.trim().toUpperCase() ?? ''
  return ({
    NEEDS_CONFIRMATION: '待確認',
    CONFIRMED: '已確認',
    APPLIED: '已納入',
    REJECTED: '已排除',
    EXTRACTED: '已辨識',
  } as Readonly<Record<string, string>>)[normalized] ?? '已處理'
}

export function analysisProviderLabel(value: string | null | undefined): string {
  const normalized = value?.trim().toUpperCase() ?? ''
  if (!normalized) return '系統辨識'
  if (normalized === 'RULE' || normalized.includes('RULE')) return '規則比對'
  if (normalized.includes('OCR') || normalized.includes('PDF')) return '文件文字辨識'
  if (
    normalized.includes('OLLAMA')
    || normalized.includes('LLM')
    || normalized.includes('AI')
    || normalized.includes('MODEL')
  ) return '智能欄位分析'
  return '系統辨識'
}