# 子系統二可信輸入與規則自動選擇設計

## 1. 目的

目前 review run 已能驗證案件文件存在、文件版本正確，以及規則版本已發布且在估價基準日有效；但是報告值、原文、頁碼、欄位路徑與要執行的規則仍由 API 呼叫端提供。這只能證明文件屬於案件，不能證明送入檢核的值真的來自該文件，也不能防止呼叫端省略必跑規則。

本次變更建立兩個可信邊界：

1. 子系統二只讀取 PostgreSQL 中已完成抽取、具有來源定位的正式欄位，不接受呼叫端提交報告值或證據。
2. 子系統二依案件條件自行選擇規則版本並枚舉所有必跑規則，不接受呼叫端指定規則 ID。

這是既有子系統二規格中「欄位標準化並保留來源」及「依案件類型、地區、日期與表型選擇規則」的落地，不新增文件抽取服務本身。

## 2. 已確認決策

- 採混合確認模式：高影響欄位必須人工確認；低影響欄位通過抽取與格式驗證後即可使用。
- 高影響欄位未確認時，案件停在 `PENDING_MATERIALS`，不得建立正式 validation run。
- 抽取資料由上游文件抽取子系統寫入；`app/review` 只有讀取權責，不提供抽取結果寫入 API。
- migration `0007` 建立可信抽取資料契約，並新增規則的案件類型、行政區、優先序及已發布規則的正式法規來源約束；正式法規來源的 `source_document_id`、外鍵與索引已由 `0004` 建立，`0007` 保留該 ownership。
- `valuation.validation_rules.target_form_code` 已能表示 F01 至 F04，不新增重複的表型欄位。
- 除核准新增的 `0007` 外，程式與文件修改均限制在 `app/review/**`。

## 3. 非目標

- 不建立 OCR、Textract、LLM 抽取或人工校正 API。
- 不修改 MinIO object key 或儲存規則。
- 不修改既有 `0005`、`0006` migration。
- 不自動替既有規則建立假的法規來源或發布狀態。
- 不將 PDF、圖片或大型附件寫入 PostgreSQL。
- 不擴充前端。

## 4. 資料模型

### 4.1 `valuation.extraction_runs`

每一列代表特定案件文件版本的一次抽取批次。

| 欄位 | 型別與限制 | 用途 |
|---|---|---|
| `extraction_run_id` | UUID PK | 抽取批次識別 |
| `case_id` | UUID NOT NULL | 所屬案件 |
| `document_id` | UUID NOT NULL | `valuation.documents` 來源文件 |
| `document_version` | integer > 0 | 抽取時的文件版本 |
| `run_no` | integer > 0 | 同一文件版本的抽取序號 |
| `status` | varchar | `PENDING / PROCESSING / COMPLETED / FAILED` |
| `extractor_name` | varchar NOT NULL | 抽取器名稱 |
| `extractor_version` | varchar NULL | 抽取器版本 |
| `started_at` | timestamptz | 開始時間 |
| `completed_at` | timestamptz NULL | 完成時間 |
| `error_code` | varchar NULL | 失敗代碼 |
| `error_message` | text NULL | 失敗原因 |

主要限制：

- `(case_id, document_id)` 外鍵連到 `valuation.documents(case_id, document_id)`。
- `(document_id, document_version, run_no)` 唯一。
- `COMPLETED` 必須有 `completed_at` 且不得有錯誤欄位。
- `FAILED` 必須有 `completed_at` 與非空白 `error_code`。
- 子系統二只讀取指定文件版本最新的 `COMPLETED` 批次。

### 4.2 `valuation.extracted_fields`

每一列代表抽取批次中的一個標準化欄位及其來源定位。

| 欄位 | 型別與限制 | 用途 |
|---|---|---|
| `extracted_field_id` | UUID PK | 欄位識別 |
| `extraction_run_id` | UUID NOT NULL | 所屬抽取批次 |
| `field_code` | varchar NOT NULL | 標準欄位代碼 |
| `field_path` | varchar NOT NULL | 陣列或巢狀位置 |
| `value_type` | varchar | `DECIMAL / TEXT / DATE / BOOLEAN / JSON` |
| `raw_text` | text NOT NULL | 文件原文 |
| `normalized_value` | jsonb NOT NULL | 正規化值，保留資料型別 |
| `page_number` | integer > 0 | PDF 頁碼 |
| `bounding_box` | jsonb NULL | 頁面來源座標 |
| `confidence` | numeric 0 至 1 | 抽取信心值 |
| `verification_status` | varchar | `AUTO_EXTRACTED / VERIFIED / REJECTED` |
| `verified_by_user_id` | UUID NULL | 確認人員 |
| `verified_at` | timestamptz NULL | 確認時間 |
| `is_official` | boolean | 是否為該批次正式採用值 |
| `created_at` | timestamptz | 建立時間 |

