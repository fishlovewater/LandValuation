# 土地估價書輔助與智慧審查系統

本專案預定包含估價書輔助製作、查估書智慧審查、案件履歷與分析、法規知識助手，以及登入與角色權限。

## 目前階段

- PostgreSQL 資料表。
- MinIO 檔案儲存。
- PostgreSQL 與 MinIO 的檔案對應規則。
- FastAPI 共用後端骨架：資料庫、MinIO、JWT/RBAC、錯誤格式與健康檢查。

目前不建置 Vue，也尚未建置案件、估價與智慧審查的業務 API；資料庫結構更新由 Alembic 管理。

## 儲存邊界

- PostgreSQL：案件、估價資料、審查結果、案件履歷、使用者權限、法規文字與向量。
- MinIO：估價書、地籍圖、土地登記資料、勘查照片、附件、檢核報告與原始法規 PDF，統一存於 `land-valuation` bucket。
- PostgreSQL 不保存大型 PDF 或圖片本體。
- 文件紀錄的 `bucket_name` 固定為 `land-valuation`，`object_key` 使用 `cases/` 或 `knowledge/` 前綴，不保存固定 localhost URL。

## 啟動

1. 安裝並啟動 Docker Desktop。
2. 將 `.env.example` 複製為 `.env`，並更換預設密碼。
3. 執行 `docker compose up -d --build`。
4. 執行 `docker compose ps` 確認 PostgreSQL、MinIO 與 API 狀態。

Compose 會透過一次性 `migrate` service 自動執行 `alembic upgrade head`。查看 migration 結果：

```powershell
docker compose logs migrate
docker compose logs api
```

FastAPI：

```text
API:     http://localhost:8000
Swagger: http://localhost:8000/docs
Live:    http://localhost:8000/health/live
Ready:   http://localhost:8000/health/ready
```

目前 API 端點：

```text
POST /api/v1/auth/login
GET  /api/v1/auth/me
GET  /health/live
GET  /health/ready
```

Knowledge AI 的 `KNOWLEDGE_ANSWER_PROVIDER` 預設為安全的 `evidence_only`：
有候選來源時回傳 `EVIDENCE_ONLY`，不宣稱答案已經 AI 驗證；只有經引用契約驗證
的模型回答才會是 `SUPPORTED`。`codex_cli` 必須明確選用，且只允許
`APP_ENV=development` 或 `test`；production/staging 會 fail closed。Codex
測試模式以 read-only sandbox、approval never、停用 web search/shell/apps/
multi-agent/login shell 的 CLI 設定，以及 allowlisted subprocess environment
共同限制邊界。完整 provider 設定與使用方式見
[app/KNOWLEDGE_AI_README.md](app/KNOWLEDGE_AI_README.md)。

Knowledge AI 對沒有既有 chunks 的 MinIO 文件採按請求擷取。可在 `.env` 以
`KNOWLEDGE_RUNTIME_MAX_OBJECTS`、`KNOWLEDGE_RUNTIME_MAX_OBJECT_BYTES`、
`KNOWLEDGE_RUNTIME_MAX_TOTAL_BYTES` 與 `KNOWLEDGE_RUNTIME_MAX_TOTAL_CHARACTERS`
限制單次處理的物件數、單一文件 bytes、總下載 bytes 與總文字字元數；預設值分別
為 100、10 MiB、50 MiB、200,000；可設定範圍分別為 1–1,000、1 KiB–100 MiB、
1 KiB–500 MiB、1,000–2,000,000。MinIO 列舉的物件大小會在下載前檢查，未知大小的
來源仍以讀取上限防護，超過限制的來源會略過並列入 unreadable sources。

若現有 PostgreSQL volume 已由舊版 `database/init` SQL 建好相同結構，不可再執行初始 migration；請先備份並核對 schema，然後執行：

```powershell
docker compose run --rm migrate alembic stamp head
```

## 更新資料庫

取得新的 migration 後，先備份資料庫，再重建 migration image 並套用到最新版本：

```powershell
docker compose build migrate
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic current
```

如需開發新的資料庫變更，請在本機安裝依賴後建立新 revision：

```powershell
python -m pip install -r requirements.txt
alembic revision -m "describe change"
```

編輯新 revision 的 `upgrade()` 與 `downgrade()`，測試後一併提交。不可修改已在任何共用環境套用過的舊 revision，也不要用 `stamp` 取代正常 upgrade。

FastAPI 架構與資料存取詳見 [app/README.md](app/README.md)。資料庫 schema、Alembic、MinIO bucket/object key 與驗證方式詳見 [database/README.md](database/README.md)。變更紀錄詳見 [UPDATE.md](UPDATE.md)。
