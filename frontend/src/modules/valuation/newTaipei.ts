export const NEW_TAIPEI_CITY_CODE = '65000000'

export const NEW_TAIPEI_DISTRICTS = [
  { code: '65000010', name: '板橋區' },
  { code: '65000020', name: '三重區' },
  { code: '65000030', name: '中和區' },
  { code: '65000040', name: '永和區' },
  { code: '65000050', name: '新莊區' },
  { code: '65000060', name: '新店區' },
  { code: '65000070', name: '樹林區' },
  { code: '65000080', name: '鶯歌區' },
  { code: '65000090', name: '三峽區' },
  { code: '65000100', name: '淡水區' },
  { code: '65000110', name: '汐止區' },
  { code: '65000120', name: '瑞芳區' },
  { code: '65000130', name: '土城區' },
  { code: '65000140', name: '蘆洲區' },
  { code: '65000150', name: '五股區' },
  { code: '65000160', name: '泰山區' },
  { code: '65000170', name: '林口區' },
  { code: '65000180', name: '深坑區' },
  { code: '65000190', name: '石碇區' },
  { code: '65000200', name: '坪林區' },
  { code: '65000210', name: '三芝區' },
  { code: '65000220', name: '石門區' },
  { code: '65000230', name: '八里區' },
  { code: '65000240', name: '平溪區' },
  { code: '65000250', name: '雙溪區' },
  { code: '65000260', name: '貢寮區' },
  { code: '65000270', name: '金山區' },
  { code: '65000280', name: '萬里區' },
  { code: '65000290', name: '烏來區' },
] as const

export function newTaipeiDistrictName(code: string | null | undefined): string {
  if (!code) return ''
  return NEW_TAIPEI_DISTRICTS.find((district) => district.code === code)?.name ?? '行政區待確認'
}
