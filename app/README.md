# FastAPI 共用後端骨架

## 模組

- `main.py`：FastAPI application、lifespan、routers 與 middleware。
- `core/`：環境設定、JWT/密碼、錯誤、request ID 與 logging。
- `db/`：SQLAlchemy async engine、session 與 transaction。
- `storage/`：MinIO client、object key 檢查與檔案操作。
- `auth/`：登入、使用者讀取、JWT 與 RBAC dependencies。
- `health/`：live/ready 健康檢查。
- `api/`：統一 `/api/v1` router。

FastAPI 不執行 `Base.metadata.create_all()`，也不自動修改 schema。所有資料庫結構變更仍由 Alembic 負責。

## PostgreSQL 寫入

Router 透過 `DbSession` 取得每個 request 專用的 `AsyncSession`：

```python
from app.auth.dependencies import DbSession

@router.post("")
async def create_item(payload: ItemCreate, session: DbSession):
    item = Item(**payload.model_dump())
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item
```

Request 正常完成後 `get_db_session()` 自動 commit；出現例外時自動 rollback。需要在 commit 前取得資料庫預設值或檢查約束時，使用 `flush()`。

## PostgreSQL 讀取

```python
from sqlalchemy import select

@router.get("/{item_id}")
async def get_item(item_id: UUID, session: DbSession):
    item = await session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise ResourceNotFoundError("資料")
    return item
```

多筆資料使用 `session.scalars(select(...))`，並在業務 API 中加入分頁、排序與權限篩選。

## MinIO 寫入

1. API 先產生 `document_id` 與 object key。
   - 新邏輯文件產生新 `document_group_id`。
   - 上傳新版本時沿用原 `document_group_id`，改用新 `document_id` 與遞增的 `version_no`。
2. 使用 `StorageService.upload()` 上傳檔案到 `land-valuation`。
3. Storage service 回傳 `bucket_name`、`object_key`、SHA-256、檔案大小與 ETag；API 應完整寫入 `mime_type`、`file_size_bytes` 與 `storage_etag`。
4. API 將 metadata 寫入 `valuation.documents` 或 `knowledge.documents`。
5. 若 PostgreSQL 寫入失敗，API 應呼叫 `StorageService.delete()` 清除剛上傳的孤兒物件。

案件文件 key：

```text
cases/{case_id}/{category}/{document_id}/v{version}/{filename}
```

知識文件 key：

```text
knowledge/{category}/{document_id}/v{version}/{filename}
```

## MinIO 讀取

API 先從 PostgreSQL documents 表取得 `bucket_name` 與 `object_key`，驗證使用者有權限後，再選擇：

- `StorageService.download()`：由 FastAPI 串流回傳檔案。
- `StorageService.presigned_download_url()`：回傳短效 MinIO 下載網址。

資料庫不保存檔案內容或長效 URL。

## 授權

```python
from fastapi import Depends
from app.auth.dependencies import require_permissions

@router.post("")
async def create_case(
    user=Depends(require_permissions("case.create")),
):
    ...
```

JWT 只識別 `user_id`。每次受保護的 request 都會從 PostgreSQL 重新讀取使用者、角色與權限，因此停用帳號或調整角色會立即生效。
