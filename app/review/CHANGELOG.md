# Review 子系統變更紀錄

本文件只記錄 `app/review` 第二子系統。提交編號來自本分支 Git 紀錄；「已完成」僅代表已有程式與驗證證據，不包含其他子系統。

## 2026-08-30 - 疑點判定、修正通知與新版重檢

### 審查責任邊界

- 審查子系統只負責「發現問題、確認問題、發出修正要求、重檢新版本」，不再產生任何正式估價值。
- 估價報告內容與正式採用值一律由查估端負責更正；審查僅接受同案件、版本更新且沿革一致的新版文件。

### 已完成

- 疑點人工判定改為 `CONFIRMED_ISSUE`、`DISMISSED_FALSE_POSITIVE`、`EXPERT_REVIEW` 三種，必填理由，且 API 以 `extra="forbid"` 直接拒絕 `after_value`。
- 新增 `POST /findings/{id}/triage`；舊版 `POST /findings/{id}/decisions` 與 `POST /cases/{id}/decision` 改為回傳 409（`LEGACY_FINDING_DECISION_DISABLED`、`LEGACY_CASE_DECISION_DISABLED`），既有歷史決策仍可讀取並標示為「舊流程歷史決策」。
- 新增 `review.correction_requests`、`review.correction_request_items`、`review.urgency_settings` 三張表（migration `20260830_0008`）；每個 Review 同時只允許一筆未完成修正通知，`RECHECKED` 歷史筆數不限。
- 修正通知一經送出即固定案件、Run、原文件版本、通知內容與逐項快照；項目只會來自最新 Run 且經人工確認成立的疑點，內容全部由伺服器端載入。
- 新版重檢會先回到完整性檢查再執行既有 rerun，並依 `supersedes_finding_id` 將每個項目標記為 `RESOLVED`、`STILL_PRESENT` 或 `NOT_EVALUATED`；無法判定者會阻擋完成審查。
- 完成審查合併為單一動作「確認無誤並完成審查」，於單一交易內鎖定案件、重新驗證所有門檻、寫入稽核決策並設為 `REVIEW_COMPLETED`；不再以正式值存在與否作為完成條件。
- 期限緊急度與內容風險完全分離：緊急度於請求時依單一設定快照計算（預設 `urgent_days=3`、`due_soon_days=7`），不寫回 Review 資料列；佇列排序改由 `urgency.py` 統一分級。
- 新增 Excel 與 Word 風險報告產出；工作表與章節皆為業務用中文，證據以可讀欄位／值呈現，且不含任何正式採用值欄位。
- 所有報告 API 回應改用安全 metadata，不再出現 bucket 名稱、object key 或固定 localhost 網址；下載一律以 `document_id` 由伺服器端解析物件位置。
- 產出物為 run/request 範圍且不可變：既有檔案不會被覆寫，相同內容因 per-case checksum 唯一約束而不會重複產生。
- 工作台以「檢核結果／修正通知／新版重檢／報告與歷程」四個業務分頁取代原本的值選取介面；案件清單以獨立徽章分別顯示內容風險與期限緊急度。

### 驗證

- Node 工作台行為測試：`38 pass, 0 fail`（於主機執行，api 映像未安裝 node）。
- 完整 `app/review/tests`：`277 passed, 1 warning`。
- 全專案 `tests app/review/tests`：`289 passed, 1 skipped, 1 warning`；唯一警告仍為既有 Starlette TestClient/httpx deprecation。
- Alembic `current` 與 `heads` 均為 `20260830_0008`，且已驗證 `downgrade 20260825_0007` 後可再 `upgrade head`。

## 2026-08-30 - 正式採用內容與單一步驟核定

### 已完成

- 疑點決策改為「維持原申報內容、採用系統建議內容、另訂正式內容、資料不足要求補件」；決策紀錄由後端統一保存採用來源、欄位位置與正式值。
- 「另訂正式內容」只由審查人員填寫正式採用內容，原申報值與系統建議值均由後端依 Finding 資料取得，避免由前端偽造。
- 核定門檻涵蓋最新 Run、未結缺件、所有未決疑點與缺少正式採用內容的決策；任何一項未完成都不能核定。
- 案件操作合併為「核定並完成審查」；成功時以單一交易建立 `APPROVED` 決策並把案件直接更新為 `REVIEW_COMPLETED`，結案後工作台改為唯讀。
- 工作台顯示核定前阻擋原因，並在選擇核定時停用送出按鈕；後端仍保留相同門檻作為最終防線。

### 驗證

- Node 工作台行為測試：`22 passed`。
- 完整 `app/review/tests`：`182 passed, 1 warning`；唯一警告仍為既有 Starlette TestClient/httpx deprecation。

## 2026-08-28 - 審查人員工作台

### 已完成

