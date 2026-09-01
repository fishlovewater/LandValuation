# 輔助估價與審查子系統完整整合設計

日期：2026-09-01

分支：`feature/integrate-valuation-review`

基準：`feature/review` (`f17e984`)

整合來源：`origin/feature/valuation` (`61611a5`)

## 1. 目標與已確認決策

本次整合採「一勞永逸」方案：把輔助估價的完整功能整合進 Review 現有基礎，建立一條可追溯、可重送、不可覆寫歷史的正式流程。

核心決策如下：

- `feature/review`、`origin/feature/valuation` 與 `main` 保持不變。
- 所有工作只在 `feature/integrate-valuation-review` 進行；未經明確同意不 push、不 merge。
- 共用資料表、欄位名稱、狀態及限制條件以 `origin/feature/valuation` 的最終結構為準。
- Valuation 是案件、文件、擷取、表單、計算、規則及檢核資料的權威來源。
- Review 消費 Valuation 的正式資料，但不反向修改 Valuation 的正式值。
- 送審時建立不可變的 Submission Snapshot；Review 不直接讀取會繼續變動的「最新資料」。
- PDF、圖片、附件及原始法規文件本體只存 MinIO；PostgreSQL 只保存結構化資料、metadata、object key 與雜湊值。
- 測試使用真正隔離的 PostgreSQL 資料庫及 MinIO 測試位置，完成後明確刪除並驗證零殘留，不把固定 Demo 假資料留在開發資料庫。

## 2. 範圍

### 2.1 本次包含

- 整合 `origin/feature/valuation` 的文件上傳、PDF/OCR/XLSX 擷取、AI 欄位分析、人工確認與 APPLIED 流程。
- 整合估價表單、正式 Decimal 計算、檢核、完整報告、規則包、多來源法規與適用性判斷。
- 保留 Review 現有工作台、Run、finding、決策、退回修正、重檢、報告及結案功能。
- 建立 Valuation → Review 的正式送審、退回、重送與結案邊界。
- 消除 Review 自建擷取資料表與 Valuation 權威擷取資料表的重複模型。
- 對現有 Alembic 歷史進行單一線性重編，不改寫已存在的 Review migration。

### 2.2 本次不包含

- 不在兩個原分支上改名、rebase、merge 或刪除 commit。
- 不讓 Review 直接修改 APPLIED 欄位、估價計算結果或已提交的 Snapshot。
- 不將 PDF 或圖片本體存進 PostgreSQL。
- 不在 object key 中保存固定 `localhost` URL。
- 不自動送審；送審必須由具權限的估價人員明確觸發。
- 不把 Demo seed 當成正式 migration 或長期測試資料。

## 3. 子系統責任邊界

### 3.1 `valuation.*`

負責：

- 案件與案件版本。
- 文件 metadata、版本、MinIO object key、SHA-256、ETag。
- `document_extractions`、`extracted_fields` 與 AI 輔助製作紀錄。
- 表單實例、比較標的、正式計算與 Decimal 結果。
- 規則版本、規則來源、檢核執行與原始 validation findings。
- 完整估價報告及送審 Submission。

### 3.2 `review.*`

負責：

- 審查案件佇列、分派、時限及進度。
- 針對某次 Submission 執行的 Review Run。
- 審查 finding、可讀證據、風險摘要及人工決策。
- 退回修正要求、重送後重檢及審查報告。
- 核准或退回的審查狀態與稽核紀錄。

Review 可以引用 Valuation 的 ID、版本及 Snapshot，但不能更新 Valuation 的正式內容。若需要修正，Review 只能建立 correction request，讓估價端產生新版本後再次送審。

## 4. 正式資料流程

```text
Valuation intake
→ PDF/OCR/XLSX/AI candidates
→ 人工確認
→ APPLIED fields
→ 正式 Decimal 計算與 validation
→ 估價人員明確送審
→ immutable Submission Snapshot
→ 自動建立或更新 Review queue
→ Review Run / findings / decisions
→ 核准，或退回修正
→ 新 Valuation 版本
→ 下一次 Submission
```

