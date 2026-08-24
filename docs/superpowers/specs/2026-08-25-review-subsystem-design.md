# 估價報告自動化分析子系統設計規格

## 目標

在既有 PostgreSQL、MinIO、FastAPI、JWT/RBAC 與 Alembic 基礎上，建立供審查人員使用的估價報告自動化分析後端。系統負責整理來源、判斷缺件、執行可重現的規則檢核與重算、產生可追溯疑點及風險摘要，並保存人工決策；AI 不得取代正式計算或最終核定。

第一個可驗收版本以一個固定案件完成以下閉環：建立待審案件、發現缺件、補件建立新版本、執行規則檢核、產生高／中風險疑點、人工部分接受、修改後重跑、保留舊結果並完成案件。

## 既有資料模型對應

不新增功能重複的 `review_cases` 或 `review_runs`。

- `review.reviews`：待審案件及整個人工審查生命週期。擴充收件日、期限、指派人、人工優先級、案件處理狀態、風險統計及最新檢核 run。
- `valuation.validation_runs`：每次不可覆蓋的機器檢核 run。擴充所屬 `review_id`、輸入快照、規則版本快照、模型及 prompt 版本、執行錯誤資訊。
- `valuation.validation_findings`：不可變的規則引擎證據，保存實際值、預期值、規則及嚴重度，不保存人工處理狀態。
- `review.findings`：審查人員看到及處理的疑點。保存來源位置、原始證據、報告原內容、法規依據、優劣結果、修正率結果、比較結果、建議動作、AI 理由摘要及處理狀態。
- `review.decisions`：人工決策的唯一權威來源，保存決策類型、理由、修改前後內容、操作者、request ID 及時間。
- `review.missing_items`：缺件與補件狀態，保存影響規則、期限、通知狀態及補正文件版本。
- `review.risk_summaries`：每個 run 的風險統計與原因；案件目前風險由最新未解決疑點計算，不由 AI 自由決定。

舊文件、舊 run、舊 finding、舊風險摘要及舊決策均不可覆蓋或連帶刪除。

## 模組邊界

第 3 步建立以下結構：

```text
app/review/
├── router.py
├── models.py
├── schemas.py
├── repository.py
├── service.py
├── sorting.py
├── completeness.py
├── rule_selection.py
├── recalculation.py
├── risks.py
├── decisions.py
├── reports.py
└── tests/
```

各檔案責任如下：

- `router.py`：`/api/v1/review` HTTP 介面、權限 dependency 及狀態碼。
- `models.py`：本子系統需要的 SQLAlchemy table mapping；不得建立第二套 engine 或 session。
- `schemas.py`：Pydantic 請求、回應及 finding 的 10 項資訊結構。
- `repository.py`：所有 PostgreSQL 查詢與寫入，接受既有 `AsyncSession`。
- `service.py`：審查案件狀態機及整體流程協調。
- `sorting.py`：逾期、剩餘天數及人工優先級排序。
- `completeness.py`：必要文件與欄位缺件判斷。
- `rule_selection.py`：依案件、地區、日期與表型選擇已發布規則版本。
- `recalculation.py`：Decimal 優劣、修正率與價格重算；不得呼叫語言模型做正式計算。
- `risks.py`：硬性風險條件、疑點數與案件風險摘要。
- `decisions.py`：疑點及案件層級人工決策、理由與狀態轉換。
- `reports.py`：結構化 JSON 報告；PDF 為後續同模組內的固定模板輸出。

建立 `app/review` 時，允許一次修改 `app/api/router.py` 掛載 review router。此後若需修改 `app/review/**` 以外的任何檔案，必須先取得使用者同意。測試固定放在 `app/review/tests/**`。

## 資料流程

1. 審查人員建立或匯入待審案件，設定收件日、期限與負責人。
2. 系統從 PostgreSQL 取得案件及文件 metadata，透過既有 storage service 讀取 MinIO 文件。
3. 每個標準化值保存原始值、文件 ID、邏輯文件版本、頁碼及欄位路徑；沒有來源的 AI 推測不得成為正式證據。
4. 完整性檢查先執行。缺少核心資料時建立 `missing_item`，案件進入待補件，依賴該資料的正式重算不執行。
5. 資料完整時建立新的 `validation_run` 與輸入快照，選擇有效規則版本，執行確定性檢核及 Decimal 重算。
6. 規則證據先寫入 `valuation.validation_findings`，再建立可供人工處理的 `review.findings`。
7. AI 僅根據已驗證的 evidence ID 與法規來源，補充結構化說明、建議與信心；AI 失敗不影響規則 finding。
8. 風險服務依未解決疑點最高嚴重度及硬性條件產生摘要。
9. 人工決策新增至 `review.decisions`，不修改 AI 原建議或機器證據。
10. 補件或修改後建立新文件版本及新 run；新 finding 可指向被取代的舊 finding。

