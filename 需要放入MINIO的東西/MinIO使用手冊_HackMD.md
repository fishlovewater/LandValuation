# MinIO 使用手冊｜土地估價輔助系統

## 1. MinIO 的用途

MinIO 用來保存系統中的實際檔案，例如：

- 法規與評價基準 PDF
- 查估表與製作手冊
- 案件原始估價書
- 地籍圖與土地登記資料
- 現場勘查照片及其他附件
- 系統產生的估價書與檢核報告

> PostgreSQL 保存案件欄位、檢核結果及檔案路徑；MinIO 保存真正的 PDF、圖片與附件。

---

## 2. 啟動 MinIO

請先啟動 Docker Desktop，再於專案根目錄執行：

```bash
docker compose up -d
```

確認服務狀態：

```bash
docker compose ps -a
```

正常情況應顯示：

```text
land_valuation_minio         Up（healthy）
land_valuation_minio_init    Exited (0)
```

`minio-init` 顯示 `Exited (0)` 代表初始化成功，不是發生錯誤。

---

## 3. 登入 MinIO

在瀏覽器開啟：

```text
http://localhost:9001
```

使用專案 `.env` 中設定的帳號與密碼登入：

```env
MINIO_ROOT_USER=你的帳號
MINIO_ROOT_PASSWORD=你的密碼
```

登入後，只使用以下 Bucket：

```text
land-valuation
```

請勿另外建立 `cases`、`knowledge`、`regulations` 等 Bucket。它們都是 `land-valuation` 裡面的物件路徑。

---

## 4. 儲存架構

```text
land-valuation
├── cases/
│   └── {case_id}/
│       ├── original/
│       ├── cadastral-map/
│       ├── land-register/
│       ├── photos/
│       ├── attachments/
│       └── generated/
│
└── knowledge/
    ├── regulations/
    ├── standards/
    └── manuals/
```

MinIO 沒有真正的空資料夾。路徑中至少有一個檔案時，才會在管理介面顯示，因此不需要事先建立所有空 Path。

---

## 5. 共用知識文件放置位置

### 5.1 法規

放置路徑：

```text
knowledge/regulations/
```

| 文件 | 完整物件路徑 |
|---|---|
| 土地徵收條例.pdf | `knowledge/regulations/土地徵收條例.pdf` |
| 土地徵收條例施行細則.pdf | `knowledge/regulations/土地徵收條例施行細則.pdf` |
| 土地徵收補償市價查估辦法.pdf | `knowledge/regulations/土地徵收補償市價查估辦法.pdf` |

### 5.2 查估表、範本及評價標準

放置路徑：

```text
knowledge/standards/
```

| 文件 | 完整物件路徑 |
|---|---|
| 土地市價查估表.pdf | `knowledge/standards/土地市價查估表.pdf` |
| 比準地查估表.pdf | `knowledge/standards/比準地查估表.pdf` |
| 比較法查估表.pdf | `knowledge/standards/比較法查估表.pdf` |
| 買賣實例調查估價表.pdf | `knowledge/standards/買賣實例調查估價表.pdf` |
| 區域或個別因素評價基準 | `knowledge/standards/{原始檔名}.pdf` |

### 5.3 製作及操作手冊

放置路徑：

```text
knowledge/manuals/
```

| 文件 | 完整物件路徑 |
|---|---|
| 新北市土地徵收補償市價查估書表製作手冊_第4至10章.pdf | `knowledge/manuals/新北市土地徵收補償市價查估書表製作手冊_第4至10章.pdf` |
| 系統操作手冊 | `knowledge/manuals/{原始檔名}.pdf` |

分類原則：

- `regulations`：正式法規及施行細則。
- `standards`：查估表、評價基準、修正率標準與填寫範本。
- `manuals`：查估書製作手冊及系統操作說明。

---

## 6. 案件文件放置位置

每個案件必須使用唯一的 `case_id`，例如：

```text
CASE-2026-0001
```

| 文件類型 | 路徑格式 | 範例 |
|---|---|---|
| 原始估價書或送審文件 | `cases/{case_id}/original/` | `cases/CASE-2026-0001/original/原始估價書.pdf` |
| 地籍圖 | `cases/{case_id}/cadastral-map/` | `cases/CASE-2026-0001/cadastral-map/地籍圖.pdf` |
| 土地登記資料或謄本 | `cases/{case_id}/land-register/` | `cases/CASE-2026-0001/land-register/土地登記謄本.pdf` |
| 現場勘查照片 | `cases/{case_id}/photos/` | `cases/CASE-2026-0001/photos/現場照片_01.jpg` |
| 其他附件 | `cases/{case_id}/attachments/` | `cases/CASE-2026-0001/attachments/都市計畫圖.pdf` |
| 系統產出文件 | `cases/{case_id}/generated/` | `cases/CASE-2026-0001/generated/檢核報告.pdf` |

