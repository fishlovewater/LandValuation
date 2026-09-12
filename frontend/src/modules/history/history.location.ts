export const HISTORY_NEW_TAIPEI_CITY_CODE = '65000000'

export const HISTORY_NEW_TAIPEI_DISTRICTS = [
  { code: '65000010', legacyCode: '3101', name: '板橋區' },
  { code: '65000020', legacyCode: '3102', name: '三重區' },
  { code: '65000030', legacyCode: '3104', name: '中和區' },
  { code: '65000040', legacyCode: '3103', name: '永和區' },
  { code: '65000050', legacyCode: '3106', name: '新莊區' },
  { code: '65000060', legacyCode: '3105', name: '新店區' },
  { code: '65000070', legacyCode: '3107', name: '樹林區' },
  { code: '65000080', legacyCode: '3108', name: '鶯歌區' },
  { code: '65000090', legacyCode: '3109', name: '三峽區' },
  { code: '65000100', legacyCode: '3110', name: '淡水區' },
  { code: '65000110', legacyCode: '3111', name: '汐止區' },
  { code: '65000120', legacyCode: '3112', name: '瑞芳區' },
  { code: '65000130', legacyCode: '3113', name: '土城區' },
  { code: '65000140', legacyCode: '3114', name: '蘆洲區' },
  { code: '65000150', legacyCode: '3115', name: '五股區' },
  { code: '65000160', legacyCode: '3116', name: '泰山區' },
  { code: '65000170', legacyCode: '3117', name: '林口區' },
  { code: '65000180', legacyCode: '3118', name: '深坑區' },
  { code: '65000190', legacyCode: '3119', name: '石碇區' },
  { code: '65000200', legacyCode: '3120', name: '坪林區' },
  { code: '65000210', legacyCode: '3121', name: '三芝區' },
  { code: '65000220', legacyCode: '3122', name: '石門區' },
  { code: '65000230', legacyCode: '3123', name: '八里區' },
  { code: '65000240', legacyCode: '3124', name: '平溪區' },
  { code: '65000250', legacyCode: '3125', name: '雙溪區' },
  { code: '65000260', legacyCode: '3126', name: '貢寮區' },
  { code: '65000270', legacyCode: '3127', name: '金山區' },
  { code: '65000280', legacyCode: '3128', name: '萬里區' },
  { code: '65000290', legacyCode: '3129', name: '烏來區' },
] as const

const DISTRICT_BY_CODE = new Map<string, (typeof HISTORY_NEW_TAIPEI_DISTRICTS)[number]>()
HISTORY_NEW_TAIPEI_DISTRICTS.forEach((district) => {
  DISTRICT_BY_CODE.set(district.code, district)
  DISTRICT_BY_CODE.set(district.legacyCode, district)
  DISTRICT_BY_CODE.set(district.name, district)
})

const NEW_TAIPEI_CITY_CODES = new Set(['31', '65000', HISTORY_NEW_TAIPEI_CITY_CODE, 'NWT', '新北市'])

export function historyCanonicalDistrictCode(value: string | null | undefined): string {
  const normalized = value?.trim()
  if (!normalized) return ''
  return DISTRICT_BY_CODE.get(normalized)?.code ?? ''
}

export function historyDistrictLabel(value: string | null | undefined): string {
  const normalized = value?.trim()
  if (!normalized) return ''
  return DISTRICT_BY_CODE.get(normalized)?.name ?? (normalized.endsWith('區') ? normalized : '')
}

export function historyLocationLabel(
  cityCode: string | null | undefined,
  districtCode: string | null | undefined,
): string {
  const district = historyDistrictLabel(districtCode)
  const normalizedCity = cityCode?.trim() ?? ''
  const city = NEW_TAIPEI_CITY_CODES.has(normalizedCity) ? '新北市' : ''
  if (city && district) return `${city} ${district}`
  if (district) return district
  if (city) return `${city} · 行政區資料待確認`
  return '行政區資料待確認'
}