送審前的候選資料不具正式效力。只有 `field_status = 'APPLIED'` 且已有 `confirmed_value` 的欄位可進入正式計算與 Submission Snapshot。

## 5. 共用欄位對齊

Valuation 的命名是唯一正式命名；Review 的重複擷取模型不得保留成第二套來源。

| 意義 | 正式名稱 | 不再作為正式來源的 Review 舊名稱 |
|---|---|---|
| 文件擷取工作 | `valuation.document_extractions` | `valuation.extraction_runs` |
| 擷取工作 ID | `extraction_id` | `extraction_run_id` |
| 擷取狀態 | `extraction_status` | `status` |
| 擷取提供者 | `provider` | Review 自訂 provider/model 組合 |
| 擷取欄位 | `valuation.extracted_fields` | Review 版同名但不同結構的資料表 |
| 目標表單 | `form_code` | `field_code` 推導表單 |
| 欄位名稱 | `field_name` | `field_code` |
| 候選值 | `extracted_value` | Review 版 `value`/文字欄位 |
| 原始頁碼 | `source_page` | Review 自訂頁碼欄位 |
| 原文證據 | `source_text` | Review 自訂 evidence 欄位 |
| AI 分析來源 | `analysis_provider` | Review 自訂 model 欄位 |
| 確認狀態 | `field_status` | Review 自訂 confirmation 狀態 |
| 確認值 | `confirmed_value` | Review 自訂 normalized value |
| 確認人員 | `confirmed_by_user_id` | Review 自訂 reviewer/user 欄位 |
| 確認時間 | `confirmed_at` | Review 自訂 confirmation time |
| 套用表單 | `applied_form_instance_id` | 無等價正式欄位 |
| 套用時間 | `applied_at` | 無等價正式欄位 |

`extracted_fields` 的最終限制必須包含 Valuation 已有演進結果：

- provider 支援 `LOCAL_PDF`、`LOCAL_OCR`、`LOCAL_XLSX`、`TEXTRACT`。
- AI provenance 依 Valuation 規則保存 `analysis_provider`、`model_id`、`prompt_version`。
- 欄位唯一性是 `(extraction_id, form_code, field_name)`。
- 表單代碼包含整合分支支援的 `F01`、`F02`、`F03`、`F04`、`S01`、`F02-RF`。

## 6. Submission Snapshot

新增 `valuation.review_submissions`，第一版 schema 固定為：

| 欄位 | 型別與空值 | 用途 |
|---|---|---|
| `submission_id` | `uuid`, PK | Submission 識別碼 |
| `review_id` | `uuid`, NOT NULL, FK | 所屬 Review |
| `case_id` | `uuid`, NOT NULL, FK | 所屬 Valuation case |
| `submission_no` | `integer`, NOT NULL | 同一 Review 的送審版次 |
| `submitted_by_user_id` | `uuid`, NOT NULL, FK | 送審人員 |
| `submitted_at` | `timestamptz`, NOT NULL | 送審時間 |
| `source_validation_run_id` | `uuid`, NOT NULL, FK | 送審前的 Valuation validation run |
| `source_report_document_id` | `uuid`, NOT NULL, FK | 送審的完整報告文件版本 |
| `input_snapshot` | `jsonb`, NOT NULL | 不可變結構化輸入 |
| `input_fingerprint` | `char(64)`, NOT NULL | canonical Snapshot SHA-256 |
| `supersedes_submission_id` | `uuid`, NULL, FK | 前一次 Submission；首次送審為 NULL |
| `request_id` | `uuid`, NOT NULL | 冪等與稽核 correlation |

必要限制：

- `(review_id, submission_no)` 唯一，且 `submission_no > 0`。
- `supersedes_submission_id` 以 `(review_id, supersedes_submission_id)` 複合 FK 保證屬於同一個 Review，並指向前一次 Submission。
- `request_id` 提供送審冪等性；相同案件與 request 不得建立第二筆 Submission。
- `input_fingerprint` 是 canonical JSON 的 SHA-256；相同 Snapshot 可被識別，但不得覆寫舊資料。
- Submission 建立後，Snapshot、fingerprint、來源 run、來源報告及提交者不可更新。
- 正式環境以資料庫 trigger 阻止 Submission 的 `UPDATE`/`DELETE`；migration downgrade 與隔離測試資料庫清理不走正式應用角色。

