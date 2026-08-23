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