- 以正式 Review View API 新增工作台摘要、案件清單、案件聚合詳情、eligible case 搜尋與 start/rerun orchestration；全部沿用既有 JWT、權限、完整性、規則、決策與報告能力。
- Demo seed 直接建立一筆 `RECEIVED` Review；新增 development-only revise HTTP route，production 在驗證 JWT 前固定回傳 404，且 revise 維持冪等與固定 ownership。
- 工作台 start 將完整性與同步 Run 合併為單一 use case；退回修正後同一路徑會先回到 preprocessing、重做完整性，再執行既有 rerun 並保留 supersedes 關聯。
- 案件詳情聚合文件、缺件、Runs、最新 Findings/Risk、決策歷程、正式欄位版本差異與最新 report metadata；版本差異以 `document_group_id` 隔離 lineage。
- 以零外部前端依賴的單檔工作台取代技術主控台，提供登入、伺服器端群組分頁、案件卷宗、完整性／智慧審查、證據與法規、人工決策、修正版、版本差異及 JSON/PDF 報告。
- 開發資訊抽屜預設關閉，紀錄 method/path/status/elapsed/payload，但會遞迴遮蔽 token、authorization 與 password 欄位；JWT 只保存在 `sessionStorage`。
- 新增零相依 Node 行為測試，實際執行憑證遮蔽、部分採納 payload、BLOCKED 提示與伺服器端群組分頁查詢邏輯；版本差異測試亦涵蓋空白 `field_path`。
- 登入首頁新增可手動選取的 Demo seed PowerShell 指令與一鍵複製按鈕；Clipboard 成功或拒絕時均提供可見回饋，不保存固定測試密碼。
- 未新增 migration、Vue/React/npm runtime、根目錄依賴或固定 localhost object URL；所有原始碼變更限定於 `app/review/**`。

### TDD、review 與驗證證據

- 工作台 API RED：2 個 endpoint 皆 404；GREEN：summary/list/eligible/detail 與 blocked start 通過。
- Demo 工作流 RED：缺少 seed review、revise route 與 rerun orchestration；GREEN：seed、start、決策、v2、rerun、version diff 與 supersedes 端到端通過。
- production route hiding RED：無 token 時為 401；GREEN：有無 token 皆為 404，development 仍要求 `review.execute`。
- document lineage RED：不同 group 被錯誤比較；GREEN：只在同一 `document_group_id` 內比較版本。
- UI RED：舊 API 主控台缺少工作台結構；GREEN：工作台結構、安全遮蔽、BLOCKED 呈現、部分採納值、證據／法規／決策歷程與 server-side pagination 契約通過。
- 獨立 code review 找到並修正 JWT logging、partial decision payload、BLOCKED success message、版本 lineage 與前 100 筆限制。
- 完整 `app/review/tests`：`158 passed, 1 warning`；唯一警告仍為既有 Starlette TestClient/httpx deprecation。
- Python compile 與 Node `new Function` JavaScript 語法檢查通過。
- 瀏覽器完成桌面與 390×844 窄螢幕登入頁視覺驗收；登入後完整流程由真實 TestClient、PostgreSQL 與 MinIO 端到端測試驗證。

## 2026-08-27 - Development 手動測試主控台

### 已完成

- 新增 development-only `GET /api/v1/review/test-ui`；非 development 固定回傳 404，且不列入 OpenAPI。
- 新增單檔、零外部前端依賴的 Review API 測試主控台，涵蓋登入、案件、完整性、run、findings、risk、人工決策、rerun、JSON 與 PDF。
- 新增 `python -m app.review.demo seed|revise|reset`，以固定所有權識別管理真實 PostgreSQL 與 MinIO Demo 資料。
- seed 每次產生新密碼且只輸出一次；重複 seed 先安全清除舊 Demo，不累積固定案件或使用者。
- revise 建立 original v2 與新 verified official fields，保留 v1 run、finding、decision 與 report 歷史。
- reset 僅依固定 username、case number、rule set 與 knowledge code 清除；識別碰撞時 fail closed，不刪除資料。
- Demo 案件與規則使用專屬 district `DEMO-F01`，避免已發布 Demo 規則被一般 `LAND + F01` 案件選中。
- live API image 已重建；readiness 顯示 PostgreSQL/MinIO `ok`，run/rerun OpenAPI 都是 `200, 422`，測試頁回傳 200。

### TDD 與驗證證據

