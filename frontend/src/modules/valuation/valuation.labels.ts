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