`input_snapshot` 是結構化 JSONB，內容包含 schema version、案件版本、表單版本、APPLIED 欄位、正式 Decimal 計算結果、規則版本、validation 統計、文件 ID/版本/雜湊及必要證據索引。Decimal 以固定字串格式保存，禁止經由 float 轉換。

Snapshot 不包含 PDF/圖片 bytes，也不保存 presigned URL。原檔仍由 `source_report_document_id` 與文件 metadata 對應 MinIO。

`review.reviews` 新增 `latest_submission_id`，指向目前審查中的 Submission。首次送審先建立 Review，再建立 Submission，最後設定 `latest_submission_id`；三個動作在同一交易完成。重送沿用同一個 Review，建立下一個 Submission 並原子更新 `latest_submission_id`。

每個 Review validation run 必須保存 `submission_id`，且其 `input_snapshot` 來自該 Submission，不能在執行中回頭查詢 Valuation 的最新 APPLIED 值。既有 finding、decision、risk summary、correction request 與報告仍透過 run 保持版本範圍。

## 7. 送審 API 為何需要保留

正式端點：

```text
POST /api/v1/valuation/cases/{case_id}/submit-for-review
```

此 API 是薄的 workflow command，不是把大量估價資料從一個子系統傳到另一個子系統。Review 後續仍直接讀 PostgreSQL 的 Submission/Review 資料，PDF 仍從 MinIO 讀取，因此效能問題不在多一層 API。

API 的必要性在於它提供單一正式交易邊界：

- 驗證呼叫者是否有送審權限。
- 鎖定案件及相關版本，避免送審瞬間資料被修改。
- 驗證 APPLIED 欄位、正式計算、完整報告及 validation run 是否一致且可送審。
- 建立不可變 Snapshot 與 fingerprint。
- 首次送審時原子建立 Review queue；重送時原子建立下一版 Submission。
- 寫入 case event 與 audit correlation。
- 以 request ID 實作冪等，避免網路重試造成重複送審。

請求內容固定為：

```json
{
  "request_id": "uuid",
  "expected_case_version": 3,
  "source_validation_run_id": "uuid",
  "source_report_document_id": "uuid"
}
```

前端不得提交整包 Snapshot。服務端必須驗證兩個來源 ID 與案件版本的所有權及一致性，並在鎖內從權威資料建立 Snapshot。成功回應包含 `submission_id`、`submission_no`、`review_id`、案件狀態及時間，不回傳 MinIO object key。

## 8. 狀態與版本規則

跨子系統 handoff 固定使用以下案件狀態：

- `IN_REVIEW`：Submission 已建立，正式估價版本鎖定。
- `REVISION_REQUIRED`：Review 已退回；原 Submission 保持不可變，估價端可建立新版本。
- `REVIEW_COMPLETED`：Review 已核准並原子結案。

其中 `REVISION_REQUIRED` 是 Valuation 案件的 handoff 狀態；Review 內部沿用既有 `RETURNED_FOR_REVISION`，兩者在同一退回交易中一起更新。`IN_REVIEW` 與 `REVIEW_COMPLETED` 則是兩側共用的跨系統語意。不得在 UI 或 API 中把兩個退回狀態混為同一資料欄位。

狀態轉換：

```text
ready for submission → IN_REVIEW
IN_REVIEW → REVISION_REQUIRED
REVISION_REQUIRED → IN_REVIEW（新 Submission）
IN_REVIEW → REVIEW_COMPLETED
```

退回後只能修改新 Valuation 版本。重送會建立 `submission_no + 1`，並以 `supersedes_submission_id` 連結前一版。任何重送都不得改寫舊 Run、finding、decision、correction request、Snapshot 或報告。

