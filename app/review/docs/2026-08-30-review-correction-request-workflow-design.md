# Review 疑點確認、退回修正與風險報告設計

日期：2026-08-30
狀態：已完成使用者逐段確認，待書面審閱
範圍：`app/review/**` 的審核子系統設計；本文件不實作估價師端編修功能

## 1. 背景

簡報第 12 至 14 張的核心方向是：系統依文件、法規、表單與計算規則找出疑點，提供證據、風險與修正建議，由審查人員確認後交由估價師修正。

目前 Review Finding 決策仍以「維持原申報內容、採用系統建議內容、審查人員另訂正式內容」為中心，後端也會保存正式採用值。這超出審核子系統的責任。Review 應只判斷疑點、製作修正通知、接收新版並重新檢核，不應修改估價內容或代替估價師決定正式值。

## 2. 目標

1. 系統產生疑點後，審查人員必須逐項判斷疑點是否成立。
2. 只有人工確認成立的疑點可以進入修正通知單。
3. Review 不提供任何改值、選值或編輯估價報告的入口。
4. 估價師在自己的子系統修改並送回新版；Review 只驗證版本、重新檢核及保留歷史。
5. 最新版本沒有未解決事項時，仍由審查人員執行「確認無誤並完成審查」，不得自動結案。
6. 內容風險與期限緊急度分開呈現，再共同決定案件處理順序。
7. 提供 Excel 作業版與 Word 正式閱讀版風險報告。

## 3. 非目標

- 不在 Review 建立估價報告或正式欄位編輯器。
- 不由 Review 直接覆寫估價師的文件、抽取欄位或估價值。
- 不在本次設計中實作 OCR、欄位抽取或估價師端畫面。
- 不讓 AI 說明取代正式規則、法規依據或人工判定。
- 不刪除既有舊流程決策與正式採用值歷史。

## 4. 責任邊界

### 4.1 Review 可以執行

- 完整性檢查、規則檢核與風險摘要。
- 顯示原始文件、頁碼、原文、法規及計算證據。
- 讓審查人員確認疑點、排除誤判或轉專業覆核。
- 將確認成立的疑點組成不可變的修正通知內容。
- 接收估價師端送回的新版文件識別，驗證案件與版本 lineage。
- 對新版建立新 Run、比對新舊 Finding 並保留歷史。
- 由審查人員完成案件，以及匯出 Excel／Word 報告。

### 4.2 Review 不得執行

- 選擇原申報值、系統建議值或審查人員另訂值作為正式值。
- 修改正式估價值、原始報告或抽取欄位。
- 替估價師完成修正。
- 在新版檢核完成後自動結案。

## 5. 核心流程

1. Review 先做完整性檢查；缺件時維持既有阻擋行為，不建立 Run。
2. 完整後依案件條件選擇規則，建立 Run、Finding 與內容風險摘要。
3. 審查人員逐項檢視原文件、規則證據與建議修正方向。
4. 每一筆 Finding 都必須被判定為「確認有問題」、「排除誤判」或「轉專業覆核」。
5. 尚有 `OPEN` 或 `EXPERT_REVIEW` 時，不得送出修正通知或完成審查。
6. 至少有一筆確認成立的疑點時，審查人員建立並預覽修正通知單。
7. 送出後，通知內容凍結，案件轉為 `RETURNED_FOR_REVISION`，Review 工作台以唯讀方式等待新版。
8. 估價師端修改原報告或正式欄位，建立同案件且較新的文件版本並重新送審。
9. Review 驗證新版後回到 `PREPROCESSING`，重新做完整性檢查並建立新 Run。
10. 系統以既有 `supersedes_finding_id`、規則識別及文件 lineage 協助對照新舊 Finding。
11. 原疑點已消失時標示已修正；仍存在或產生新疑點時，進入下一輪人工確認及修正通知。
12. 最新版本沒有缺件、未處理疑點、確認成立但尚未修正的疑點或未完成通知單時，審查人員才可按「確認無誤並完成審查」。

## 6. Finding 人工判定

### 6.1 新流程狀態

