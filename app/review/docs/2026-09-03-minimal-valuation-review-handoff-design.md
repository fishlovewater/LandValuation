# Valuation → Review 最小可跑通送審設計

日期：2026-09-03

分支：`feature/integrate-valuation-review`

## 1. 目標

以既有 Valuation 與 Review 功能為基礎，完成一條可由人工實際操作的最小正式流程：

```text
估價人員完成正式資料
→ 明確送審
→ 建立不可變 Submission Snapshot 與 Review 案件
→ 審查人員登入後在待審清單看到案件
→ 開啟送審資料、執行檢核並處理疑點
→ 核准或退回
```

第一版以「首次送審可完整審查」為完成條件，不擴充新的多版本比較 UI、自動送審、通知或跨系統協作功能。

## 2. 責任邊界

- Valuation 是 APPLIED 欄位、正式 Decimal 計算、validation run、完整報告與原始文件的權威來源。
- Review 只讀取送審當下的 Submission Snapshot，不修改 Valuation 的正式內容。
- PDF、圖片與報告本體保存在 MinIO；PostgreSQL 只保存 metadata、object key、雜湊與結構化 Snapshot。
- Review 的 Run 統計保持不可變；人工疑點處理與機器檢核結果分開顯示。

## 3. 最小送審 API

恢復既有端點：

```text
POST /api/v1/valuation/cases/{case_id}/submit-for-review
```

請求只包含：

```json
{
  "request_id": "uuid",
  "expected_case_version": 3,
  "source_validation_run_id": "uuid",
  "source_report_document_id": "uuid"
}
```

伺服器必須在單一交易中：

1. 驗證呼叫者具 Valuation 送審權限。
2. 鎖定案件並驗證 `expected_case_version`。
3. 驗證 validation run、完整報告及 APPLIED 欄位都屬於相同案件與版本。
4. 由伺服器建立 canonical Snapshot 與 SHA-256 fingerprint。
5. 建立第一筆 `valuation.review_submissions`。
6. 建立或連結一筆 `review.reviews`，並設定 `latest_submission_id`。
7. 將案件狀態改為 `IN_REVIEW`。

相同 `request_id` 與相同內容重試時回傳原成功結果；相同 `request_id` 但內容不同時回應 `409`。前端不得直接提交 Snapshot、bucket、object key 或 presigned URL。

## 4. Review 讀取流程

- Review 待審清單顯示新建的 Review 案件。
- 案件明細以 `latest_submission_id` 取得 Submission Snapshot、來源文件及送審版本。
- Review 的正式檢核輸入來自 Snapshot；開啟案件時不得再查詢已移除的 `valuation.extraction_runs`，也不得讀取送審後的新草稿值。
- Review Demo seed、reset、revise 與工作台查詢全面使用 canonical `valuation.document_extractions`、`valuation.extracted_fields.extraction_id`、`form_code`、`field_name`、`confirmed_value`、`field_status`。

## 5. 核准與退回

- 審查人員沿用現有 Review Run、finding、triage、decision、correction request 與報告流程。
- 核准時沿用既有完整 gate，並原子更新 Review 與案件為 `REVIEW_COMPLETED`。
- 退回時建立 correction request，Review 使用 `RETURNED_FOR_REVISION`，Valuation 案件使用 `REVISION_REQUIRED`。
- 第一版不新增重送 UI；資料表保留 `submission_no` 與 `supersedes_submission_id`，後續可在不改寫第一版歷史的前提下擴充。

## 6. 權限與文件介面

- 隔離測試與正式 runtime role 必須具有 Review 與所需 Valuation schema/table/sequence 的最小讀寫權限。
- migration owner 不屬於 runtime group，必須能執行 upgrade、downgrade 與測試清理。
- 恢復 Valuation 既有客製 Swagger JSON 編輯器，且自訂 `/docs` route 不出現在 OpenAPI schema。
- Submission 欄位只有在 runtime API 可建立並供 Review 讀取後才保留在公開 response schema。

## 7. 錯誤處理

- `401/403`：未登入或缺少送審／審查權限。
- `404`：案件、validation run、報告或 Review 不存在，或不屬於同一案件。
- `409`：版本過期、案件狀態衝突、request ID 衝突或重複送審。
- `422`：缺少 APPLIED 欄位、正式計算、完成的 validation run 或完整報告。
- 任一步驟失敗時整筆送審交易 rollback，不留下孤立 Submission 或 Review。

## 8. TDD 與驗收

實作順序固定為：先新增或調整會失敗的測試、確認失敗原因正確，再做最小修正並重跑。

自動驗收至少包含：

1. Review 工作台與 Demo 不再引用 legacy extraction schema。
2. runtime role 可執行 Review 正常流程，但不能改寫 Submission。
3. Valuation 客製 Swagger 測試通過。
4. migration 測試可整套執行，測試間不因 downgrade 污染後續案例。
5. APPRAISER 可首次送審，重試具冪等性，過期版本與跨案件來源會被拒絕。
6. REVIEWER 登入後可在待審清單看到該案件，明細內容等於送審 Snapshot。
7. 送審後修改 Valuation 草稿不影響 Review 的既有輸入。
8. Review 可完成 Run、疑點處理及核准或退回。
9. Valuation、Review、integration 與 Node UI 全套測試通過。
10. 隔離 PostgreSQL、MinIO、容器與網路在測試後零殘留。

自動測試通過後，使用兩個真實角色完成瀏覽器人工驗收；Node 靜態 UI 測試不能代替瀏覽器驗收。

本次最小 handoff 的實作驗證紀錄：

- 公開送審端點為 `POST /api/v1/valuation/cases/{case_id}/submit-for-review`。
- 資料庫 migration head 為 `20260904_0014`；`0014` 以明確檢查既有重複資料後，
  強制每個估價案件只有一筆 Review 工作流。
- 可執行的跨模組驗收測試為
  `tests/integration/test_valuation_review_handoff.py`；路由共存檢查在
  `tests/test_integration_surface.py`。
- 首次送審後的退回／重送流程仍刻意不提供重送 UI；本次只驗證退回狀態與既有
  `submission_no`／`supersedes_submission_id` 延伸邊界。
- 本文件不宣稱瀏覽器驗收；瀏覽器角色流程仍由使用者依 APPRAISER／REVIEWER
  checklist 親自確認。

## 9. 非目標

- 不新增自動送審、通知、批次送審或新的前端框架。
- 不重新設計 Valuation 或 Review 已有工作台。
- 不在本次新增完整重送 UI 或歷史版本比較 UI。
- 不把 Demo seed 當成 migration 或正式資料。
- 不 push、不 merge，也不修改 `feature/review` 或 `origin/feature/valuation`。

## 10. 完成條件

只有在全套自動測試通過、送審交易可建立不可變 Snapshot、Review 實際能讀取並審查同一筆送審資料、測試資源零殘留後，才交由使用者進行最後人工測試。
