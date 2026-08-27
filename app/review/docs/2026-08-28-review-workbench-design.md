# Review 審查人員工作台設計

## 目的

將既有 development-only API 測試主控台改造成接近未來正式產品的「審查人員工作台」。使用者以審查業務語言操作案件、疑點、決策、修正版與報告，不需要理解 UUID、API path 或 HTTP response。

本次仍只修改 `app/review/**`。若實作需要修改其他路徑，必須停止並先取得使用者同意。

## 已確認決策

- 採審查人員工作台，不採單一案件展示或雙角色完整前端。
- seed 後 Demo 案件直接出現在待審清單。
- 保留「搜尋既有案件後手動建立審查」功能。
- 審查人員按「開始智慧審查」後，系統先檢查完整性；完整才執行 Run。
- 修正版由 development-only Demo 工具列模擬查估端送出，不將修改查估資料呈現為審查人員正式權限。
- 技術性 API 紀錄收進預設關閉的「開發資訊」抽屜。
- 直接以工作台取代現有 `/api/v1/review/test-ui` 內容，網址維持不變。
- 採 Review 工作台 View API；不建立 Vue/React 專案，不修改其他子系統或根目錄 build 設定。

## 使用者與邊界

主要使用者是具有 `review.execute`、`review.decide` 權限的審查人員。

正式操作包括：

- 查看、搜尋及篩選審查案件。
- 搜尋尚未進入審查的既有案件並建立 Review。
- 檢查文件與資料完整性。
- 執行智慧審查與複查。
- 查看風險、疑點、證據與法規依據。
- 作成 Finding 與案件決策。
- 查看版本差異、歷次 Run 與決策歷史。
- 預覽 JSON report、產生及下載 PDF。

development-only 操作包括：

- 載入測試工作台 HTML。
- 模擬查估端送出修正版。
- 顯示 API path、UUID、HTTP status、耗時與原始 JSON。

OCR、Textract、正式欄位校正、通知寄送、RAG 問答及建立全新查估案件不在本次範圍。

## 頁面資訊架構

### 登入頁

- 帳號與密碼。
- 登入失敗、憑證過期及權限不足提示。
- 不顯示 API Base 或 JWT 欄位。

### 工作台框架

左側導覽：

- 待審案件。
- 審查中。
- 待補件／待修正。
- 已完成。
- 風險案件。

主區案件清單：

- 案件編號、案件名稱、行政區。
- 收件時間、期限、承辦審查人。
- 審查狀態、風險等級、缺件數。
- 關鍵字、狀態、風險篩選。
- 「手動建立審查」入口。

案件審查頁：

- 案件摘要。
- 文件與完整性。
- 智慧檢核結果。
- 疑點與人工決策。
- 修正版差異與歷次 Run。
- 審查報告。

開發資訊抽屜預設關閉，僅 development HTML 顯示。

## 核心流程

### 預載待審案件

`python -m app.review.demo seed` 除既有使用者、案件、文件、抽取與規則外，直接建立一筆 `RECEIVED` Review。登入後可由待審清單開啟，不需貼 Case ID 或建立 Review。

### 手動建立審查

1. 開啟建立視窗。
2. 以案件編號或案件名稱搜尋既有 valuation case。
3. 只回傳尚未存在 Review 的案件。
4. 選擇案件，設定期限與優先級。
5. 使用既有 Review 建立及優先級能力保存，成功後加入待審清單。

手動建立不負責建立新的 valuation case。

### 開始智慧審查

1. 使用者按「開始智慧審查」。
2. 後端執行既有完整性檢查並保存結果。
3. 若不完整，回傳缺件、原因及受影響規則，不建立 Run。
4. 若完整，於同一 use case 接續執行既有同步 Run。
5. 回傳完整性結果、Run、Findings 與 Risk Summary，前端更新案件狀態。

### 人工決策與修正版

1. 審查人員查看 Finding 的申報值、系統值、文件版本、頁碼、原始文字及法規依據。
2. 作成 Finding 決策並填寫理由。
3. 作成案件決策，例如退回修正。
4. development Demo 工具列呼叫獨立 Demo API，模擬查估端提交 v2。
5. 工作台顯示 v1/v2 文件及正式欄位差異。
6. 審查人員按「執行複查」，使用既有 rerun，保留舊 Run、Finding、Decision 與 report。

## 工作台 API

以下 API 是具 JWT 與權限檢查的正式 Review View API，可由未來 Vue/React 前端沿用，不限定 development。

### `GET /api/v1/review/workbench/summary`

回傳：

- 各工作台狀態群組案件數。
- HIGH／CRITICAL 風險案件數。
- 未處理 Finding 與缺件總數。

### `GET /api/v1/review/workbench/cases`

