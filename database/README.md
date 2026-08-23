# PostgreSQL 與 MinIO

## 啟動

1. 將 `.env.example` 複製為 `.env`，並更換 PostgreSQL 與 MinIO 密碼。
2. 執行 `docker compose up -d --build`。
3. 以 `docker compose ps` 查看狀態。
4. 以 `docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB>` 進入 PostgreSQL。

Compose 不再將 `database/init` 掛載到 PostgreSQL entrypoint，而是由一次性 `migrate` service 執行 `alembic upgrade head`，避免兩套建表機制重複執行。

## Alembic

本機執行：

```powershell
python -m pip install -r requirements.txt
alembic upgrade head
alembic current
```

Compose 執行：

```powershell
docker compose up -d --build
docker compose logs migrate
```

現有 PostgreSQL volume 若已由舊版 `database/init` SQL 建好相同 schema，應先備份與核對，再建立 Alembic baseline：

```powershell
docker compose run --rm migrate alembic stamp head
```

`stamp` 只寫入 Alembic 版本，不會建表或修改現有 schema。不可對結構不完整的資料庫直接 stamp。

新的 migration：

```powershell
alembic revision -m "describe change"
alembic upgrade head
```

目前 SQLAlchemy ORM metadata 只包含 FastAPI 登入所需的 `auth` 部分，並非完整資料庫模型，因此不使用 `--autogenerate`；需在 revision 中明確寫入 schema 變更。

## 如需更新資料庫

### 1. 開發新的 schema 變更

1. 確認本機 `.env` 連到開發資料庫，不是生產資料庫。
2. 安裝依賴並查看目前 revision：

   ```powershell
   python -m pip install -r requirements.txt
   alembic current
   alembic heads
   ```

3. 建立新 revision：

   ```powershell
   alembic revision -m "add review due date"
   ```

4. 編輯新檔案的 `upgrade()` 和 `downgrade()`。目前沒有 ORM metadata，請勿使用 `--autogenerate`。
5. 確認 migration 只處理本次變更，並對新建的測試資料庫驗證：

   ```powershell
   alembic upgrade head
   alembic current
   alembic downgrade -1
   alembic upgrade head
   ```

6. 將 revision 檔、相關說明與 `UPDATE.md` 一併提交。

### 2. 將已有 migration 套用到環境

1. 先備份 PostgreSQL，並確認新版 migration 的影響。
2. 重建 `migrate` image，確保新 revision 已複製進 image：

   ```powershell
   docker compose build migrate
   ```

3. 查看當前版本與待套用歷史：

   ```powershell
   docker compose run --rm migrate alembic current
   docker compose run --rm migrate alembic history
   ```

4. 套用最新 migration：

   ```powershell
   docker compose run --rm migrate alembic upgrade head
   ```

5. 確認版本與資料表：

   ```powershell
   docker compose run --rm migrate alembic current
   docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "SELECT version_num FROM alembic_version;"
   ```

### 3. 重要原則

- 不可修改或刪除已在共用、測試或生產環境套用過的 revision；後續變更必須新建 revision。
- 不要直接在共用資料庫手動執行 DDL，否則實際 schema 可能與 Alembic 版本不一致。
- `alembic stamp` 只用於已經人工核對為相同結構的舊資料庫 baseline，不能取代 `upgrade`。
- 在含重要資料的環境執行 `downgrade`前必須備份；若 downgrade 會刪除欄位、資料表或資料，應優先撰寫新的修正 migration。
- migration 應同時提供可審查的 `upgrade()` 與 `downgrade()`，並在獨立測試資料庫驗證。

### 4. 常用指令

```powershell
alembic current                 # 目前資料庫 revision
alembic heads                   # 程式碼最新 revision
alembic history                 # migration 歷史
alembic upgrade head            # 升級到最新版
alembic upgrade <revision>      # 升級到指定版
alembic downgrade -1            # 回退一個 revision
alembic downgrade <revision>    # 回退到指定版
```

## PostgreSQL schemas

- `auth`：使用者、角色、權限、使用者角色與角色權限。
- `valuation`：案件、宗地、估價表、案件文件、計算結果與四種查估明細。
- `review`：審查、缺件、疑點、風險摘要與人工決策。
- `history`：案件事件、版本、修改前後與調閱紀錄。
- `knowledge`：法規文件、切片、向量、對話、訊息與引用來源。

`database/optional/002_optional_rag_schema.sql` 保留為舊版選配 RAG 設計，不會自動執行。新開發以 `knowledge` schema 為準。

## 比賽角色與權限

- `APPRAISER`（估價人員）：建立與編輯案件、估價資料與案件文件。
- `REVIEWER`（審查人員）：執行智慧審查、查看疑點並作成審查決定。
- `INSPECTOR`（稽查人員）：唯讀查看案件、估價、審查結果與稽核履歷。

角色與權限由 Alembic seed 管理。實際使用者與密碼不寫入 migration，等登入流程建立時再以安全方式建立三個示範帳號。

## 修改履歷分工

- `valuation.change_logs`：估價業務欄位級變更，保存估價表、計算與宗地欄位的修改前後值。
- `history.change_logs`：跨模組系統稽核，保存案件、審查、文件、權限與知識資料變更。

同一次操作如果需同時寫入兩表，應共用同一個 `operation_id` UUID，便於稽核時對應。

## MinIO

- API：`http://localhost:<MINIO_API_PORT>`
- Console：`http://localhost:<MINIO_CONSOLE_PORT>`
- `minio-init` 會冪等建立單一 `land-valuation` bucket。

### Object key

案件文件：

```text
land-valuation / cases/{case_id}/{category}/{document_id}/v{version_no}/{stored_filename}
```

`category` 為 `original`、`cadastral-map`、`land-register`、`photos`、`attachments` 或 `generated`。

知識文件：

```text
land-valuation / knowledge/{category}/{document_id}/v{version_no}/{stored_filename}
```

`category` 為 `regulations`、`standards` 或 `manuals`。

PostgreSQL 僅保存 `bucket_name = 'land-valuation'` 與以 `cases/` 或 `knowledge/` 開頭的 `object_key`，不保存 `localhost` URL、endpoint 或 presigned URL。PDF、圖片與附件本體只存 MinIO。

## 基本驗證

```sql
SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('auth', 'valuation', 'review', 'history', 'knowledge')
ORDER BY schema_name;

SELECT table_schema, table_name FROM information_schema.tables
WHERE table_schema IN ('auth', 'valuation', 'review', 'history', 'knowledge')
ORDER BY table_schema, table_name;
```

MinIO 上傳、下載、刪除驗證完成後，應再核對 `valuation.documents` 或 `knowledge.documents` 的 `(bucket_name, object_key)` 能定位同一物件。
