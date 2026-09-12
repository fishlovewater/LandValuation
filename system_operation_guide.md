# 系統操作指南（欄位確認與計算優先）

> 本文件是目前版本的操作準則。系統會協助擷取、提出欄位候選與檢查資料，但不會自行編造資料、圖表、略圖或地價區段圖。

## 1. 目前流程

~~~
登入 Swagger
→ 建立案件並上傳來源檔
→ 檢查 OCR／AI 候選與證據
→ 明確確認或拒絕每筆候選
→ 下載確認結果清單 Excel (.xlsx) 檢視已處理資料
→ 依 form_guidance 補齊必要欄位
→ 執行計算與驗證
→ 通過驗證後，才視需要手動產生 PDF
~~~

按下 confirm 不會自動建立正式估價 PDF；`automatic_pdf_generation_enabled` 仍為 false。但每次 confirm 都會建立一份「確認結果清單 Excel (.xlsx)」，讓使用者在一行一行的試算表中完整檢視本次已確認、已套用或已拒絕的欄位結果與原文來源證據，無版面截斷問題。

## 2. 啟動與登入

在專案根目錄執行：

~~~
cd "D:\master proj\LandValuationAssistant"
docker compose up -d --build api
docker compose ps -a
~~~

此電腦的專案根目錄已放置可攜式 PowerShell 7 於 `.tools\powershell\pwsh.exe`。若 VS Code 新終端機未自動使用 PowerShell 7，或 `pwsh` 指到 Windows Store 別名，後續的欄位分析指令請一律改用：

~~~
.\.tools\powershell\pwsh.exe --version
~~~

開啟：

- Swagger：http://localhost:8000/docs
- MinIO：http://localhost:9001
- 健康檢查：http://localhost:8000/health/ready

先用 POST /api/v1/auth/login 登入，複製回應的 access_token，再按 Swagger 右上角 Authorize，貼上 token（不用自行加 Bearer）。

以 GET /api/v1/auth/me 回傳 200 確認登入有效。

## 3. 建立案件與上傳文件

在 Swagger 使用：

~~~
POST /api/v1/valuation/auto-workflows/intake
~~~

- intake_manifest_json 填入本案真實案件資料。
- files 一次選取本案全部來源檔。
- 至少要有一個檔案。
- case_id 與 document_id 都要從這次 Swagger 回應複製；UUID 格式必須是 8-4-4-4-12。

常見資料：

~~~
{
  "case": {
    "case_no": "本案案號",
    "case_title": "本案名稱",
    "case_type": "土地徵收補償市價查估",
    "valuation_base_date": "YYYY-MM-DD",
    "city_code": "65000000",
    "district_code": "本案行政區代碼",
    "land_use_type": "COMMERCIAL"
  },
  "parcels": [],
  "benchmark_lands": [],
  "create_commercial_report": true
}
~~~

上傳的檔案會保存到 MinIO；系統對 PDF 做文字擷取或 OCR。XLSX 會保留工作表、列與儲存格座標，再將結果保留為待確認的欄位候選值。

若 XLSX 有「比較標的」工作表（例如 `06比較標的資料`），F01 的實例編號、交易日期、行政區／段／地號、面積與有明確欄名的交易總價或正常土地單價，會由該工作表直接擷取。它們仍須確認，但不交由 AI 猜測，也不會誤用徵收宗地工作表的資料。

## 4. 讓 Codex 分析欄位候選（選用）

這個步驟只產生候選欄位與證據，不能取代人工確認，也不會直接寫入正式表單。

### 4.1 依匯入規格分析 S01 與 F02-RF

系統已匯入下列六份 Excel 表單規格作為 AI 欄位白名單：

- 買賣實例調查估價表（建物全部層數，F01）：26 個作業與稽核欄位。
- 地價區段勘查表（S01）：77 個欄位，含道路、設施、污染源、土地使用、勘查與簽核資料。
- 影響地價區域因素分析明細表（商業用地，F02-RF）：29 項區域因素，並保存原始細項代碼 C1_01 至 C8_01。
- 比較法調查估價表（F02）：26 個作業與稽核欄位。
- 比準地地價估計表（F03）：24 個作業與稽核欄位。
- 徵收土地宗地市價估計表（F04）：17 個作業與稽核欄位。

若已設定 Bedrock，案件上傳並完成 OCR 後，商業用地會自動依這些欄位規格分批建立候選資料。AI 只可回傳文件中實際出現、且附有 source_text 原文證據的欄位。

以 Codex 手動測試時，可改用：

