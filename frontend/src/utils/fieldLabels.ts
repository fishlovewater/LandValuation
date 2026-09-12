const FIELD_LABELS: Readonly<Record<string, string>> = {
  before_value: '修改前內容',
  after_value: '修改後內容',
  old_value: '修改前內容',
  new_value: '修改後內容',
  previous_value: '修改前內容',
  current_value: '修改後內容',
  raw_value: '原始內容',
  raw_text: '原始辨識內容',
  normalized_value: '整理後內容',
  field_name: '欄位名稱',
  field_code: '欄位項目',
  field_path: '相關欄位',
  form_code: '表單類型',
  form_status: '表單狀態',
  rule_code: '檢核項目',
  rule_name: '檢核項目',
  case_no: '案件編號',
  case_title: '案件名稱',
  case_type: '案件類型',
  case_status: '案件狀態',
  document_type: '文件類型',
  document_code: '文件編號',
  document_version: '文件版本',
  version_no: '版本',
  file_name: '檔案名稱',
  original_filename: '檔案名稱',
  file_size_bytes: '檔案大小',
  mime_type: '檔案格式',
  content_type: '檔案格式',
  page_no: '頁碼',
  page_number: '頁碼',
  article_no: '條文',
  section_name: '段名',
  source_type: '資料來源',
  source_module: '資料來源',
  source: '審查資料來源',
  source_page: '來源頁碼',
  run_no: '檢核批次',
  input_version: '審查輸入版本',
  frozen_at: '輸入凍結時間',
  fingerprint: '內容指紋',
  document_count: '使用文件數',
  primary_document_name: '主要文件',
  primary_document_version: '主要文件版本',
  primary_document_checksum: '主要文件指紋',
  confidence: '辨識可信度',
  ai_confidence: '智能分析可信度',
  ai_status: '智能分析狀態',
  ai_reasoning_summary: '智能分析說明',
  recommended_action: '建議處理方式',
  status: '狀態',
  result_status: '結果狀態',
  run_status: '檢核狀態',
  review_status: '審查狀態',
  review_type: '審查類型',
  finding_type: '疑點類型',
  finding_status: '疑點狀態',
  finding_code: '疑點項目',
  verification_status: '確認狀態',
  notification_status: '通知狀態',
  recheck_outcome: '重新檢核結果',
  correction_status: '補正狀態',
  valuation_type: '估價類型',
  valuation_status: '估價狀態',
  analysis_status: '分析狀態',
  status_group: '工作群組',
  risk_level: '風險等級',
  overall_risk_level: '整體風險',
  current_risk_level: '目前風險',
  risk_score: '風險分數',
  severity: '嚴重程度',
  summary: '摘要',
  decision: '處理決定',
  decision_reason: '決定理由',
  decision_note: '處理備註',
  change_reason: '修改原因',
  change_summary: '修改摘要',
  requested_role: '申請角色',
  display_name: '顯示名稱',
  username: '帳號',
  email: '電子郵件',
  reason: '原因',
  is_active: '目前使用版本',
  created_at: '建立時間',
  updated_at: '最後更新時間',
  uploaded_at: '上傳時間',
  received_at: '收件時間',
  started_at: '開始時間',
  completed_at: '完成時間',
  generated_at: '產生時間',
  calculated_at: '計算時間',
  decided_at: '決定時間',
  handled_at: '處理時間',
  due_at: '期限',
  prepared_date: '製表日期',
  valuation_base_date: '估價基準日',
  land_no: '地號',
  subsection_name: '小段',
  area_sqm: '面積（平方公尺）',
  land_use_zone: '土地使用分區',
  designated_use: '編定使用',
  price_zone_no: '地價區段',
  unit_price: '單價',
  total_value: '總價',
  passed_count: '通過項目',
  warning_count: '警示項目',
  failed_count: '需處理項目',
  missing_item_count: '缺件數',
  high_count: '高風險項目',
  medium_count: '中風險項目',
  low_count: '低風險項目',
  sort_by: '排序欄位',
  sort_direction: '排序方式',
  page_size: '每頁筆數',
}

const ROLE_LABELS: Readonly<Record<string, string>> = {
  APPRAISER: '估價人員',
  REVIEWER: '審查人員',
  INSPECTOR: '案件查詢人員',
  ADMIN: '系統管理員',
  SYSTEM_ADMIN: '系統管理員',
  SUPERADMIN: '系統管理員',
}

const TECHNICAL_ONLY_FIELDS = new Set([
  'object_key',
  'bucket_name',
  'checksum',
  'checksum_sha256',
  'sha256',
  'content_hash',
  'etag',
  'provider',
  'model_id',
  'generation_mode',
  'input_fingerprint',
  'payload',
  'request_payload',
  'response_payload',
  'metadata_json',
  'trace_id',
])

function normalizeFieldKey(value: string): string {
  return value
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/\[[^\]]*\]/g, '')
    .replace(/[.\-\s/]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .toLowerCase()
}

export function isTechnicalOnlyField(value: string): boolean {
  const key = normalizeFieldKey(value)
  if (!key || key === 'id' || key.endsWith('_id') || key.endsWith('_uuid')) return true
  if (key.includes('password') || key.includes('secret') || key.endsWith('_token')) return true
  return TECHNICAL_ONLY_FIELDS.has(key)
}

export function userFieldLabel(value: string): string {
  const key = normalizeFieldKey(value)
  if (!key) return '其他資料'
  const explicit = FIELD_LABELS[key]
  if (explicit) return explicit

  if (key.endsWith('_at')) return '相關時間'
  if (key.endsWith('_date')) return '相關日期'
  if (key.endsWith('_status')) return '狀態'
  if (key.endsWith('_type')) return '類型'
  if (key.endsWith('_count')) return '項目數量'
  if (key.endsWith('_reason')) return '原因'
  if (key.endsWith('_summary')) return '摘要'
  if (key.endsWith('_name')) return '名稱'
  if (key.endsWith('_number') || key.endsWith('_no')) return '編號'
  if (key.endsWith('_version')) return '版本'
  if (key.endsWith('_score')) return '分數'
  if (key.endsWith('_level')) return '等級'
  if (key.endsWith('_price')) return '價格'
  if (key.endsWith('_amount')) return '金額'
  if (key.endsWith('_rate')) return '比率'
  if (key.endsWith('_value') || key.endsWith('_text')) return '內容'
  if (key.endsWith('_code')) return '資料項目'

  return '其他資料'
}

export function userRoleLabel(value: string | null | undefined): string {
  const role = typeof value === 'string' ? value.trim().toUpperCase() : ''
  return ROLE_LABELS[role] ?? '其他工作角色'
}

function briefStructuredValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'bigint') return String(value)
  if (Array.isArray(value)) return value.length ? `${value.length} 筆資料` : '—'
  return '已提供資料'
}

export function userStructuredValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'bigint') return String(value)

  if (Array.isArray(value)) {
    if (!value.length) return '—'
    const allScalar = value.every((item) => item === null || ['string', 'number', 'boolean', 'bigint'].includes(typeof item))
    if (allScalar) {
      const visible = value.slice(0, 6).map(briefStructuredValue)
      return `${visible.join('、')}${value.length > visible.length ? `，另有 ${value.length - visible.length} 筆` : ''}`
    }
    return `${value.length} 筆資料`
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([key, item]) => !isTechnicalOnlyField(key) && item !== null && item !== undefined && item !== '')
      .slice(0, 4)
    if (!entries.length) return '已提供資料'
    return entries
      .map(([key, item]) => `${userFieldLabel(key)}：${briefStructuredValue(item)}`)
      .join('、')
  }

  return '已提供資料'
}