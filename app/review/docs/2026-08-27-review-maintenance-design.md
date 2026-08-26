# Review 子系統維護設計

## 目的

本次只整理 `app/review` 第二子系統，不改動其他業務子系統。修正同步執行的 review run API 回應契約，並補齊可追溯的變更紀錄。

## 核准範圍

- `POST /api/v1/review/cases/{review_id}/runs` 在同一個 request 內完成檢核並回傳完成結果，因此成功狀態碼改為 `200 OK`。
- `POST /api/v1/review/cases/{review_id}/rerun` 同樣同步完成，因此成功狀態碼改為 `200 OK`。
- 先修改既有 API 測試，使其因目前仍回傳 `202` 而失敗，再修改 router 讓測試通過。
- 新增 `app/review/CHANGELOG.md`，依既有 Git commit 與 `.sdd/progress.md` 記錄先前及本次動作。
- 更新 `app/review/OUTSIDE_REVIEW_CHANGES.md` 與 `app/review/.sdd/` 紀錄，使文件反映 migration `0006`、`0007` 及本次維護的實際狀態。
- 將目前未追蹤的 `app/review/.sdd/` 工作紀錄一併納入版本控制。

## 明確不做

- 不修改根目錄 `pytest.ini`。
- 不修改 `app/review` 以外的程式、設定、migration 或文件。
- 不建立背景工作佇列；run 與 rerun 維持同步執行。
- 不新增規則、Bedrock 串接、外部補件通知或其他子系統功能。

## 測試與驗收

- 明確執行 `pytest -q app/review/tests`，不依賴根目錄 pytest 的測試收集設定。
- run 與 rerun API 測試必須驗證 `200 OK`，回傳內容仍為已完成的 `ValidationRunRead`。
- Review 完整測試不得出現失敗。
- 提交前確認所有本次修改都位於 `app/review/**`。

## 提交與紀錄

設計文件先單獨提交。實作完成後，將 router、測試、CHANGELOG、外部變更紀錄與既有 `.sdd` 工作紀錄放入後續 Review 維護提交。