~~~
.\.tools\powershell\pwsh.exe -NoProfile -File .\scripts\run_codex_field_analysis.ps1 -CaseId "<case_id>" -DocumentId "<document_id>" -FormCode "S01" -ModelId "gpt-5.4"

.\.tools\powershell\pwsh.exe -NoProfile -File .\scripts\run_codex_field_analysis.ps1 -CaseId "<case_id>" -DocumentId "<document_id>" -FormCode "F02-RF" -ModelId "gpt-5.4"
~~~

S01 欄位較多；每次 Codex 匯入最多 30 個有證據的候選。重新執行相同 S01 指令時，已經儲存的候選會排除，讓下一次分析其餘欄位。


請使用 PowerShell 7，不要用 Windows PowerShell 5.1。這台電腦請優先使用專案內的可攜版本：

~~~
.\.tools\powershell\pwsh.exe --version

.\.tools\powershell\pwsh.exe -NoProfile -File .\scripts\run_codex_field_analysis.ps1 -CaseId "<case_id>" -DocumentId "<document_id>" -FormCode "F01" -ModelId "gpt-5.4"
~~~

注意：

- F01 的 Codex 分析只讀取「比較標的」工作表；PDF、Word 或 OCR 文字則只讀取有「買賣實例調查估價表」表頭的區段。若沒有可辨識的比較標的／比較實例來源，系統會停止並回傳 `F01_SOURCE_SCOPE_NOT_FOUND`，不會把徵收宗地、比準地或其他表單資料誤填為 F01。
- Excel 中已有固定欄列的值，會先由 `XLSX_RULE` 建立待確認候選；Codex 只分析尚未由規則擷取的欄位與需要語意判斷的描述。
- case_id、document_id 必須來自同一個 API、資料庫與登入帳號。
- 出現 RESOURCE_NOT_FOUND（找不到指定案件）時，先用 GET /api/v1/valuation/cases 確認該案件在目前登入帳號與目前 API 中可見；不要混用其他 Docker、Swagger 或測試資料庫的 UUID。
- 出現 UUID 格式錯誤時，重新從 Swagger 回應複製完整 ID，不要從 MinIO 路徑猜測。
- PowerShell 5.1 的語法錯誤或亂碼，代表啟動了錯誤的 PowerShell；改用上面的 pwsh 指令。

## 5. Review：核對候選資料

使用：

~~~
GET /api/v1/valuation/cases/{case_id}/auto-workflow/review
~~~

每一筆候選都要檢查：

- form_code：資料要填入哪張表，例如 F01。
- field_code：對應欄位。
- candidate_value：擷取或 AI 建議的值。
- source_text、頁碼或來源證據。
- analysis_provider：確認是否為 CODEX、OCR 或其他來源。
- field_status：尚未確認的候選不可直接視為正式資料。

無證據、內容不確定或不屬於本案的候選要拒絕，而不是硬填。

## 6. Confirm：只套用明確確認的欄位

使用：

~~~
POST /api/v1/valuation/cases/{case_id}/auto-workflow/confirm
~~~

範例：

~~~
{
  "confirmations": [
    {
      "document_id": "來源文件的 document_id",
      "extracted_field_id": "候選欄位的 extracted_field_id",
      "decision": "CONFIRM",
      "corrected_value": null
    }
  ],
  "confirm_apply": true
}
~~~

如果候選值要修正，仍使用 CONFIRM，並在 corrected_value 填入已核對的真實值。拒絕時使用 REJECT，且 corrected_value 必須是 null。

確認後，重點看回應：

- status 為 READY_FOR_VALIDATION：已進入補欄位／計算／驗證流程。
- form_guidance：每張表下一步應做什麼。
- missing_required_fields：必填但尚缺的欄位。
- pending_confirmation_fields：仍待人工決定的候選。
- calculation_ready：是否可以計算。
- fill_endpoint、calculate_endpoint、validate_endpoint：Swagger 中下一個可呼叫的 API。
- automatic_pdf_generation_enabled 為 false：系統沒有自動產生正式估價 PDF。
- confirmation_export：本次確認結果清單 Excel (.xlsx) 的檔名、document_id 與 download_path。

要下載確認結果，在 Swagger 保持已 Authorize 的狀態，直接開啟回應中的 `confirmation_export.download_path`，或使用：

~~~
GET /api/v1/valuation/cases/{case_id}/documents/{confirmation_export.document_id}/download
~~~

