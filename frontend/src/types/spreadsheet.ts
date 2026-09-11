export type SpreadsheetCell = string | number | boolean | null

export interface SpreadsheetPreviewSheetDto {
  name: string
  rows: SpreadsheetCell[][]
  total_rows: number
  total_columns: number
  truncated: boolean
}

export interface SpreadsheetPreviewDto {
  kind: 'spreadsheet'
  sheets: SpreadsheetPreviewSheetDto[]
  truncated: boolean
}
