# Review 測試主控台設計

## 目的

建立一個只供本機 development 環境使用的簡易前端與 Demo 資料 CLI，讓使用者能以真實 JWT、PostgreSQL、MinIO 與 Review API 手動驗證第二子系統的完整 MVP 流程。

本功能只測試 `app/review`；不建立正式產品前端，也不補做其他子系統。

## 邊界與安全

- 所有新增或修改的檔案都必須位於 `app/review/**`。
- 測試頁面只在 `APP_ENV=development` 時提供；其他環境回傳 `404`，不暴露功能存在與否。
- Demo 資料異動只透過容器內 CLI 執行，前端不提供 seed、revise 或 reset 按鈕。
- 前端不保存密碼；JWT 只放在瀏覽器 `sessionStorage`，關閉分頁後失效。
- Demo reset 只能依固定 ownership marker、固定 username 與固定案件編號刪除資料；不得使用模糊條件或清空整張表。
- PostgreSQL 只保存檔案 metadata，Demo PDF 本體存入 MinIO `land-valuation` bucket。
- CLI 發生 PostgreSQL 寫入失敗時，必須清理由本次命令新建的 MinIO objects，避免孤兒物件。

## 元件

### 1. Development-only 測試頁面

路徑：`GET /api/v1/review/test-ui`

頁面使用一個位於 `app/review/test_ui/index.html` 的靜態 HTML 檔，CSS 與 JavaScript 全部內嵌，不加入 npm、Vue、React 或額外後端套件。

`app/review/router.py` 只負責：

1. 檢查 `APP_ENV`。
2. 非 development 回傳 `404`。
3. development 以 `FileResponse` 回傳 HTML。

### 2. Demo CLI

入口：

```powershell
python -m app.review.demo seed
python -m app.review.demo revise
python -m app.review.demo reset
```

在容器內執行時：

```powershell
rtk docker exec land_valuation_api python -m app.review.demo seed
rtk docker exec land_valuation_api python -m app.review.demo revise
rtk docker exec land_valuation_api python -m app.review.demo reset
```

CLI 在非 development 環境拒絕執行並回傳非零 exit code。

### 3. Demo ownership

使用固定識別：

- username：`review_demo`
- case number：`DEMO-REVIEW-001`
- Demo 文件 object key 必須位於該 Demo case ID 下，並使用 `demo/` category。
- Demo 法規文件使用可由固定文件標題及 ownership metadata 精確辨識的紀錄。

CLI 不使用固定密碼。每次 `seed` 產生新的隨機密碼、更新 Demo 使用者密碼雜湊，並只在命令輸出顯示一次。

## Demo 資料流程

### seed

`seed` 採可重複執行設計：先以 reset 的相同精確 ownership 規則移除舊 Demo，再建立新資料。

建立內容：

1. `review_demo` 使用者，啟用並授予 `REVIEWER` 角色。
2. 固定 Demo case 與估價基準資料。
3. 原始估價文件 v1 metadata 與 MinIO PDF。
4. v1 completed extraction run。
5. 已確認的 `adjustment_rate` 與 `expert_grade` 正式欄位。
6. 已發布且已完成抽取的法規來源文件與 MinIO PDF。
7. 適用該案件的 published rule version。
8. `ADJUSTMENT_RATE` 與 `EXPERT_GRADE` 兩條 active validation rules。

命令輸出 JSON：

```json
{
  "username": "review_demo",
  "password": "generated-on-each-seed",
  "case_id": "uuid",
  "test_ui_url": "http://localhost:8000/api/v1/review/test-ui"
}
```

seed 不預先建立 `review.reviews`；該紀錄必須由測試頁面呼叫正式 `POST /review/cases` 建立。

### revise

`revise` 只對固定 Demo case 建立：

1. 原始估價文件 v2 metadata 與 MinIO PDF。
2. v2 completed extraction run。
3. 修正後且已確認的正式欄位，使新 run 能呈現問題已改善。

revise 不直接修改舊文件、舊 extraction、舊 run 或舊 finding。

### reset

reset 先找出固定 Demo case、Demo 使用者、Demo 規則來源與其明確 object keys。清除順序依外鍵限制由子資料到父資料執行，並在資料庫成功後刪除對應 MinIO objects。

若找不到 Demo 資料，reset 回傳成功且刪除數為零。任何不符合固定 ownership 的紀錄都不可刪除。

## 前端操作流程

頁面分成五個區塊：

1. **連線與登入**：顯示 health、輸入 username/password、登入、登出。
2. **案件與完整性**：輸入 seed 輸出的 `case_id`、建立 Review、查看案件、執行 completeness check。
3. **檢核結果**：執行 run、列出 runs、findings 與 risk summary。
4. **人工決策與重跑**：對 finding 送出決策、對案件送出決策；提示使用者在 PowerShell 執行 revise，再執行 completeness check 與 rerun。
5. **報告**：查看結構化 JSON 報告、產生及下載 PDF。

頁面自動保存目前 `review_id`、`validation_run_id` 與選取的 `finding_id` 至 `sessionStorage`，但允許手動覆寫，方便測試錯誤情境。

## API 顯示與錯誤處理

- 每次操作顯示 HTTP method、path、status、elapsed time 與格式化 JSON。
- 非 2xx 回應顯示共用 API error code、message、details，不把錯誤吞掉。
- `401` 提示重新登入；`403` 顯示權限不足；`404` 顯示資源不存在；`409` 顯示狀態或規則衝突；`422` 顯示輸入驗證錯誤。
- 網路失敗與非 JSON 回應保留原始文字，方便診斷。
- 產生 PDF 與下載 PDF 分開操作，避免把不存在的報告誤判為下載錯誤。

## 測試

### 後端與安全

- development 環境可取得測試頁面。
- 非 development 環境回傳 `404`。
- CLI 非 development 拒絕 seed、revise、reset。
- seed 可重複執行且不累積 Demo 資料。
- reset 只刪固定 Demo ownership，保留非 Demo 資料。
- seed 或 revise 的 DB 寫入失敗時不留下新 MinIO objects。

### Demo 完整流程

- seed 後可使用輸出帳密呼叫正式 login。
- 建立 Review、completeness、run、findings、risk、decision 均走正式 API。
- revise 後 rerun 使用 v2欄位，舊 run／finding 仍可查詢。
- 結構化報告與 PDF API 均可使用。
- reset 後 Demo DB rows 與 MinIO objects 均不存在。

### 視覺與手動驗收

- 在 1280px 桌面寬度與 375px 行動寬度下可操作。
- 所有按鈕具 loading／disabled 狀態，避免重複送出。
- 鍵盤可操作登入、案件、run、決策與報告流程。
- 使用瀏覽器實際完成一次 seed → UI flow → revise → rerun → report → reset。

## 明確不做

- 不建立 Vue、React 或正式設計系統。
- 不修改 `app/main.py`、`app/api/router.py`、Compose、migration、根目錄測試設定或其他子系統。
- 不讓前端直接寫 PostgreSQL 或 MinIO。
- 不建立 production seed endpoint。
- 不模擬 OCR、Bedrock、通知寄送、履歷分析或 RAG。

## 驗收條件

1. 所有程式與文件變更都在 `app/review/**`。
2. live API 的 Review 既有測試仍全部通過。
3. development-only UI 與 CLI 的安全測試通過。
4. Demo 完整流程以真實 PostgreSQL、MinIO、JWT 與 Review API 跑通。
5. reset 後沒有 Demo rows、Demo objects 或未追蹤工作檔。
6. `app/review/CHANGELOG.md` 與 `.sdd` 紀錄本次設計、測試與提交結果。
