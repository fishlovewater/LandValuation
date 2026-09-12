import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ValuationParcelImportPanel from '../../src/modules/valuation/components/ValuationParcelImportPanel.vue'
import type { ParcelImportPreviewDto } from '../../src/modules/valuation/valuation.types'

const preview: ParcelImportPreviewDto = {
  document_id: '11111111-1111-4111-8111-111111111111',
  filename: '宗地個別因素清冊.xls',
  layout: 'OFFICIAL_TRANSPOSED',
  ready_count: 1,
  needs_confirmation_count: 0,
  duplicate_count: 1,
  candidates: [
    {
      source_location: '宗地個別因素清冊!C欄',
      source_serial: '0001',
      source_owner_name: '甲一',
      district_code: '65000010',
      district_name: '板橋區',
      section_name: '文化段',
      subsection_name: '一小段',
      land_no: '30',
      area_sqm: '878',
      land_use_zone: '住宅區',
      designated_use: null,
      ownership_numerator: null,
      ownership_denominator: null,
      status: 'READY',
      errors: [],
      warnings: [],
      existing_parcel_id: null,
    },
    {
      source_location: '宗地個別因素清冊!D欄',
      source_serial: '0002-01',
      source_owner_name: '乙二',
      district_code: '65000010',
      district_name: '板橋區',
      section_name: '文化段',
      subsection_name: '一小段',
      land_no: '31-1',
      area_sqm: '952.5',
      land_use_zone: '住宅區',
      designated_use: null,
      ownership_numerator: null,
      ownership_denominator: null,
      status: 'DUPLICATE',
      errors: [],
      warnings: [],
      existing_parcel_id: '22222222-2222-4222-8222-222222222222',
    },
  ],
}

describe('ValuationParcelImportPanel', () => {
  it('shows district names, excludes duplicates, and emits only confirmed parcel rows', async () => {
    const wrapper = mount(ValuationParcelImportPanel, {
      props: {
        preview,
        caseDistrictCode: '65000010',
        loading: false,
        importing: false,
        canImport: true,
      },
    })

    expect(wrapper.text()).toContain('內政部清冊格式')
    expect(wrapper.text()).toContain('板橋區')
    expect(wrapper.text()).toContain('所有權人／管理人：甲一')
    expect(wrapper.text()).toContain('既有宗地 1 筆')
    expect(wrapper.get('[data-testid="parcel-import-submit"]').text()).toContain('確認匯入 1 筆')
    expect(wrapper.get('[data-testid="parcel-import-row-1"] input[type="checkbox"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="parcel-import-submit"]').trigger('click')

    expect(wrapper.emitted('import')).toHaveLength(1)
    expect(wrapper.emitted('import')?.[0]).toEqual([
      [
        {
          source_location: '宗地個別因素清冊!C欄',
          source_serial: '0001',
          district_code: '65000010',
          section_name: '文化段',
          subsection_name: '一小段',
          land_no: '30',
          area_sqm: '878',
          land_use_zone: '住宅區',
          designated_use: null,
          ownership_numerator: null,
          ownership_denominator: null,
        },
      ],
    ])
  })
})
