# Review 子系統變更紀錄

本文件只記錄 `app/review` 第二子系統。提交編號來自本分支 Git 紀錄；「已完成」僅代表已有程式與驗證證據，不包含其他子系統。

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
