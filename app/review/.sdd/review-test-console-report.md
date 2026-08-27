# Review 測試主控台實作報告

## 範圍

本次所有專案檔案變更均位於 `app/review/**`。未修改 `app/main.py`、`app/api/router.py`、Docker Compose、migration、根目錄 pytest 設定或其他子系統。

## 交付內容

- `router.py`：development-only `/review/test-ui` 路由；production/test 等非 development 環境回傳 404。
- `test_ui/index.html`：單檔 HTML/CSS/JavaScript 作業台，不需 npm 或外部 CDN。
- `demo.py`：`seed`、`revise`、`reset` CLI，連接既有 PostgreSQL 與 MinIO。
- `tests/test_test_ui.py`：頁面環境閘門與功能契約。
- `tests/test_demo.py`：CLI 閘門、固定所有權、PDF、命令、上傳補償與碰撞保護。
- `tests/test_demo_workflow.py`：真實 JWT/API/DB/MinIO 完整流程與 idempotency。

## Demo 資料界線

- username：`review_demo`
- case number：`DEMO-REVIEW-001`
- rule set：`DEMO-REVIEW-RULES`
- knowledge document code：`DEMO-REVIEW-SOURCE`
- 案件物件：`cases/{case_id}/demo/...`
- 法規物件：`knowledge/{document_id}/demo/review-validation-rules.pdf`

固定識別存在但其輔助所有權欄位不符時，reset 回報 `OWNERSHIP_COLLISION` 並 rollback。密碼每次 seed 隨機產生，不寫入 Markdown、Git 或瀏覽器 storage；頁面只保存 JWT 與流程 UUID。

## 手動測試

```powershell
rtk docker compose --env-file .env.example up -d api
rtk docker exec land_valuation_api python -m app.review.demo seed
```

1. 開啟 `http://localhost:8000/api/v1/review/test-ui`。
2. 貼入 seed JSON 的 password 與 case_id，登入。
3. 建立審查案件，執行完整性檢查，確認 `ready=true`。
4. 建立 run，讀取 findings 與 risk summary。
5. 對 HIGH finding 做 `PARTIALLY_ACCEPTED`，案件做 `RETURNED_FOR_REVISION`，狀態改成 `PREPROCESSING`。
6. 終端執行 `rtk docker exec land_valuation_api python -m app.review.demo revise`。
7. 再做完整性檢查與 rerun，確認 run_no=2，舊 run 仍可讀，新 finding 串接 `supersedes_finding_id`。
8. 取得 JSON report，產生並下載 PDF。
9. 測試完執行 `rtk docker exec land_valuation_api python -m app.review.demo reset`。

## 驗證結果

- 完整 Review suite：153 passed，1 個既有 deprecation warning。
- live readiness：PostgreSQL `ok`、MinIO `ok`。
- live OpenAPI：run/rerun responses 均為 `200`、`422`。
- live test UI：HTTP 200。
- Python compile 與 JavaScript syntax：通過。
- 自動化瀏覽器視覺驗收：未完成；瀏覽器控制端無法建立本機執行資源。此限制不影響 API/HTML/JS 契約結果，但仍建議人工確認實際畫面與 PDF 下載互動。

