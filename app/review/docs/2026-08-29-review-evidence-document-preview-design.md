# Review 證據呈現與原文件對照設計

## 目的

將審查工作台中的技術資料轉換為審查人員可直接判讀的內容，並讓人員在作成疑點決策時，同畫面核對原文件對應頁。JSON、API 路徑及物件儲存資訊不得成為主要審查內容。

本次只修改 `app/review/**`。不建立 Vue／React 專案、不新增 migration，也不修改其他子系統或根目錄設定。

## 核准範圍

- 「原始文字與證據」改成中文、可閱讀的欄位及段落。
- 「法規依據」改成中文、可閱讀的引用內容。
- 開發資訊中的每筆 API 請求預設收合。
- 文件類型、疑點決策及案件決策顯示中文。
- 「部分採納後的正式值」只在部分採納時顯示並必填。
- 疑點審查採原 PDF 與決策內容左右分欄。
- 小螢幕提供開啟原文件的替代操作。

## 顯示原則

### 證據內容

每個疑點依序顯示：

1. 申報值與系統判斷。
2. 來源文件中文名稱、文件版本及頁碼。
3. 原始文字摘錄。
4. 結構化證據的中文名稱和值。
5. 法規文件名稱、條文或章節、適用日期、引用內容及適用說明。

`source_evidence` 與 `legal_basis` 若含未預先定義的欄位，仍以「欄位名稱：內容」呈現，不直接輸出 JSON。空值顯示「未提供」，不得由前端推測或補造內容。原始 JSON 只可出現在預設關閉的開發資訊中。

### 中文名稱

文件類型至少包含：

- `original`：原始查估文件。
- `land-register`：土地登記謄本。
- `cadastral-map`：地籍圖。

未知文件類型顯示「其他文件（原代碼）」以避免資訊遺失。

疑點決策顯示：

- `ACCEPTED`：採納疑點。
- `PARTIALLY_ACCEPTED`：部分採納。
- `REJECTED`：不採納。
- `REQUIRES_SUPPLEMENT`：要求補件。
- `EXPERT_REVIEW`：轉專家覆核。

案件決策顯示：

- `RETURNED_FOR_REVISION`：退回修正。
- `SUPPLEMENT_REQUIRED`：要求補件。
- `EXPERT_REVIEW`：轉專家覆核。
- `APPROVED`：核定通過。
- `REVIEW_COMPLETED`：完成審查。

前端只翻譯顯示文字，API request 仍使用既有英文代碼。

## 疑點決策

所有疑點決策都必須填寫決策理由。

只有選擇「部分採納」時才顯示「採納後的正式值」，且該欄位必填。前端沿用疑點既有 `field_path`，送出：

```json
{
  "field_path": "疑點既有欄位路徑",
  "value": "審查人員輸入的採納後正式值"
}
```

此值是決策紀錄，不直接改寫查估端的正式抽取欄位。來源文件、版本及頁碼由疑點證據保留，不要求審查人員重複輸入；若理由引用其他依據，審查人員應在決策理由中說明。

## 原文件對照

### 桌面版

「疑點與決策」頁籤採左右分欄：

- 左側：原 PDF 預覽。
- 右側：疑點清單、證據、法規與決策表單。

選擇疑點時，以該疑點的 `document_id` 與 `page_number` 載入對應文件頁。第一版只保證跳至頁碼；目前資料沒有文字座標，因此不提供原文框選或螢光標示。

### 小螢幕及相容性

窄螢幕不強制左右分欄，顯示「查看原文件第 N 頁」按鈕。若瀏覽器不支援內嵌 PDF，顯示安全下載按鈕及說明，不清除右側決策輸入。

### 文件讀取 API

新增 Review 範圍內的受保護端點：

`GET /api/v1/review/workbench/cases/{review_id}/documents/{document_id}/content`

端點必須：

- 使用既有 JWT 及 `review.execute` 權限。
- 驗證 `review_id` 存在，且 `document_id` 確實屬於該 Review 的 valuation case。
- 只從 PostgreSQL 取得 metadata／object key，再由既有 StorageService 從 MinIO 讀取檔案。
- 以正確 MIME type 回傳串流內容。
- 不在 View API、HTML 或紀錄中暴露 bucket、object key、MinIO 帳密或固定 localhost URL。
- 文件不存在或不屬於案件時回傳 404；儲存服務失敗時使用既有統一錯誤處理。

前端以帶有 Bearer token 的 `fetch` 取得 Blob，再建立暫時 object URL 供 PDF 預覽；切換文件或離開案件時撤銷舊 object URL。

## 開發資訊

每筆 API 紀錄使用獨立的 `details`：

- 預設收合。
- 摘要列保留 method、path、HTTP status 及耗時，例如 `GET /review/... · 200 · 42 ms`。
- 展開後才顯示經過敏感資訊遮罩的 request／response payload。
- 失敗請求沿用醒目樣式，但同樣預設收合。

密碼、Authorization、token 及其他敏感欄位維持遮罩。PDF 二進位內容不得寫入紀錄，只顯示 MIME type 與 bytes。

## 狀態與錯誤處理

- PDF 載入中：左側顯示載入狀態，右側仍可閱讀疑點。
- 文件未提供：顯示「此疑點未連結原文件」，不得載入任意文件。
- 頁碼未提供：開啟文件第一頁並標示「未提供對應頁碼」。
- 401：沿用既有登出並返回登入頁。
- 403：顯示權限不足。
- 404：顯示文件不存在或不屬於此案件。
- 500／MinIO 失敗：保留疑點與尚未送出的決策內容，提供重試。

## 程式邊界

預計修改：

- `app/review/test_ui/index.html`：中文映射、證據格式化、條件式決策欄位、PDF 分欄與收合式 API 紀錄。
- `app/review/router.py`：受保護文件內容端點。
- `app/review/workbench_repository.py`：驗證文件與 Review 案件關聯並取得安全 metadata。
- `app/review/tests/test_ui_behavior.mjs`：前端顯示及決策行為測試。
- `app/review/tests/test_workbench_api.py` 或新增 Review 測試檔：文件權限、案件歸屬、內容與錯誤測試。
- `app/review/tests/test_test_ui.py`：HTML 結構與安全邊界測試。

如實作發現必須修改 `app/review/**` 以外的檔案，停止並先取得使用者同意。

## 驗收條件

- 證據與法規主要畫面不再直接顯示 JSON。
- 所有指定文件及決策代碼顯示中文，送出的 API 代碼不變。
- 非部分採納不顯示正式值欄位；部分採納缺少理由或正式值時不可送出。
- 點選具文件資訊的疑點，可預覽所屬案件文件並跳至對應頁。
- 無權限、跨案件 document_id 或不存在文件不得下載內容。
- 窄螢幕與不支援內嵌 PDF 的瀏覽器仍可安全查看文件。
- API 紀錄預設收合，摘要列可辨識請求與狀態，展開後才顯示遮罩後內容。
- PDF Blob URL 在切換或離開時撤銷，API 紀錄不保存 PDF 本體。
- 既有登入、案件清單、完整性檢查、Run、疑點決策、案件決策、版本差異及報告流程維持可用。
- 新增測試與完整 `app/review/tests` 通過。

## 非目標

- 不新增 PDF 文字座標或螢光標示。
- 不讓審查人員在此畫面修改原始查估文件或正式抽取欄位。
- 不在 PostgreSQL 保存 PDF 本體。
- 不建立通用文件管理前端、OCR、RAG 或其他子系統 API。
- Demo PDF 仍是開發測試素材，不宣稱為正式查估文件內容。