Review 的機器檢核統計與人工決策維持分離：Run 的 passed/warning/failed 是不可變執行結果；人工處理不重寫歷史機器結果。只有核准才套用完整結案 gate，退回修正不強迫先為所有 finding 建立正式採用值。

## 9. Alembic 整合策略

Review 現有 migration `20260823_0001` 至 `20260830_0008` 保持原樣，`20260830_0008` 是整合分支的既有權威 head。

不能直接複製 Valuation 的 migration 檔，因為兩分支的 `0005` 至 `0008` revision ID 相同但內容不同，且 Valuation 後續 migration 的 `down_revision` 建立在其自身歷史上。整合分支改為將 Valuation 的「最終 schema 結果」重新移植到 Review `0008` 之後：

| 新 revision | 內容 | 對應 Valuation 最終演進 |
|---|---|---|
| `20260901_0009` | 權威擷取、AI 助理、OCR/XLSX provider、欄位 provenance 與最終唯一性 | 原 `0005`–`0008`、`0015`、`0016` |
| `20260901_0010` | 表單、正式計算、request correlation、完整報告與 benchmark 經緯度 | 原 `0009`、`0010`、`75dcc9441ca7` |
| `20260901_0011` | 規則包來源、多來源、草稿日期及範例文件政策 | 原 `0011`–`0014` |
| `20260901_0012` | Submission、Review handoff、狀態、run scope、FK 與索引 | 新整合設計 |

每支 migration 都以資料庫目前實際結構為前提，不以「migration 檔名相似」推斷物件存在。升級前先做 schema/constraint inventory；對 Review 已存在且語意相同的欄位予以保留，對名稱相同但結構不同的物件明確轉換或移除。

### 9.1 Review 舊擷取資料

Review `0007` 建立的 `valuation.extraction_runs` 及其版本 `valuation.extracted_fields` 不是最終權威模型。已確認目前只有 `DEMO-REVIEW-001` 使用這些資料，使用者已同意清除並以正式模型重建 Demo。

安全規則：

1. 升級前備份 PostgreSQL，並實際驗證備份可讀。
2. migration 先盤點舊表資料；若存在不屬於明確 Demo 案件的資料，立即停止，不得靜默刪除。
3. 對已確認的 Demo rows 清除相依 Review Demo 資料，再移除舊擷取表並建立 Valuation 權威表。
4. migration 不自動建立新的 Demo/fake rows。
5. 新 Demo 若仍需要，使用 development-only 明確 seed/reset 命令，且可完整刪除。

Downgrade 只保證 schema 可回退，不承諾把已移除的 Demo 候選資料還原。此限制必須在 migration docstring 與操作手冊明示。

## 10. 交易、鎖與併發

送審交易順序：

1. 以 `FOR UPDATE` 鎖定 case 及目前可送審版本。
2. 依 `expected_case_version` 防止 stale submit。
3. 驗證來源 form、calculation、validation run 與 report document 都屬於同一 case/version。
4. 從 APPLIED 權威資料建立 canonical Snapshot 及 fingerprint。
5. 首次送審建立 Review；重送鎖定既有 Review 並計算下一個 submission number。
6. 建立 Submission、更新 `latest_submission_id`、更新跨系統狀態及寫入 audit event。
7. 單一 transaction commit；任一步驟失敗則全部 rollback。

Review Run、finding 決策及核准沿用既有鎖與重驗證原則。核准時必須再次鎖定 Review，確認最新 Submission 的最新完整 Run、所有 finding、缺件及正式值 gate，然後在同一 transaction 更新 `REVIEW_COMPLETED`。

MinIO 物件先以唯一 versioned object key 上傳，驗證 SHA-256/ETag 後才寫入文件 metadata。不得覆寫既有 object；資料庫交易失敗時，補償流程只刪除本次新建且尚未被引用的物件。

## 11. 錯誤處理