- 測試頁 RED：`1 failed, 1 passed`；GREEN：`2 passed`。
- Demo CLI RED：`6 failed`（模組不存在）；公開契約 GREEN：`6 passed`。
- 真實工作流第一次發現所有權查詢參數順序錯誤；修正後端到端 `2 passed`。
- 聚焦安全與流程測試：`12 passed, 1 warning`。
- 完整 Review suite：`153 passed, 1 warning`；唯一警告仍為既有 Starlette TestClient/httpx deprecation。
- 在 Demo 預先存在的條件下，完整 suite 曾抓到 7 failures；隔離 district 並修正碰撞測試前置清理後，同條件恢復 `153 passed, 1 warning`。
- Python compile 成功；單檔 JavaScript 由 Node `new Function` 語法檢查通過。
- 瀏覽器控制工具因本機執行資源路徑錯誤未能連線，因此未宣稱完成自動化視覺驗收；已完成 live HTTP 與契約驗證。

### 提交

- `29e6d96 docs(review): design manual test console`
- `7a21cb7 docs(review): plan manual test console`
- `bd78110 feat(review): add manual test console`
- `d710b46 fix(review): isolate demo rule selection`

## 2026-08-27 - 同步 API 契約與紀錄整理

### 已完成

- 確認 run 與 rerun 都在同一個 HTTP request 內完成，回傳內容已是 `COMPLETED` run。
- 將 `POST /api/v1/review/cases/{review_id}/runs` 與 `/rerun` 的成功狀態碼由 `202 Accepted` 改為 `200 OK`。
- 同步更新 run、rerun 與固定案件端到端測試的成功契約。
- 保留根目錄 `pytest.ini` 不變；Review 測試一律明確指定 `app/review/tests`。
- 將既有 `.sdd` brief、report、diff 與進度紀錄納入版本控制，並建立本 changelog 作為較精簡的歷史入口。

### TDD 證據

- RED：聚焦測試在 router 尚未修改時為 `10 failed, 54 passed`，失敗皆為預期 `200`、實際 `202`。
- GREEN：補齊參數化成功案例後，run、rerun 與端到端聚焦測試為 `64 passed`。
- 完整 Review suite：`141 passed, 1 warning`；唯一警告為既有 Starlette TestClient/httpx deprecation。

### 提交

- `f0c923f docs(review): define maintenance boundary`
- `fix(review): align synchronous run responses`（本次實作與紀錄提交）

## 2026-08-25 - 可信輸入與規則自動選擇

### 已完成

- 建立 `valuation.extraction_runs`、`valuation.extracted_fields` 與規則適用條件契約。
- 高影響欄位必須經人工確認；重複、未知或不可信的正式值採 fail closed。
- Review 後端依案件、日期、行政區與表型自行選擇已發布規則，不接受呼叫端指定正式值或省略必跑規則。
- run snapshot 保存文件、抽取批次、全部正式欄位、規則與法規來源的不可變稽核內容。
- rerun 保留舊 finding、舊 report 與決策歷史，並以 `supersedes_finding_id` 串接新舊結果。
- 修正 Decimal JSONB 序列化，避免信心度或規則設定造成 run 寫入失敗。

### 代表提交

- `3478aa2 docs(review): define trusted input contract`
- `b609234 docs(review): plan trusted input implementation`
- `927cab3 feat(review): add trusted extraction schema`
- `9e4a407 feat(review): define trusted input policy`
- `a9bb46f feat(review): load trusted run context`
- `f68ccf9 feat(review): require verified formal inputs`
- `e2e93a6 feat(review): execute server-selected trusted inputs`
- `1eaf9f2 test(review): verify trusted workflow history`
- `507c19f fix(review): preserve trusted audit context`
- `f6b6ef9 fix(review): snapshot every official field`
- `1152d0c fix(review): serialize snapshot decimals`

## 2026-08-25 - Review MVP 閉環

### 已完成

- 審查案件建立、佇列、分派、優先級與狀態轉換。
- 文件／欄位完整性檢查、缺件保存與補件通知待送狀態。
- 確定性 Decimal 重算、規則 finding、風險摘要與人工決策。
- 高風險核定阻擋、理由與權限檢查、append-only 決策紀錄。
- JSON 與固定模板 PDF 報告，以及 MinIO 報告 metadata 對應。
- 固定案件流程：缺件、補件、新版本、檢核、人工處理、重跑、歷史保留與完成案件。

### 代表提交

- `64bac88 docs(review): define review subsystem`
- `bb7c61c docs(review): plan review subsystem MVP`
- `4faef26 feat(review): expand review workflow schema`
- `d24464a feat(review): mount review API`
- `5f81a0f fix(review): harden run and decision boundaries`

## 目前明確延後

- Bedrock adapter 已存在，但尚未接入正式 ReviewService 流程。
- 補件只建立 `PENDING` 通知狀態，實際寄送由後續邊界決策處理。
- 正式執行器目前支援 `ADJUSTMENT_RATE` 與 `EXPERT_GRADE`；其他規則需另外設計與驗收。
- OCR、欄位抽取／校正、案件履歷分析及 RAG 問答屬其他子系統，不列為 Review 缺口。