- `OPEN`：尚未人工判定。
- `CONFIRMED_ISSUE`：人工確認問題成立，必須由估價師修正。
- `DISMISSED_FALSE_POSITIVE`：人工確認為誤判，不列入修正通知。
- `EXPERT_REVIEW`：目前無法判定，轉專業覆核並阻擋退回及結案。

人工判定理由必填，Finding 判定仍維持單次寫入與稽核軌跡；若要改判，應使用明確的管理更正流程，不得直接覆寫既有 Decision。

### 6.2 移除新建正式採用值

新流程不得接受：

- `ACCEPTED`
- `REJECTED`
- `PARTIALLY_ACCEPTED`
- 審查人員提供的 `after_value`
- `selection_source = REPORTED | SYSTEM | REVIEWER`

既有資料保留並以「舊流程歷史決策」唯讀顯示。既有 API 若收到新建舊流程決策的要求，應回傳明確的相容性錯誤，不得默默轉換語意。

## 7. 修正通知資料模型

### 7.1 `review.correction_requests`

建議欄位：

- `correction_request_id`
- `review_id`
- `request_no`：同一案件由 1 開始遞增
- `based_on_validation_run_id`
- `status`：`DRAFT`、`SENT`、`RESUBMITTED`、`RECHECKING`、`RECHECKED`
- `due_at`
- `message`
- `base_document_id`、`base_document_version`
- `response_document_id`、`response_document_version`
- `created_by_user_id`、`created_at`
- `sent_by_user_id`、`sent_at`
- `resubmitted_at`
- `rechecked_by_user_id`、`rechecked_at`

草稿可修改；轉為 `SENT` 後，案件、Run、基準文件、通知文字及項目快照均不可覆寫。後續只允許寫入生命週期狀態及新版回覆識別。

### 7.2 `review.correction_request_items`

建議欄位：

- `correction_request_item_id`
- `correction_request_id`
- `finding_id`
- `finding_code`、`finding_type`、`severity`
- `document_id`、`document_version`、`page_number`
- `reported_text`、`reported_value`
- `legal_basis_snapshot`
- `source_evidence_snapshot`
- `issue_summary`
- `requested_correction`
- `recheck_outcome`：`PENDING`、`RESOLVED`、`STILL_PRESENT`、`NOT_EVALUATED`
- `resulting_finding_id`
- `rechecked_at`

`requested_correction` 只能描述問題與應重新檢查的方向，不得保存 Review 指定的正式估價值。

### 7.3 migration 邊界

正式方案需要新增資料表及索引，因此實作時需要 Alembic migration。migration 位於 `app/review/**` 之外；在使用者明確允許修改 migration 路徑前，只能完成設計與 `app/review/**` 內的規劃，不得建立 migration。

## 8. 狀態與門檻

沿用案件主流程：

有修正事項時：

`REVIEW_REQUIRED → RETURNED_FOR_REVISION → PREPROCESSING → REVIEW_REQUIRED`

最新 Run 無待修正事項時，由人工完成：

`REVIEW_REQUIRED → REVIEW_COMPLETED`

後端可為相容既有稽核資料，在同一交易內建立 `APPROVED` Decision 後直接更新為 `REVIEW_COMPLETED`；工作台不提供分開的「核定」與「完成」兩次操作。

### 8.1 建立及送出修正通知的門檻

- 最新 Run 必須完成。
- 最新 Run 的所有 Finding 都已人工判定。
- 不得存在 `OPEN` 或 `EXPERT_REVIEW`。
- 至少存在一筆 `CONFIRMED_ISSUE`。
- 同一案件不得已有一張 `SENT`、`RESUBMITTED` 或 `RECHECKING` 的未完成通知單。

### 8.2 完成審查的門檻

- 最新 Run 必須完成。
- 沒有未解決缺件。
- 沒有 `OPEN`、`CONFIRMED_ISSUE` 或 `EXPERT_REVIEW`。
- 不得存在 `SENT`、`RESUBMITTED` 或 `RECHECKING` 通知單。
- 任何已送出的修正通知都已完成新版重檢並成為 `RECHECKED`。`RECHECKED` 只代表該輪檢核完成；是否真正修正成功由各 item 的 `recheck_outcome` 表示。
- 完成動作由審查人員明確觸發，後端鎖定案件、重新驗證全部門檻、建立完成 Decision 並在同一交易更新為 `REVIEW_COMPLETED`。

