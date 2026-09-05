# Development Valuation → Review Handoff Seed 設計

日期：2026-09-05

分支：`feature/integrate-valuation-review`

## 1. 目標

新增只在 development 可用的人工整合測試 seed，讓全新本機環境可以直接完成：

```text
appraiser_demo 登入 Swagger
→ 對尚未送審的 Valuation 案件執行 submit-for-review
→ review_demo 登入 Review 工作台
→ 找到同一案件並執行審查
→ 核准或退回
```

成功條件是 seed 完成後不需要人工寫 SQL，也不需要先準備既有帳號或案件。

## 2. 已確認的方案

### 採用：既有 CLI 入口 + 獨立整合 seed 模組

- 指令入口維持熟悉的 `python -m app.review.demo handoff-seed`。
- `app.review.demo` 只負責解析指令與輸出結果。
- 跨 Valuation／Review 的資料準備放在獨立 `app.review.handoff_demo`，避免繼續放大既有 `demo.py`。
- seed 只建立送審前置資料；不得直接建立 `valuation.review_submissions` 或 `review.reviews`。

### 未採用方案

1. 全部直接加進 `app.review.demo`：檔案已包含既有 Review Demo lifecycle，繼續加入跨模組資料會讓責任混雜。
2. 提供一段手動 SQL：會繞過密碼雜湊、MinIO 補償處理與伺服器送審驗證，也不適合一般人工測試。

## 3. CLI 合約

啟動服務後執行：

```powershell
docker exec land_valuation_api python -m app.review.demo handoff-seed
```

成功時輸出一個 JSON 物件，至少包含：

```json
{
  "ok": true,
  "command": "handoff-seed",
  "appraiser": {
    "username": "appraiser_demo",
    "password": "本次隨機密碼"
  },
  "reviewer": {
    "username": "review_demo",
    "password": "本次隨機密碼"
  },
  "case": {
    "case_id": "uuid",
    "case_no": "DEMO-HANDOFF-001",
    "case_version": 1,
    "source_validation_run_id": "uuid",
    "source_report_document_id": "uuid"
  },
  "swagger_url": "http://localhost:8000/docs",
  "review_url": "http://localhost:8000/api/v1/review/test-ui"
}
```

限制：

- 密碼每次使用安全亂數產生，只在 CLI stdout 顯示一次。
- 不在程式、HTML、文件或資料庫保存明文固定密碼。
- 輸出不得包含 MinIO bucket、object key、presigned URL 或 JWT。
- `APP_ENV` 不是 `development` 時固定失敗，且不寫入任何資料或物件。

## 4. Seed 建立內容

### 帳號與權限

- 建立或重建 `appraiser_demo`，啟用並綁定既有 `APPRAISER` 角色。
- 建立或重建 `review_demo`，啟用並綁定既有 `REVIEWER` 角色。
- migration 仍是角色與權限的唯一正式來源；seed 不自行發明新 permission。

### Valuation 案件

建立固定可辨識案件編號 `DEMO-HANDOFF-001`，並準備 SubmissionService 送審前置檢核實際需要的最小資料：

- 案件屬於 `appraiser_demo`，狀態允許首次送審，`case_version=1`。
- 一份保存在 MinIO 的正式完整估價報告 PDF，以及 PostgreSQL 文件 metadata。
- 同案、同版本的正式報告 form lineage。
- 完成且屬於 Valuation 的 source validation run。
- server-built Snapshot 所需的 APPLIED 欄位、文件證據、Decimal-safe 正式資料。
- Review 執行所需的已發布 rule version、來源文件與 active validation rules。

Seed 結束時必須保證：

- 尚無 `valuation.review_submissions`。
- 尚無該案件的 `review.reviews`。
- 使用者必須親自在 Swagger 呼叫正式送審 API，才能讓 Review 工作台出現案件。

## 5. 重複執行與清理

- `handoff-seed` 必須可重複執行。
- 每次只清理 `DEMO-HANDOFF-001` 與兩個指定 Demo 帳號所屬的測試資料，不得清除一般案件或使用者。
- 清理順序必須符合外鍵；既有 Submission、Run、finding、decision、correction request、report 等測試歷史可在重建同一 Demo 前刪除，但不得影響非 Demo 資料。
- MinIO 只移除這個 Demo 擁有的 object keys，不做 bucket 清空或全域 prune。
- 若資料庫寫入失敗，rollback 並補償刪除本次已上傳的 MinIO 物件。
- 不新增 migration；Demo 資料不可由 migration seed。

