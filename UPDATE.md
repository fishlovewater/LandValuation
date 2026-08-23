# UPDATE

## 2026-08-23 - Alembic

- 擴充根目錄與 `database/README.md` 的資料庫更新說明，加入建立 revision、測試 upgrade/downgrade、Compose 套用、版本核對、baseline stamp 與備份原則。
- 完成現有 `alembic.ini` 與 `migrations/env.py`，連線資訊改從 `DATABASE_URL` 或 `POSTGRES_*` 環境變數取得。
- 新增 `migrations/versions/20260823_0001_initial_schema.py` 作為初始 revision，依序套用三個已審查的 schema SQL。
- 新增 `requirements.txt`，包含 Alembic、SQLAlchemy、psycopg 與 SQL 切分工具。
- 新增 `Dockerfile.migrations` 專用 migration image。
- `docker-compose.yml` 新增一次性 `migrate` service，並移除 PostgreSQL entrypoint 的 `database/init` 掛載，讓 Alembic 成為唯一 schema 建立來源。
- 更新根目錄與資料庫 README，記錄 upgrade、current、revision 與現有資料庫 baseline stamp 流程。
- 未建立 FastAPI、Vue 或 ORM models。
- Alembic Python 檔案已通過語法編譯檢查，Compose 設定解析也已通過。
- 本機尚未安裝 `requirements.txt` 依賴，且 Docker daemon 未啟動，因此尚未對實際 PostgreSQL 執行 `alembic upgrade head`。

## 2026-08-23

### 本次範圍

僅建置 PostgreSQL 資料結構、MinIO 物件儲存與兩者的對應規則。未建立 Vue、FastAPI 或 Alembic。

### 變更內容

- `docker-compose.yml`：新增 MinIO API/Console、`minio-init`、`cases`/`knowledge` buckets 與 `minio_data` volume。
- `.env.example`：新增 MinIO 帳號、密碼與 ports。
- `database/init/001_core_schema.sql`：`valuation.documents` 將 `storage_key` 拆為 `bucket_name` 與 `object_key`，並新增唯一性及安全格式約束。
- `database/init/002_platform_schema.sql`：新增 `auth`、`review`、`history` schemas 及指定資料表；新增 `auth.role_permissions` 與 `valuation.valuations`。
- `database/init/003_knowledge_schema.sql`：新增 `knowledge.documents`、`chunks`、`embeddings`、`conversations`、`messages` 與 `message_sources`。
- `database/optional/002_optional_rag_schema.sql`：舊版選配 RAG 文件位置也改為 `bucket_name` 與 `object_key`；仍不會自動執行。
- `database/README.md`：記錄啟動、schema、bucket/object key 與驗證規則。

### 儲存規則

- PostgreSQL 不保存大型 PDF、圖片或附件本體。
- MinIO object key 不包含固定 `localhost` URL、endpoint 或 presigned URL。
- 案件物件：`{case_id}/{category}/{document_id}/v{version_no}/{stored_filename}`。
- 知識物件：`{category}/{document_id}/v{version_no}/{stored_filename}`。

### 注意

PostgreSQL image 只會在全新 data volume 執行 `database/init` SQL。已有資料庫不會自動套用本次新增結構，且不應在未備份時刪除現有 volume。

### 驗證結果

- `docker compose --env-file .env.example config --quiet` 已通過。
- 已確認初始化 SQL 包含五個指定 schemas 與所需資料表。
- MinIO Server 與 Client 的固定 release tags 已對照官方 release 記錄。
- 本機 Docker daemon 未啟動，因此本次無法完成實際容器初始化、MinIO 上傳/下載/刪除與 PostgreSQL 查詢驗證。