## 9. 期限緊急度與排序

內容風險與期限緊急度是兩個不同概念：

- 內容風險：依 Finding 類型與嚴重度計算。
- 期限緊急度：依案件 `due_at` 與目前日期動態計算。

預設門檻：

- 已超過 `due_at`：`OVERDUE`
- 剩餘 0 至 3 天：`URGENT`
- 剩餘 4 至 7 天：`DUE_SOON`
- 剩餘 8 天以上：`NORMAL`
- 沒有截止日：`NOT_SET`

新增管理設定：

- `urgent_days = 3`
- `due_soon_days = 7`
- `updated_by_user_id`
- `updated_at`

必須驗證 `0 <= urgent_days < due_soon_days`。緊急度與剩餘天數在查詢時依設定計算，不回寫案件，因此日期跨日後會自動更新。

預設案件排序：

1. 人工置頂或人工優先度。
2. 已逾期與期限緊急度。
3. 高風險、再中風險疑點數。
4. 剩餘天數。
5. 收件時間。

## 10. API 設計

API 名稱可在實作計畫中依既有 router 慣例微調，但語意必須保持：

- `POST /findings/{finding_id}/triage`：建立人工判定，不接受正式採用值。
- `POST /cases/{review_id}/correction-requests`：依最新 Run 建立草稿，伺服器選取已確認疑點並建立快照。
- `GET /correction-requests/{id}`：讀取通知與項目。
- `POST /correction-requests/{id}/send`：鎖定、重驗門檻、凍結內容並將案件退回。
- `POST /correction-requests/{id}/resubmissions`：由授權的估價師端或整合服務登記新版文件識別。
- `POST /cases/{review_id}/recheck`：驗證新版、完整性檢查並建立新 Run。
- `POST /cases/{review_id}/complete-review`：後端原子驗證及完成審查。
- `GET /review-settings/urgency`、`PUT /review-settings/urgency`：讀取及由管理員更新期限門檻。
- `POST /runs/{run_id}/reports`：依格式產生 `xlsx` 或 `docx` 快照報告。

所有寫入 API 都要沿用 JWT、RBAC、request ID、案件鎖定及單次決策防重複機制。跨子系統送回新版時，必須驗證文件屬於同一案件、版本高於基準版本、lineage 正確，且不得接受 bucket、object key 或任意網址作為業務輸入。

## 11. 工作台設計

案件清單同時顯示：

- 內容風險。
- 截止日期、剩餘天數與期限緊急度。
- 目前流程狀態與修正輪次。

案件詳情使用四個業務頁籤：

1. `檢核結果`：PDF 對照、原文、法規、系統結果、問題與建議修正方向，以及三個人工判定動作。
2. `修正通知`：顯示已確認成立的疑點、通知文字、期限、預覽與送出。
3. `新版重檢`：顯示舊版／新版文件、原疑點是否解決、新疑點及重新檢核動作。
4. `報告與歷程`：顯示每次 Run、通知、送回、重檢、完成紀錄及 Excel／Word 匯出。

當案件為 `RETURNED_FOR_REVISION` 時，Review 端不得顯示任何改值或修改報告控制，只顯示等待新版、通知內容及歷史。

## 12. 報告輸出

### 12.1 Excel 作業版

一個 `.xlsx` 包含：

1. `案件摘要`：案號、估價師、截止日期、剩餘天數、內容風險、期限緊急度、文件版本、Run、疑點數及修正輪次。
2. `疑點與修正要求`：每筆確認成立疑點一列，包含頁碼、原始內容、法規、問題、建議修正方向、期限及狀態。
3. `新版重檢結果`：新舊文件版本、原疑點是否消失、對應新舊 Finding 及重檢時間。
4. `審查歷程`：通知、退回、重新送件、重新檢核及結案的操作人、時間與理由。

Excel 不含巨集，不使用公式產生正式估價值。

### 12.2 Word 正式閱讀版

一個 `.docx` 依序包含：

