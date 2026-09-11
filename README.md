# 土地估價書輔助與智慧審查系統

本專案提供估價書輔助製作、來源文件與 AI/OCR 擷取、查估書智慧審查、案件履歷與版本追溯、法規知識助手，以及登入與角色權限管理。

## 目前階段

- FastAPI：案件、估價、文件、AI/OCR extraction、正式查估書、送審、智慧審查、History、Knowledge / AI Assistant API。
- Vue 3 + TypeScript：角色導向登入、估價 Wizard、來源文件預覽、候選欄位確認、送審、審查工作台、案件歷程與持續可開啟的 AI Assistant。
- PostgreSQL：結構化案件、估價、審查、History、權限與知識資料。
- MinIO：PDF、圖片、Excel、附件與產出報告。
- Alembic：資料庫 schema migration。
- Docker Compose：PostgreSQL、MinIO、migration 與 API；另有 Demo 與 integration compose 設定。

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

主要 API 分區：

```text
POST /api/v1/auth/login
POST /api/v1/auth/demo-login          # development 或明確 Demo 開關
GET  /api/v1/auth/me
     /api/v1/valuation/...
     /api/v1/review/...
     /api/v1/history/...
     /api/v1/knowledge/...
     /api/v1/assistant/...
GET  /health/live
GET  /health/ready
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

一般 production build：

```powershell
npm run build
```

競賽／展示 build（顯示三個一鍵 Demo 帳號按鈕）：

```powershell
npm run build:demo
```

後端 Demo 部署需同時設定 `DEMO_QUICK_LOGIN_ENABLED=true`；`docker-compose.demo.yml` 已明確開啟此設定。一般 production 預設為 `false`，避免固定 Demo 帳號入口被意外開放。

本機展示建議直接從 repository root 執行：

```powershell
.\scripts\demo-up.ps1
```

此腳本會建置並啟動獨立的 `landvaluation-persistent-demo` Compose project、等待 API ready、檢查 Demo 狀態，並只在安全的 pre-submission 狀態建立／刷新三個展示帳號與示範案件。若該 Demo generation 已經送審或進入 Review，腳本會拒絕自動 reseed，避免覆蓋展示證據。映像已是最新時可用 `-SkipBuild` 略過 build。後端就緒後只需在另一個 PowerShell 視窗執行 `cd frontend; npm run dev`，再使用登入頁三個一鍵角色按鈕。

Excel / DOCX 內嵌預覽預設最多讀取 10 MiB，可用 `DOCUMENT_PREVIEW_MAX_BYTES` 調整；超過限制時仍可下載原始文件查看。

F03 AI Assistant 可在開發環境使用本機 Ollama 測試，不需要 API key。預設測試模型為 `qwen3.5:latest`：

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DOCKER_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3.5:latest
OLLAMA_TIMEOUT_SECONDS=120
```

直接在主機執行 FastAPI 時使用 `OLLAMA_BASE_URL`；透過 Docker Compose 啟動 API 時，Compose 會將 `OLLAMA_DOCKER_BASE_URL` 映射為 container 內的 `OLLAMA_BASE_URL`。Assistant 使用 Ollama 原生 `/api/chat` tool calling，既有欄位寫入、計算、PDF 產生與設施查詢的結構化確認／權限檢查仍由後端執行。

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