`generated` 原則上由後端程式寫入，不應拿來存放使用者上傳的原始文件。

---

## 7. 使用網頁介面上傳檔案

1. 登入 `http://localhost:9001`。
2. 點選 `land-valuation` Bucket。
3. 進入目標路徑。
4. 點右上角 `Upload`。
5. 選擇要上傳的檔案。
6. 上傳完成後按 `Refresh`，確認檔案名稱、位置及大小正確。

如果目標路徑尚未顯示，可以直接以完整物件路徑上傳；第一個檔案上傳成功後，路徑便會顯示。

---

## 8. 使用指令上傳檔案（Windows CMD）

假設檔案放在 Windows 的：

```text
C:\Users\user\Downloads\土地徵收補償市價查估辦法.pdf
```

執行：

```bat
docker compose run --rm --entrypoint /bin/sh -v "C:\Users\user\Downloads:/upload:ro" minio-init -c "mc alias set local http://minio:9000 實際帳號 實際密碼 && mc cp '/upload/土地徵收補償市價查估辦法.pdf' 'local/land-valuation/knowledge/regulations/土地徵收補償市價查估辦法.pdf'"
```

注意：掛載後，容器內的來源位置是 `/upload/檔案名稱`，不能在容器內使用 `C:\Users\...`。

如果密碼含有 `&`、`!`、空格等特殊字元，不建議直接寫在 CMD 指令中，請改用專案既有的環境變數設定。

---

## 9. 下載、查看與刪除

### 下載

1. 在 Object Browser 找到檔案。
2. 勾選檔案或開啟檔案功能選單。
3. 選擇 `Download`。
4. 確認下載後可以正常開啟。

### 刪除

1. 確認檔案路徑及案件編號。
2. 勾選檔案。
3. 選擇刪除功能。
4. 再次確認後刪除。

請勿任意刪除其他組員上傳的檔案。正式系統完成後，上傳、下載與刪除都應透過 FastAPI 處理，不直接使用 MinIO 管理介面。

---

## 10. 檔案命名規則

建議格式：

```text
文件名稱_版本或日期.副檔名
```

例如：

```text
土地徵收補償市價查估辦法_2026.pdf
查估書表範本_v1.pdf
現場照片_01.jpg
檢核報告_v2.pdf
```

注意事項：

1. 保留正確副檔名，不能將 PPTX 直接改名為 PDF。
2. 移除下載時自動產生的 `(1)`、`(2)`、`(3)`。
3. 不使用 `/`、`\`、`:`、`*` 等特殊符號作為檔名。
4. 同一案件的所有檔案必須使用相同 `case_id`。
5. 更新正式文件時應保留版本或日期，不直接覆蓋到無法追蹤。

---

## 11. 團隊共同規則

> 所有檔案統一存入 `land-valuation` Bucket；案件檔案使用 `cases/{case_id}/{category}/{filename}`，知識文件使用 `knowledge/{category}/{filename}`。

1. 不建立其他 Bucket。
2. Bucket 保持 `PRIVATE`，不得設成公開。
3. 不任意修改既定英文路徑名稱。
4. 案件原始文件與系統產出文件必須分開保存。
5. PostgreSQL 記錄 `bucket_name`、`object_key`、原始檔名、檔案類型、上傳者及時間。
6. MinIO 保存實際檔案，不保存案件欄位與檢核結果。
7. 未來 Vue 前端不得直接連線 MinIO，應透過 FastAPI 上傳及下載。

---

## 12. 驗收方式

完成建置後，請確認：

- [ ] `land_valuation_minio` 顯示 `healthy`
- [ ] 可以登入 `http://localhost:9001`
- [ ] 只有一個 `land-valuation` Bucket
- [ ] Bucket 權限是 `PRIVATE`
- [ ] 可以上傳一份 PDF
- [ ] 可以下載並正常開啟該 PDF
- [ ] 法規、標準與手冊放在正確路徑
- [ ] 中文檔名可以正常顯示
- [ ] 沒有把 `cases` 或 `knowledge` 建成獨立 Bucket

---

## 13. 注意：GitHub 不會同步 MinIO 內容

`git push` 和 `git pull` 只會同步程式碼及設定檔，不會同步：

- MinIO 中的 PDF 與圖片
- PostgreSQL 中既有的資料
- Docker Volume
- `.env`

因此每位組員第一次建置時，仍需取得團隊共用文件並上傳到相同路徑。未來可以再製作自動匯入共用文件的初始化程式。

---

## 14. 常用指令

啟動服務：

```bash
docker compose up -d
```

查看狀態：

```bash
docker compose ps -a
```

查看 MinIO 日誌：

```bash
docker compose logs minio
```

停止服務但保留資料：

```bash
docker compose down
```

> 不要隨意執行 `docker compose down -v`。`-v` 會刪除 PostgreSQL 與 MinIO 的 Docker Volume，已上傳的檔案也會消失。