## API 第一階段

第一階段先完成：

```text
POST  /api/v1/review/cases
GET   /api/v1/review/cases
GET   /api/v1/review/cases/{review_id}
PATCH /api/v1/review/cases/{review_id}
POST  /api/v1/review/cases/{review_id}/assign
POST  /api/v1/review/cases/{review_id}/priority
```

列表支援案件編號、審查人員、狀態、風險、待補件、期限區間、逾期、分頁及排序。預設排序鍵為：人工優先級降冪、逾期優先、高風險數降冪、中風險數降冪、剩餘天數升冪、收件時間升冪。

後續 API 依完整性、run、finding、人工決策、重跑及報告順序加入，但路徑均保持在 `/api/v1/review`。

## 狀態與錯誤

案件主要狀態為：

```text
RECEIVED
PREPROCESSING
PENDING_MATERIALS
READY_FOR_REVIEW
ANALYZING
REVIEW_REQUIRED
RETURNED_FOR_REVISION
SUPPLEMENT_REQUIRED
EXPERT_REVIEW
APPROVED
REVIEW_COMPLETED
```

- 同一 review 不可同時存在兩個執行中的 run，衝突回傳 `409`。
- 未登入回傳 `401`；沒有審查權限回傳 `403`；找不到資源回傳 `404`；輸入錯誤回傳 `422`。
- Bedrock 或檢索不可用時回傳或記錄 `503`，但已完成的規則 finding 必須保留並可查閱。
- 所有錯誤沿用既有統一格式與 request ID。
- 所有寫入沿用既有 request-scoped `AsyncSession`，失敗由共用 session rollback。

## 儲存與安全

- PostgreSQL 只保存結構化資料、metadata、法規文字及向量。
- PDF、圖片、附件、原始法規與產生的檢核報告只存 MinIO。
- bucket 固定為 `land-valuation`；object key 使用 `cases/` 或 `knowledge/` 前綴，不保存 endpoint、localhost URL 或長效下載網址。
- 前端不可直接連線 MinIO。
- 法規文件必須同時為 `extraction_status = COMPLETED` 與 `publication_status = PUBLISHED` 才可成為正式檢索來源。
- AI 不可捏造法規、頁碼或數字，不可保存隱藏思考過程，不可自行核定案件。
- 個資、AWS Key、密碼與 `.env` 不得寫入程式、migration、一般日誌或 Git。

## Migration 規則

- 只新增 `20260825_0005` 之後的新 revision，不修改或刪除 `0001`～`0004`。
- 正式 schema 以 Alembic 為權威；不更新歷史 `database/init` SQL。
- 升級前檢查既有 constraint、舊資料與命名，遇到可能資料遺失時中止。
- 所有新增可查詢、需約束的主要欄位使用正式欄位；JSONB 只保存證據、快照及顯示結構。
- 金額、比例與修正率使用 PostgreSQL `numeric` 及 Python `Decimal`。

## 測試與驗收

所有新測試放在 `app/review/tests/**`，遵循先失敗、再最小實作、最後全量回歸的 TDD 流程。

測試至少涵蓋：

- 案件排序、期限及逾期判斷。
- Decimal 修正率與價格重算。
- 優劣級距及風險分級。
- 缺件判斷與依賴規則阻擋。
- 案件狀態轉換與非法轉換。
- `401`、`403`、`404`、`409`、`422`、`503`。
- 跨案件 document、finding、decision ID 拒絕。
- 同一案件只能有一個執行中 run。
- 新 run 不覆蓋舊 run、finding 或 decision。
- AI 原建議與人工決策分開保存。
- Bedrock 失敗時規則 finding 仍可查閱。

第一個端到端驗收必須證明：固定案件缺件後進入待補件；補件建立新版本後完成檢核；產生至少一筆高風險及一筆中風險疑點；人工部分接受並輸入理由；修改後建立新 run；舊結果保留且新結果顯示問題已解決。

## 明確不做

- 不建立 Vue。
- 不另建 PostgreSQL engine、MinIO client、登入、案件主檔或錯誤格式。
- 不一次支援全部土地類型、法規、F01～F04 因素與公式。
- 不做在線模型訓練、自動更新規則、多人協作鎖定或跨案件統計儀表板。
- 不讀寫黑客鬆階段保留的 `valuation.valuations` 摘要表。
- 不刪除 volume，不直接在共用資料庫手動執行 DDL。