- `400`：請求格式、版本選擇或 request ID 不合法。
- `401/403`：未登入或缺少送審/審查權限。
- `404`：case、來源 run、report document 或 Review 不存在，或不屬於該 case。
- `409`：案件版本過期、案件狀態不可轉換、已有不同內容的相同 request、重複決策或併發衝突。
- `422`：缺 APPLIED 欄位、validation 未完成、正式計算/報告不完整、來源版本不一致，或不符合業務送審條件。
- `500`：非預期失敗；交易 rollback，回應只提供 correlation ID，不暴露 SQL、object key、憑證或模型內部內容。

相同 `request_id` 且 payload/版本相同時回傳原成功結果；相同 `request_id` 但內容不同時回 `409`。

## 12. 權限與稽核

- 只有具 Valuation 送審權限的人可呼叫 submit API。
- Review 人員只有讀取 Snapshot/文件證據及寫入 Review 決策的權限。
- 所有送審、退回、重送、finding 決策、報告產生及結案均記錄 actor、時間、request/correlation ID、before/after 狀態與相關版本 ID。
- API 不接受 bucket/object key 作為文件授權依據；文件存取必須驗證 `review_id + submission_id + document_id` 的所有權關係。
- UI 只取得短效 presigned URL，不顯示 object key 或固定 localhost URL。

## 13. 驗證與零殘留測試

### 13.1 Migration 驗證

- 建立資料庫備份並驗證備份可讀。
- 在隔離 PostgreSQL 測試資料庫執行 `upgrade 0008 → 0012`。
- 執行 `downgrade 0012 → 0008`，再執行 `upgrade 0008 → 0012`。
- 驗證只有一個 Alembic head，revision graph 無碰撞。
- 驗證表、欄位、型別、FK、unique/check constraints、索引與 enum/status contract。
- 驗證非 Demo 舊資料會阻止具破壞性的舊擷取表清理。

### 13.2 功能與跨子系統驗證

- Valuation 單元、API 與計算測試。
- Review 單元、API、Run、決策、退回、重檢與報告測試。
- 跨子系統 E2E：upload → extraction → confirmation → APPLIED → calculation → validation → submit → Review → correction → new version → resubmit → approval → reports。
- 驗證 Snapshot/fingerprint 可重現，Decimal 無 float 漂移。
- 驗證 Review 執行期間修改 Valuation 最新草稿不影響已提交 Snapshot。
- 驗證重送保留所有歷史 Run/findings/decisions/reports。
- 驗證併發送審、重試及 stale version 不會產生重複 Submission。
- 使用真實瀏覽器完成主要工作流程，不把 Node 靜態 UI test 當成瀏覽器驗收。
- 驗證 PostgreSQL、API、MinIO health。
- 驗證每一版 MinIO object key 唯一且舊物件未被覆寫。

### 13.3 測試隔離與清理

- 使用專用 test database 名稱，不連接開發資料庫。
- 使用專用 MinIO test bucket 或不可混淆的 test prefix。
- 測試容器、資料庫、bucket/prefix 名稱帶本次 run ID。
- 測試完成後，明確刪除 test database、MinIO objects/bucket 及 test containers。
- 清理後再次查詢 PostgreSQL、MinIO 與 Docker，確認沒有本次 run ID 的殘留。
- 即使測試失敗也在 finally/teardown 執行清理；若清理失敗，整體驗收視為失敗。
- 不在 migration 或正式資料庫留下固定 Demo/fake data。

## 14. 完成條件

只有同時符合以下條件才算完成：

- 兩套功能已在整合分支運作，原分支無變更。
- 欄位及 constraint 以 Valuation 最終 schema 為準，Review 不再寫入重複擷取模型。
- Alembic 從 Review `0008` 線性升級到整合 `0012`，upgrade/downgrade/upgrade 通過。
- 送審 API 只負責 workflow command，Review 以 Submission Snapshot 與 PostgreSQL/MinIO 權威資料審查。
- 首次送審、退回、重送及核准具原子性、冪等性與完整 audit。
- 歷史 Submission、Run、finding、decision、correction request 及報告不可覆寫。
- 完整自動測試與真實瀏覽器流程通過。
- 測試資料及容器清除完畢，確認零殘留。
- 未經使用者明確同意，不 push、不 merge。
