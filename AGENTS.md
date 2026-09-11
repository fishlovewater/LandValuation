# Project Instructions

## Current phase

目前專案已進入整合與 Demo 收尾階段，包含 FastAPI、Vue 3、Alembic、PostgreSQL 與 MinIO。
主要模組包含估價流程、文件上傳與 AI/OCR 擷取、送審、智慧審查、案件歷程與 AI 助手。

修改現有功能時優先維持既有 API contract、RBAC 邊界與資料庫 migration 相容性；不要因舊文件描述而移除已存在的 FastAPI、Vue 或 Alembic 功能。

## Storage rules

- PostgreSQL：結構化資料、檔案metadata、法規文字及向量。
- MinIO：PDF、圖片、附件與原始法規文件。
- PostgreSQL不得保存大型PDF或圖片本體。
- MinIO object key不得保存成固定localhost網址。

## Current validation

- PostgreSQL可正常啟動並查詢資料表。
- MinIO可上傳、下載及刪除檔案。
- documents紀錄能正確對應MinIO object。
- FastAPI 由 Alembic migration 管理 schema，主要業務 API 已存在。
- Vue 3 frontend 已包含估價、審查、History、AI Assistant 與角色導向路由。
- 一般修改完成後至少執行相關 pytest / Vitest，前端變更另執行 `npm run build`。
- `docker-compose.demo.yml` 是競賽／展示用途；Demo-only 開關不可默認開在一般 production 部署。



<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