主要限制：

- 外鍵以 `ON DELETE RESTRICT` 連到 `valuation.extraction_runs`，避免正式來源被刪除而破壞追溯。
- 同一抽取批次的 `(field_code, field_path)` 唯一。
- `VERIFIED` 必須同時保存 `verified_by_user_id` 與 `verified_at`。
- `AUTO_EXTRACTED` 與 `REJECTED` 不得假裝具有人工確認人及時間。
- `REJECTED` 不得設為 `is_official = true`。
- `normalized_value`、`raw_text`、頁碼與來源定位均由上游抽取流程保存，review API 不提供修改路徑。

### 4.3 高影響欄位政策

`app/review/trusted_inputs.py` 保存子系統二目前支援欄位的最低確認要求。MVP 高影響欄位包含：

- 調整率與修正率。
- 比較價格與重算價格。
- 最終估值。
- 評價級距。
- 法規依據欄位。

高影響欄位只有 `VERIFIED + is_official` 可使用。低影響欄位接受 `AUTO_EXTRACTED` 或 `VERIFIED`，但仍必須是 `is_official`，且來源批次為 `COMPLETED`。

欄位未達最低確認要求時，完整性檢查建立缺失項目；正式 run endpoint 仍會再次檢查，避免繞過完整性流程。

### 4.4 規則版本擴充

`0004` 已在 `valuation.rule_versions` 建立正式法規來源的 `source_document_id`、外鍵與索引；`0007` 保留該 ownership，並新增：

| 欄位 | 型別與限制 | 用途 |
|---|---|---|
| `applicable_case_type` | varchar NULL | NULL 表示全部案件類型 |
| `applicable_district_code` | varchar NULL | NULL 表示全部行政區 |
| `selection_priority` | integer >= 0 | 多筆候選規則版本的選擇優先序 |
| `source_document_id` | UUID | 正式法規來源，連到 `knowledge.documents`；由 `0004` 建立，`0007` 僅以約束使用它 |

`source_document_id` 的欄位、外鍵與索引由 `0004` 建立；`0007` 新增約束，要求 `PUBLISHED` 規則版本必須具有該來源。Migration 套用前若發現現有 `PUBLISHED` 規則版本沒有來源，必須失敗並列出原因，不得自動填入假資料或靜默降級狀態。

規則來源文件必須同時符合：

- `knowledge.documents.extraction_status = COMPLETED`
- `knowledge.documents.publication_status = PUBLISHED`
- 文件有效日期涵蓋案件估價基準日，若文件未設定有效日期則不額外限制。

## 5. 規則自動選擇

後端從案件與資料庫取得以下選擇條件：

- `valuation.cases.case_type`
- `valuation.cases.district_code`
- `valuation.cases.valuation_base_date`
- 本案 `valuation.form_instances` 中狀態不是 `VOID` 的 F01 至 F04 表型

候選規則版本必須：

1. 狀態為 `PUBLISHED`。
2. 規則版本有效日期涵蓋估價基準日。
3. `applicable_case_type` 為 NULL 或等於案件類型。
4. `applicable_district_code` 為 NULL 或等於案件行政區。
5. 法規來源文件可用。

符合條件後選擇最高 `selection_priority`。若最高優先序有多筆，回傳 `RULE_SELECTION_CONFLICT`，不自行猜測。

選定版本後，後端列出該版本下所有 `is_active = true`，且 `target_form_code` 為 NULL 或存在於本案表型集合的 validation rules。這個集合即為必跑規則，呼叫端無法刪除、增加或替換。

## 6. API 契約

正式檢核與重新檢核都不再接受報告值、頁碼、證據或規則 ID：

```http
POST /api/v1/review/cases/{review_id}/runs
Content-Type: application/json

{}
```

```http
POST /api/v1/review/cases/{review_id}/rerun
Content-Type: application/json

{}
```

`RunCreate` 使用 `extra = forbid` 的空請求模型。傳入 `reported_rate`、`reported_grade`、`reported_text`、`field_path`、頁碼、document ID、rule version ID、validation rule ID、證據或法律依據均回傳 `422`。

## 7. 正式執行流程

1. 鎖定 review，確認案件狀態可執行且沒有進行中的 run。
2. 取得案件最新版、有效的 `original` 估價報告。
3. 取得相同文件與版本最新的 `COMPLETED` extraction run。
4. 讀取該批次所有 `is_official` 欄位並套用高低影響確認政策。
5. 取得案件類型、行政區、估價基準日及有效表型。
6. 自動選擇唯一適用的規則版本。
7. 驗證法規來源文件的抽取、發布與有效日期。
8. 枚舉全部必跑 validation rules，並確認每條規則所需的 `target_field_code` 有可信正式值。
9. 在所有 preflight 檢查成功後，才將 review 轉為 `ANALYZING` 並建立 run。
10. 執行確定性重算與比較，產生 findings 與 risk summary。
11. 保存不可變 input snapshot，完成 run 並將 review 轉為 `REVIEW_REQUIRED`。