此 Excel 表格列出欄位審核成果（表單、欄位、狀態、確認/修正值、擷取原始值、來源證據、頁碼等），每一筆候選完整呈現，不是正式估價報告。

F02-RF 的候選確認只保存已審核的原文資料；尚未選擇正式規則版本時，系統會保留提示 `F02_RF_CONFIRMED_CANDIDATES_AWAIT_RULE_VERSION`，但不會拒絕 confirm。規則版本與因素級距只在後續正式轉換與計算時才需要。

## 7. F01：補值、計算、驗證

F01（買賣實例調查估價表）在計算前至少需有：

~~~
transaction_no
transaction_date
transaction_total_price
location
land_area_sqm
~~~

操作順序：

1. 從 form_guidance 取得 form_instance_id。
2. 用回應的 fill_endpoint 補齊或修正欄位。F01 為 PATCH /api/v1/valuation/cases/{case_id}/forms/{form_id}/f01。
3. 用 calculate_endpoint（POST .../f01/calculate）執行計算。
4. 用 validate_endpoint（POST .../f01/validate）檢查結果。
5. 只有驗證通過、數值與來源證據都合理時，才進入後續正式作業。

若回應提示 FILL_MISSING_REQUIRED_FIELDS，先補完 missing_required_fields；若提示 CONFIRM_OR_REJECT_CANDIDATES，先回到 review/confirm 處理候選。

## 8. F03、F02-RF、F02 與正式計算

其他表單也以 form_guidance 為準：

- F03 必要資料含 valuation_base_date、benchmark_land_id，並需要地籍／土地登記來源文件。
- F02-RF 與 F02 的因素、修正率、公式和比準地資料，必須來自已核實的正式規則及人工確認資料。
- 系統不讓 AI 自行建立級距、修正率或計算公式。
- 只有需要輸出正式文件時，才在所有必要表單完成計算與驗證後，使用明確的正式 PDF API。

## 9. 圖件與 MinIO

系統不會自行製作、繪製或補造：

- 低價區段略圖
- 地價使用分區圖
- 地價區段圖
- 任何圖表或地圖

系統不要求上傳這些圖件，也不會因為缺少圖件而阻擋欄位確認、計算或驗證流程。

MinIO 的 land-valuation bucket 用於保存原始上傳檔與日後明確產生的檔案。confirm 成功後會保存最新的確認結果清單 Excel (.xlsx)；成功標準仍是欄位已安全套用，並回傳正確的 form_guidance。

## 10. 常見問題

| 現象 | 原因與處理 |
|---|---|
| pwsh 找不到或指到 Windows Store 版本 | 直接使用 `.\.tools\powershell\pwsh.exe`；這是本專案已驗證可用的 PowerShell 7.6.5。 |
| PowerShell 顯示 OCR、引號、try 等語法錯誤 | 多半是 Windows PowerShell 5.1 解析 UTF-8 指令碼造成；改用 pwsh -NoProfile -File ...。 |
| RESOURCE_NOT_FOUND | case/document UUID 與目前 API、資料庫或登入身分不一致；先用 cases API 查詢。 |
| 422 或 UUID 格式錯誤 | 依 Swagger 回應修正欄位，並使用完整 UUID。 |
| 409 DATA_CONFLICT（Codex 已找到候選但無法儲存） | 通常是服務尚未套用最新 migration。於專案根目錄執行 `docker compose up -d --build`，確認 migrate 完成後再重跑相同表單分析；同一文件不同 form_code 的同名欄位可以並存。 |
| confirm 後找不到確認結果 Excel (.xlsx) | 先確認服務已以 `docker compose up -d --build` 更新，再重新執行一次 confirm；於回應的 `confirmation_export` 取得 API 下載路徑。 |
| 欄位仍空白 | 候選尚未確認、缺少必要資料，或該欄沒有可靠證據；不可用猜測補值。 |
| MinIO 按下載沒有反應 | 可改用 API 回應中的授權下載路徑；瀏覽器也要允許 localhost:9001 的下載。 |

## 11. 上線前檢查

- [ ] /health/ready 顯示 PostgreSQL 與 MinIO 正常。
- [ ] /auth/me 可驗證目前登入帳號。
- [ ] Review 的每個已確認候選都有來源證據。
- [ ] form_guidance.missing_required_fields 已處理。
- [ ] 每張需要計算的表單均已計算及驗證。
- [ ] 沒有把 AI/OCR 候選、範例檔或猜測值當成正式數值。
- [ ] 若要產出 PDF，已由使用者明確決定，且所有前置驗證通過。
