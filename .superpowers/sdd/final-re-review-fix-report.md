# Final Re-review Fix Report

日期：2026-09-05

分支：`feature/integrate-valuation-review`

本輪只修正新版回件文件與目前 latest Submission 不一致時仍可能啟動新版重檢
的 Important finding；未 push、merge、branch cleanup 或清理 `.serena/`。

## 修正內容

- `CorrectionService.recheck()` 在確認 latest Submission 已不同於原 Run 後，
  以 Review 與 Case ownership 條件讀取該 Submission 的
  `source_report_document_id`。
- 若 latest Submission 不存在或其 `source_report_document_id` 不等於
  `correction_request.response_document_id`，回傳明確的
  `409 CORRECTION_RECHECK_DOCUMENT_MISMATCH`（不存在或 ownership 錯誤則為
  `409 CORRECTION_RECHECK_SUBMISSION_INVALID`），維持 request 在
  `RESUBMITTED`，不進入 `RECHECKING`、完整性檢查或 Review Run。
- `ReviewRepository.get_submission_provenance_by_id()` 增加讀取
  `source_report_document_id`；未新增 workflow schema，精確 document UUID
  仍代表文件版本。

## TDD 證據

新增測試情境：correction response 是 v2，但 Review 的 latest Submission
指向 v3 文件。測試要求 409、request 維持 `RESUBMITTED`、沒有 flush，且
`check_completeness()` 不得被呼叫。

- RED：尚未加入 guard 時，直接以 `asyncio.run` 執行測試會進入
  `check_completeness()`，觸發 `AssertionError: recheck must reject before
  starting a Run`。
- GREEN：加入 guard 後，該測試與原有「需要較新 Submission」測試均以
  `asyncio.run` 執行成功；同檔 6 個 async locking coroutine 均成功。

## 可用環境驗證

- `node --test app/review/tests/test_ui_behavior.mjs`：**38 passed, 0 failed**。
- `python -m compileall -q -f app tests`（`PYTHONPYCACHEPREFIX` 指向可寫暫存）：
  成功，無編譯錯誤。
- `git diff --check`：成功，無 whitespace error。
- Host `pytest` 無法提供有效後端結果：缺少 `pytest-asyncio`，async 測試會被
  skip；其他正式報告測試的收集也受本機缺少 `fastapi` 阻擋。因此不宣稱
  pytest/backend suite 通過。
- Docker 整合測試無法執行：Docker Desktop service 未啟動，Docker API
  pipe `npipe:////./pipe/docker_engine` 不存在。故本輪未取得 Docker
  focused/integration/full-suite 或實際 SQLAlchemy session 證據。

## 待環境恢復後

重新執行 correction focused pytest、Review backend suite、完整 isolated
suite 與 Docker residue check，特別確認實際 repository provenance query、
transaction rollback，以及 mismatch 時沒有新 Run、finding 或歷程紀錄。