任何 preflight 失敗都不得建立零檢核、零疑點、LOW 的成功 run。

## 8. 快照與證據

Run input snapshot 至少保存：

- 案件 ID。
- 文件 ID、版本、document group 與 SHA-256。
- extraction run ID、抽取器名稱及版本。
- 每個正式欄位的 ID、field code/path、原文、標準化值、頁碼、確認狀態及確認人。
- 自動選出的規則版本與全部實際執行的 validation rule ID。
- 法規來源文件 ID、版本及 SHA-256。

Finding 的 `source_evidence` 只由 extracted field 組成，不再從 API payload 組裝。Finding 的 `legal_basis` 只由規則版本、validation rule 與正式 knowledge document 組成。

同一舊 run 的 snapshot、finding 與 risk summary 不會因文件重抽取、欄位重新確認或規則更新而改變。

## 9. 錯誤處理

| 錯誤碼 | 條件 |
|---|---|
| `TRUSTED_INPUT_MISSING` | 沒有最新版原始文件、完成的抽取批次或正式採用值 |
| `TRUSTED_INPUT_UNVERIFIED` | 必要高影響欄位未人工確認 |
| `RULE_SELECTION_REQUIRED` | 沒有適用規則版本 |
| `RULE_SELECTION_CONFLICT` | 最高優先序有多筆規則版本 |
| `RULE_SOURCE_UNAVAILABLE` | 法規來源文件未完成抽取、未發布或日期不適用 |
| `REQUIRED_RULE_INPUT_MISSING` | 必跑規則缺少對應可信欄位 |

上述錯誤均發生在建立 run 之前，review 保持原狀並回傳可供補件或管理者修正的明確資訊。

## 10. Migration 策略

- 新增 `migrations/versions/20260825_0007_add_trusted_review_inputs.py`。
- `revision = 20260825_0007`，`down_revision = 20260825_0006`。
- 不修改既有 migration。
- `0007` Upgrade 先執行既有資料 preflight，再建立抽取表與其索引／外鍵，並新增規則版本的適用條件、優先序及已發布來源約束；`source_document_id` 的欄位、外鍵與索引維持 `0004` 的既有 ownership。
- Preflight 發現不符合新發布規則契約的資料時直接失敗，不修改業務資料。
- 先在隔離資料庫驗證 `upgrade head -> downgrade 0006 -> upgrade head`，成功後才套用主資料庫。
- Downgrade 只供受控回退驗證；正式環境若已產生抽取資料，不應在未備份的情況下降版。

## 11. 測試與驗收

### Schema contract

- `0007` 是唯一 head，且正確接在 `0006`。
- 新資料表、欄位、索引、外鍵、唯一條件與 CHECK constraints 存在。
- 高影響確認與規則發布來源限制無法被無效資料繞過。

### API 與整合測試

- 呼叫端提交任何舊版報告值、頁碼或規則 ID 都回傳 `422`。
- 沒有完成抽取批次時禁止執行。
- 高影響欄位只有 `AUTO_EXTRACTED` 時禁止執行。
- `VERIFIED` 高影響欄位可執行。
- 其他案件、非最新版文件或不同文件版本的抽取值不可使用。
- DRAFT、失效日期、錯誤案件類型、錯誤行政區與錯誤表型規則不會被選中。
- 法規文件未抽取完成或未發布時禁止執行。
- 同優先序規則衝突時禁止執行。
- 後端執行所有必跑規則，無法建立空 run。
- Snapshot 與 finding evidence 全部可追溯到資料庫正式來源。
- Rerun 建立新歷史，不覆寫舊 run。

### 完成條件

- 隔離資料庫升降版測試成功且測試資料庫已移除。
- 主資料庫 `alembic_version = 20260825_0007`。
- PostgreSQL、API 與 MinIO 維持 healthy。
- `pytest tests app/review/tests -q` 全部通過；既有環境性 skip 與已知第三方 deprecation warning 必須如實回報。
- `git diff --check` 通過。
- `app/review/OUTSIDE_REVIEW_CHANGES.md` 記錄 `0007`、核准時間、目的與驗證結果。

## 12. 修改範圍

允許的外部修改只有：

- `migrations/versions/20260825_0007_add_trusted_review_inputs.py`

其餘修改限制為：

- `app/review/trusted_inputs.py`
- `app/review/completeness.py`
- `app/review/schemas.py`
- `app/review/repository.py`
- `app/review/service.py`
- `app/review/tests/**`
- `app/review/docs/**`
- `app/review/OUTSIDE_REVIEW_CHANGES.md`

不得修改 `app/api/**`、`app/auth/**`、其他子系統、前端、既有 migrations、PostgreSQL/MinIO 基礎設定或根目錄相依套件。
