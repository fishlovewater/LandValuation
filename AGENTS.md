# Project Instructions

## Current phase

目前只建置 PostgreSQL 與 MinIO。
未經要求，不建立 FastAPI、Vue 或 Alembic。

## Storage rules

- PostgreSQL：結構化資料、檔案metadata、法規文字及向量。
- MinIO：PDF、圖片、附件與原始法規文件。
- PostgreSQL不得保存大型PDF或圖片本體。
- MinIO object key不得保存成固定localhost網址。

## Current validation

- PostgreSQL可正常啟動並查詢資料表。
- MinIO可上傳、下載及刪除檔案。
- documents紀錄能正確對應MinIO object。

