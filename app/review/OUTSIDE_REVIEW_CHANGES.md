# Review 子系統外部變更紀錄

本文件專門記錄「估價報告自動化分析系統（子系統二）」實作期間，所有位於 `app/review/**` 以外的修改。

## 邊界規則

- 第 3 階段開始後，預設只允許修改 `app/review/**`。
- 若需修改其他路徑，必須先取得使用者明確同意。
- 每次核准及實際修改都要補記於本文件。
- 本文件本身位於 `app/review/**`，不屬於外部變更。

## 已完成的外部變更

### 1. 子系統設計文件

- 檔案：`docs/superpowers/specs/2026-08-25-review-subsystem-design.md`
- Commit：`64bac88`
- 原因：記錄子系統二的資料邊界、流程、狀態、API、安全限制與驗收原則。
- 時點：第 3 階段路徑限制生效前。
- 核准狀態：已核准。

### 2. 實作計畫

- 檔案：`docs/superpowers/plans/2026-08-25-review-subsystem-mvp.md`
- Commit：`bb7c61c`
- 原因：將已確認規格拆成可測試、可逐步提交的實作工作。
- 時點：第 3 階段路徑限制生效前。
- 核准狀態：已核准。

### 3. Review workflow 資料庫擴充

- 檔案：`migrations/versions/20260825_0005_expand_review_workflow.py`
- Commit：`4faef26`
- 原因：擴充既有 `review` 與 `valuation.validation_*` 資料表，加入案件佇列、run、finding 證據、風險、缺件及人工決策所需欄位與約束。
- 時點：第 3 階段路徑限制生效前。
- 核准狀態：已核准。

### 4. 後端套件需求

- 檔案：`requirements.txt`
- Commit：`4faef26`
- 修改：加入 `boto3>=1.35,<2.0` 與 `reportlab>=4.2,<5.0`。
- 原因：分別供 Bedrock structured explanation adapter 與固定模板 PDF 報告使用。
- 時點：第 3 階段路徑限制生效前。
- 核准狀態：已核准。

### 5. Review API 掛載

- 檔案：`app/api/router.py`
- Commit：`d24464a`
- 原因：將 `app.review.router` 掛入既有 `/api/v1` router；後續所有 review endpoints 均留在 `app/review/router.py`。
- 時點：第 3 階段路徑限制生效前的最後一次產品程式外部修改。
- 核准狀態：已核准。

## 已核准、尚未完成的外部變更

### 6. Review 狀態欄位長度修正

- 預定檔案：`migrations/versions/20260825_0006_expand_review_status_length.py`
- 發現原因：`review.reviews.review_status` 實際為 `varchar(20)`，但已確認狀態 `RETURNED_FOR_REVISION` 長度為 21，寫入時會觸發 `StringDataRightTruncation`。
- 預定修改：只將 `review.reviews.review_status` 擴為 `varchar(30)`；不刪資料、不改狀態值、不修改既有 migration。
- 回復方式：downgrade 前先檢查既有值長度；全部值不超過 20 時才縮回 `varchar(20)`，否則中止，避免資料截斷。
- 核准狀態：使用者已於 2026-08-25 明確同意新增 migration。
- 實際狀態：已建立並套用；主資料庫目前為 `20260825_0006 (head)`。
- 驗證：schema contract 已由 RED 轉為 GREEN；隔離資料庫已完成 `upgrade head → downgrade 0005 → upgrade head`，測試資料庫隨後刪除。

### 7. 可信輸入與規則自動選擇資料庫契約

- 檔案：`migrations/versions/20260825_0007_add_trusted_review_inputs.py`
- 核准狀態：使用者已於 2026-08-25 明確同意此唯一的 `app/review/**` 外變更。
- 原因：建立可追溯的正式抽取欄位與抽取批次資料契約，並支援依案件條件自動選擇規則。
- 實際狀態：已建立並套用；主資料庫目前為 `20260825_0007 (head)`。
- 驗證：隔離資料庫 `land_valuation_migration_test_0007` 已完成 `upgrade head → downgrade 0006 → upgrade head`，三個 Alembic 指令均成功並回到 `20260825_0007`；驗證後已刪除該隔離資料庫。
- 補充：`source_document_id`、其外鍵與索引原已由 `20260824_0004` 建立，`0007` 僅保留其 ownership 並新增已發布規則的來源約束。

## 範圍核對

截至目前，branch 起點 `9bcf5a0` 之後的 `app/review/**` 外變更只有上述第 1～7 項；除第 7 項已明確核准的 migration 外，其餘後續程式變更均位於 `app/review/**`。
