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

## 本輪追加：Correction draft provenance 修正

日期：2026-09-05

上一輪的 recheck 文件綁定修正已保留。本輪處理另一個 Important：
`CorrectionService.create_draft()` 原本無論 Review 是否有
`latest_submission_id` 都讀 live 最新 `original` 文件，可能讓 Submission 1
的修正通知錯綁後來的 v3。現在有 pointer 的 Review 會依
`review_id + case_id` 讀取該 Submission，並使用其
`source_report_document_id` 對應的文件 ID、版本與 `document_group_id`；
pointer 不存在時才保留既有 live 最新文件 fallback。Submission 或來源文件
不存在、跨 Review/Case 或無法完成 ownership join 時，會以明確的
`409 CORRECTION_BASE_DOCUMENT_SUBMISSION_INVALID` fail closed。

`ReviewRepository.get_submission_provenance_by_id()` 現在 join
`valuation.documents` 取得來源文件 metadata，未限制 `is_active`，因此已被
新版取代的歷史來源文件仍能作為 correction base；同時要求來源文件屬於同一
Case。未新增 schema、UI 或 workflow 狀態。

### 本輪 TDD 證據

- RED：新增 pointer-backed draft 測試後，在尚未分流的實作上以
  `asyncio.run` 執行，確實在 `request.base_document_id == source_document_id`
  斷言失敗，拿到 live v3 而非 Submission source v1。
- GREEN：加入 pointer/fallback 分流後，`tests/test_correction_service_locking.py`
  的 9 個 async coroutine 直接執行均成功；另涵蓋 pointer 缺少 owned source
  document 時的 409 fail-closed。
- 整合測試已擴充同一 handoff：live original v3、complete report v2、
  Submission 2、同 group 回件登記、新 Review Run、`RESOLVED` correction item
  與 `CORRECTION_RECHECKED` history。

### 本輪環境驗證與限制

- `node --test app/review/tests/test_ui_behavior.mjs`：38 passed, 0 failed。
- `python -m compileall -q -f app tests`（`PYTHONPYCACHEPREFIX` 指向可寫暫存）：
  成功，無編譯錯誤。
- `git diff --check`：成功，無 whitespace error。
- `python -m pytest tests/test_correction_service_locking.py -q`：9 skipped；
  Host 缺少 `pytest-asyncio`，因此 async pytest 結果不可視為通過；直接
  coroutine 驗證才是本輪 unit 證據。
- `python -m pytest tests/integration/test_valuation_review_handoff.py
  --collect-only -q`：收集前即因 Host 缺少 `pwdlib` 的
  `ModuleNotFoundError` 中止。
- Docker Desktop `com.docker.service` 仍為 `Stopped`；`docker version` 無法
  連線 `npipe:////./pipe/docker_engine`（permission denied）。因此本輪沒有
  實際 PostgreSQL/SQLAlchemy session、focused integration、backend/full-suite
  或 transaction 證據，不宣稱整合測試通過。