查詢參數：`q`、`status`、`risk_level`、`limit`、`offset`。

每筆回傳：

- review_id、case_id。
- case_no、case_title、district_code。
- review_status、current_risk_level、missing_item_count。
- received_at、due_at、assigned reviewer display name。
- latest validation run number and status。

### `GET /api/v1/review/workbench/cases/{review_id}`

回傳單一畫面所需的聚合資料：

- 案件與 Review 摘要。
- 文件清單及版本。
- 最新完整性與缺件資訊。
- 歷次 Runs。
- 最新風險摘要與 Findings。
- 決策時間軸。
- v1/v2 正式抽取欄位差異。
- 最新 report document metadata。

### `GET /api/v1/review/workbench/eligible-cases`

查詢參數：`q`、`limit`。

只回傳尚無 `review.reviews` 的既有案件，欄位包括 case_id、case_no、case_title、district_code、valuation_base_date、case_status。

### `POST /api/v1/review/workbench/cases/{review_id}/start`

執行完整性檢查；若 ready，接續建立同步 Run。回應明確區分：

- `BLOCKED`：包含 completeness 與 missing items，run 為 null。
- `COMPLETED`：包含 completeness、run、findings 與 risk summary。

### Development Demo API

`POST /api/v1/review/demo/revise`

- 僅 `APP_ENV=development` 可用，其他環境回傳 404。
- 只操作固定 Demo ownership。
- 模擬外部查估端建立 original v2 與 verified official fields。
- 重複執行為 idempotent。

## 程式邊界

為避免單一檔案持續膨脹，工作台拆成：

- `workbench_schemas.py`：View API request/response models。
- `workbench_repository.py`：聚合查詢與 eligible case 搜尋。
- `workbench_service.py`：summary/detail/start orchestration 與版本差異。
- `router.py`：路由與權限邊界，不放聚合邏輯。
- `demo.py`：保留 CLI，提供可由 development route 呼叫的同一 revise service function。
- `test_ui/index.html`：單檔工作台 UI；不增加 npm 或外部 runtime dependency。

不新增 migration；使用現有資料表與欄位。

## 錯誤與互動狀態

- 401：清除失效 token，回到登入畫面。
- 403：顯示缺少審查或決策權限。
- 404：顯示案件不存在；Demo HTML/API 在非 development 同樣使用 404 隱藏。
- 409：顯示 API 的業務錯誤，例如缺件、規則衝突、狀態不允許。
- 422：在對應表單欄位顯示驗證問題。
- 500：保留既有畫面資料並提供重試，不清空使用者輸入。

所有主要操作提供 loading、empty、no-results、success 及 error state。決策需理由，重大案件決策送出前需確認；Run 執行期間禁止重複送出。

## 安全與資料界線

- 工作台 API 全部使用既有 JWT 與 `review.execute`／`review.decide` 權限。
- 搜尋只讀取案件摘要，不讀取或修改其他子系統業務明細。
- 工作台聚合資料以 review_id 為主要操作識別，UI 不要求使用者輸入 UUID。
- Demo revise route 嚴格沿用固定 username、case number、rule set、knowledge code 與 `DEMO-F01` ownership。
- 技術紀錄不得顯示密碼；JWT 只存在 sessionStorage。
- MinIO 仍只保存檔案本體；PostgreSQL 只保存 metadata/object key，不保存固定 localhost URL。

## 測試與驗收

- seed 後案件直接出現在 `RECEIVED` 待審清單。
- summary 與案件清單的狀態、風險、缺件計數正確。
- 依案件編號或名稱搜尋 eligible case。
- 已有 Review 的案件不出現在 eligible results。
- 手動建立後案件加入清單，重複建立維持既有衝突行為。
- start 的缺件路徑不建立 Run。
- start 的完整路徑建立同步完成 Run，回傳 Findings 與 Risk。
- Finding／案件決策與權限檢查。
- Demo HTTP revise 的 development 200、非 development 404、idempotency 與 ownership collision。
- v1/v2 差異、rerun history 與 `supersedes_finding_id`。
- JSON/PDF report 及 MinIO metadata/download。
- UI 不要求輸入 UUID，並具有登入、清單、案件頁、決策、版本及報告區。
- 開發資訊預設關閉，但能查看 method、path、status、elapsed 與 payload。
- 鍵盤 focus、窄螢幕布局及 reduced-motion。
- Demo 預先存在時，完整 `app/review/tests` 仍通過且不污染一般 F01 案件。

## 非目標

- 不建立正式 Vue/React bundle。
- 不修改根目錄依賴、Compose、main router 或 migration。
- 不讓審查人員直接編輯正式抽取值。
- 不模擬 OCR、RAG、通知寄送或其他子系統前端。