- 案件基本資料與審查範圍。
- 整體內容風險與期限緊急度。
- 文件、法規及規則版本。
- 逐項確認成立的疑點與證據。
- 發給估價師的修正要求。
- 各次送回與新版重檢結果。
- 最終審查結論及人工完成紀錄。

AI 說明若存在，必須明確標為輔助說明並保留來源引用；不得把 AI 建議描述成正式法規結論或正式估價值。

### 12.3 報告不可變性與儲存

- 修正通知可在送出時產生一版 Excel／Word。
- 最終風險報告只在完成審查後產生，包含完整修正循環。
- 報告必須綁定指定案件、Run、通知單與文件版本快照，不得查詢「目前最新」資料後回填歷史報告。
- PostgreSQL 保存報告 metadata、版本、checksum、bucket 與 object key。
- MinIO 保存 `.xlsx`、`.docx` 及其他大型檔案本體。
- API 不得向前端暴露 MinIO object key，也不得將 object key 存成固定 localhost URL。

## 13. 錯誤處理與不變條件

後端必須拒絕：

- 尚有 `OPEN` 或 `EXPERT_REVIEW` 卻送出修正通知。
- 沒有 `CONFIRMED_ISSUE` 卻退回修正。
- 前端指定不屬於最新 Run 的 Finding 作為通知項目。
- 通知送出後修改其問題、證據或修正要求快照。
- 重複送出同一通知或重複接收同一文件版本。
- 使用其他案件、相同版本、較舊版本或錯誤 lineage 的文件作為新版。
- 新版尚未完成完整性檢查及 Run 就完成審查。
- 報告混入其他案件、其他 Run 或後續版本資料。
- 新流程傳入正式採用值或選值來源。

所有重複請求應以 request ID 或資料庫唯一限制得到確定且可稽核的結果；不得因重試建立兩張通知或兩次結案紀錄。

## 14. 相容性

- 舊 `ACCEPTED`、`REJECTED`、`PARTIALLY_ACCEPTED`、`after_value` 及 `selection_source` 必須可讀。
- 舊報告仍依原 Run 快照產生或下載，不回寫成新語意。
- 新工作台以清楚標籤顯示「舊流程歷史決策」，不提供複製或重新送出舊決策的按鈕。
- 現有 `RETURNED_FOR_REVISION`、rerun、Finding supersedes、PDF 預覽、MinIO 報告保存與原子完成基礎應重用，不另建重複子系統。

## 15. 測試與驗收

### 15.1 後端測試

- Finding 人工判定合法值、理由必填、單次寫入及舊值拒絕。
- 修正通知建立、快照內容、送出門檻、凍結及重複請求。
- 新版案件 ownership、版本遞增、lineage 及重複送件驗證。
- 重新檢核保留舊 Run、Finding、Decision、通知與報告。
- 新舊 Finding 對照及每個修正項目的重檢結果。
- 完成門檻、案件鎖定及單一交易。
- 緊急度門檻設定、跨日計算、排序及無截止日期案例。
- Excel／Word 報告的工作表、章節、欄位、快照範圍及 MinIO metadata。
- 權限、跨案件存取、物件儲存資訊洩漏及 request ID 冪等性。

### 15.2 工作台測試

- 不存在選值、改值或正式採用內容欄位。
- 每筆 Finding 可確認、排除或轉專業覆核，且錯誤原因可讀。
- 未完成判定時按鈕正確阻擋並說明原因。
- 送出後畫面唯讀並顯示等待新版。
- 新版重檢清楚呈現已修正、仍存在及新增疑點。
- 內容風險與期限緊急度分開顯示，案件順序符合規則。
- Excel／Word 匯出入口只在允許的階段啟用。

最終驗收必須包含完整後端測試與實際瀏覽器流程；靜態 Node 測試不得宣稱為瀏覽器驗收。

## 16. 成功定義

設計完成後，Review 的產品語意必須可以用一句話說明：

> Review 找出問題、提供證據並形成修正通知；估價師修改原報告；Review 對新版重新檢核並由審查人員完成審查。

任何需要審查人員選擇或輸入正式估價值的流程，都不符合本設計。