## 6. 資料流

```text
handoff-seed
→ 建立兩個隨機密碼 Demo 使用者
→ 建立 Valuation 案件與正式資料／PDF／規則
→ 輸出登入資訊與送審 ID

人工：APPRAISER login
→ POST /api/v1/valuation/cases/{case_id}/submit-for-review
→ SubmissionService 建立 immutable Snapshot + Review

人工：REVIEWER login
→ Review workbench 讀取該 Submission
→ 執行 Run、疑點判定、核准或退回
```

## 7. 錯誤處理

- 缺少 APPRAISER／REVIEWER 角色或必要 migration：清楚回傳 Demo error，整批不建立。
- MinIO 上傳失敗：資料庫不 commit。
- 資料庫建立失敗：rollback，刪除本次已上傳物件。
- 重複 seed：先精確清除舊 `DEMO-HANDOFF-001`，再建立一組全新的 IDs 與密碼。
- 不得吞掉部分成功；stdout 的 `ok: true` 只在所有前置資料完成後輸出。

## 8. 專案結構與風格

- `app/review/demo.py`：新增 `handoff-seed` CLI route，沿用 development gate 與 JSON 輸出風格。
- `app/review/handoff_demo.py`：整合 seed／reset、精確清理、MinIO 補償與結果組裝。
- `app/review/tests/test_handoff_demo.py`：CLI 合約、development gate、輸出安全與冪等行為。
- `tests/integration/test_handoff_demo.py`：真實 PostgreSQL／MinIO／HTTP handoff 驗收。
- `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md`：改成以 `handoff-seed` 為零前置人工流程。

遵循現有 Python typing、Pydantic／SQLAlchemy／psycopg 模式，不新增第三方依賴。

## 9. 測試策略

所有 production change 採 Red → Green：

1. 先寫 CLI contract 測試，確認 `handoff-seed` 尚不存在而失敗。
2. 先寫 development-only、密碼安全與輸出不洩漏 object key 測試。
3. 寫真實整合測試，執行 seed 後驗證：
   - 兩個帳號能登入且角色正確。
   - APPRAISER 取得 `valuation.submit_review`。
   - 案件送審前不存在 Submission／Review。
   - APPRAISER 透過正式 API 送審成功。
   - REVIEWER 在工作台看到同一案件並能建立 Review Run。
4. 重跑既有 Review Demo 測試，確保 `seed/revise/reset` 不回歸。
5. 重跑 Review backend、完整 isolated suite、Node UI、compileall 與 `git diff --check`。
6. 確認測試容器、網路與 volumes 沒有殘留。

## 10. 邊界

### 一定要做

- development-only。
- 隨機密碼只顯示一次。
- 使用正式登入、送審與 Review service/API 驗證 handoff。
- PostgreSQL 只存 metadata；PDF 本體在 MinIO。
- seed 後案件保持尚未送審。
- 更新人工測試說明，讓全新環境可直接照做。

### 需要先詢問

- 新 migration 或 schema。
- 新第三方依賴。
- 修改 development 以外的正式資料初始化策略。

### 絕對不做

- 不自動送審。
- 不直接建立 Review 來冒充 handoff。
- 不提供固定密碼或經 HTTP 取得明文密碼的端點。
- 不新增 APPRAISER 前端、通知、背景工作或 batch workflow。
- 不 push、merge、清理 branch/worktree 或修改 `.serena/`。

## 11. 驗收標準

1. 全新 development Compose 啟動後，只需一個 `handoff-seed` 指令即可取得兩組帳密與一件可送審案件。
2. Seed 回傳的 APPRAISER 登入後可用正式 `submit-for-review` 建立 Submission 1。
3. 送審前 Review 工作台沒有該案件；送審後 REVIEWER 可看到同一案件。
4. REVIEWER 可開啟 immutable evidence、執行 Run、處理疑點並核准或退回。
5. 重複 seed 不累積同名案件、Review、歷史資料或 MinIO 物件。
6. 非 development 執行沒有任何副作用。
7. 自動測試與人工說明均不得把 fixture-only 資料描述成持久可用資料。

## 12. 開放問題

無。使用者已確認建立一件可送審案件；若要同時測試核准與退回，可重新執行 seed 取得乾淨案件後測另一條路徑。
