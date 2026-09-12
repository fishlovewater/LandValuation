import { describe, expect, it } from 'vitest'
import {
  isTechnicalOnlyField,
  userFieldLabel,
  userRoleLabel,
  userStructuredValue,
} from '../../src/utils/fieldLabels'

describe('user-facing technical field labels', () => {
  it('converts common backend field names into readable Traditional Chinese', () => {
    expect(userFieldLabel('before_value')).toBe('修改前內容')
    expect(userFieldLabel('after_value')).toBe('修改後內容')
    expect(userFieldLabel('field_name')).toBe('欄位名稱')
    expect(userFieldLabel('rule_code')).toBe('檢核項目')
    expect(userFieldLabel('riskLevel')).toBe('風險等級')
    expect(userFieldLabel('statusGroup')).toBe('工作群組')
  })

  it('does not expose an unknown snake_case key as a raw engineering label', () => {
    expect(userFieldLabel('internal_magic_flag')).toBe('其他資料')
    expect(userFieldLabel('internal_magic_flag')).not.toContain('_')
  })

  it('hides internal identifiers and provider metadata from generic record displays', () => {
    expect(isTechnicalOnlyField('document_id')).toBe(true)
    expect(isTechnicalOnlyField('request_id')).toBe(true)
    expect(isTechnicalOnlyField('provider')).toBe(true)
    expect(isTechnicalOnlyField('model_id')).toBe(true)
    expect(isTechnicalOnlyField('before_value')).toBe(false)
  })

  it('uses readable role names without leaking unknown role codes', () => {
    expect(userRoleLabel('APPRAISER')).toBe('估價人員')
    expect(userRoleLabel('REVIEWER')).toBe('審查人員')
    expect(userRoleLabel('SYSTEM_ADMIN')).toBe('系統管理員')
    expect(userRoleLabel('INTERNAL_ROLE_X')).toBe('其他工作角色')
  })

  it('summarizes structured values with localized keys instead of raw JSON', () => {
    const displayed = userStructuredValue({
      before_value: '舊值',
      after_value: '新值',
      provider: 'ollama',
      document_id: 'internal-id',
    })

    expect(displayed).toBe('修改前內容：舊值、修改後內容：新值')
    expect(displayed).not.toContain('before_value')
    expect(displayed).not.toContain('provider')
    expect(displayed).not.toContain('ollama')
    expect(displayed).not.toContain('{')
  })

  it('renders booleans in ordinary language', () => {
    expect(userStructuredValue(true)).toBe('是')
    expect(userStructuredValue(false)).toBe('否')
  })
})