# Review 測試主控台實作計畫

> 執行範圍：僅修改 `app/review/**`。若實作需要修改其他路徑，立即停止並先取得同意。

## 目標與驗收

- development 環境可由 `GET /api/v1/review/test-ui` 開啟手動測試頁；非 development 回傳 404。
- `python -m app.review.demo seed|revise|reset` 可建立、修正版與清除固定 Demo 資料，非 development 拒絕執行。
- Demo 使用真實 JWT、PostgreSQL、MinIO 與既有 Review API，不繞過登入或權限。
- seed 可重複執行且不累積資料；reset 僅清除固定 Demo 所有權範圍；MinIO 或資料庫失敗不留下半套資料。
- 手動頁可完成登入、建立審查、完整性檢查、run、findings、risk、finding/case decision、revise 後 rerun、JSON/PDF 報告。
- `app/review/tests` 全部通過，並更新 `CHANGELOG.md` 與 `.sdd` 實作紀錄。

## Task 1：測試頁路由與環境閘門

**檔案**

- 新增：`app/review/tests/test_test_ui.py`
- 修改：`app/review/router.py`
- 新增：`app/review/test_ui/index.html`

**TDD 步驟**

1. 先寫測試：development 回傳 200/HTML，production 回傳 404，且無須 JWT。
2. 執行 `pytest -q app/review/tests/test_test_ui.py`，確認因路由不存在而失敗。
3. 在 Review router 新增固定 `/test-ui` 路由，讀取 `get_settings().app_env`；非 development 主動回傳 404。
4. 建立最小 HTML 骨架，再執行聚焦測試至通過。

## Task 2：Demo CLI 安全邊界與資料生命週期

**檔案**

- 新增：`app/review/demo.py`
- 新增：`app/review/tests/test_demo.py`

**TDD 步驟**

1. 先測環境閘門、命令解析、固定所有權常數與 JSON 輸出。
2. 測 reset 的範圍：固定 username、case number、文件識別；不存在時成功 no-op，非 Demo sentinel 不得被刪除。
3. 實作同步 CLI：`seed`、`revise`、`reset`；所有 SQL 使用參數化查詢與單一交易。
4. seed：先安全 reset，建立隨機密碼與 REVIEWER 關聯、案件、宗地、F01、三份案件文件、v1 抽取、法規文件、published rule version、兩條 active 規則；PDF 寫入 MinIO，metadata 寫 PostgreSQL。
5. revise：僅針對固定 Demo 案件建立 v2 original 文件與新 verified official 欄位；停用 v1 original，但保留既有 review/run/finding/decision。
6. reset：先蒐集固定 Demo 的 object keys 與 UUID，再依外鍵順序刪除 Review、validation、extraction、case、rule、knowledge、user 資料；最後刪除已確認的 MinIO objects。
7. 任一步驟失敗時 rollback DB；已上傳但尚未提交的 object 做補償刪除。
8. 執行聚焦測試，包含連續兩次 seed、revise 保留 v1 歷史、兩次 reset、非 Demo sentinel 保留與 MinIO 對應。

## Task 3：完整手動測試介面

**檔案**

- 修改：`app/review/test_ui/index.html`
- 視需要修改：`app/review/tests/test_test_ui.py`

**介面與行為**

1. 採單檔 HTML/CSS/JavaScript，不新增 npm、框架或外部資源。
2. 使用「公務審查作業台」視覺：紙張底色、深墨藍、朱紅狀態色、清楚步驟欄與證據紀錄，不使用裝飾性漸層。
3. 提供五段流程：連線/登入、案件/完整性、run/findings/risk、decisions/rerun、JSON/PDF。
4. API 呼叫一律走同 origin `/api/v1`；JWT 放 Authorization header；token、review_id、run_id、finding_id 存 `sessionStorage`。
5. 每次操作顯示 method、path、HTTP status、耗時、格式化回應；401/403/404/409/422/500 顯示可理解提示。
6. 提供可鍵盤操作的表單、明確 label/focus、窄螢幕單欄布局與 reduced-motion 支援。

## Task 4：真實流程與瀏覽器驗證

**檔案**

- 視需要新增：`app/review/tests/test_demo_workflow.py`

**驗證步驟**

1. 執行 Review 完整測試。
2. 以 `.env.example` 重建並啟動 API，確認 readiness 與 live OpenAPI run/rerun 皆為 200。
3. 在容器執行 `python -m app.review.demo seed`，取得一次性密碼與 case_id。
4. 用瀏覽器依序完成登入、建立審查、完整性、run、findings/risk、決策、JSON/PDF。
5. 執行 `revise`，在頁面 rerun，確認 run 2 與 supersedes/history。
6. 執行 `reset`，確認 Demo DB/MinIO 清空且非 Demo 資料不受影響。

## Task 5：紀錄與提交

**檔案**

- 修改：`app/review/CHANGELOG.md`
- 新增：`app/review/.sdd/review-test-console-report.md`
- 新增：`app/review/.sdd/review-test-console-progress.md`

**步驟**

1. 記錄功能邊界、RED/GREEN 指令、完整驗證結果、手動測試命令與已知限制。
2. 檢查 `git diff --check`（只針對本次 live files）、`git status` 與變更路徑。
3. 僅 stage `app/review/**`，依功能建立可回溯 commits；不得混入其他子系統。

