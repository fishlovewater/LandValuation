# Review 工作台：檢核進度與未儲存提醒實作規劃

## 目標

在不新增資料表、背景工作服務或前端框架的前提下，完成兩項工作台功能：

1. 以實際完成的 API 階段顯示檢核進度，不使用計時器模擬百分比。
2. 使用者有尚未儲存的審查內容時，在內容可能消失前提出提醒。

所有變更限制於 `app/review/**`。保留既有
`POST /api/v1/review/workbench/cases/{review_id}/start` 相容性，不修改資料庫結構。

## 已確認的設計

### 檢核進度

進度代表「已完成的流程里程碑」，不是逐筆公式的即時運算量：

| 進度 | 階段 | 完成條件 |
|---:|---|---|
| 0% | 準備檢核 | 使用者送出開始審查／複查 |
| 25% | 完整性檢查完成 | preflight API 已回應；若缺件則停在此處 |
| 75% | 規則檢核完成 | Run 或 rerun API 已成功完成 |
| 90% | 疑點與風險完成 | 案件 detail 已重新載入 |
| 100% | 工作台更新完成 | summary 已重新載入並呈現 |

不以 `setTimeout`、亂數或動畫時間推進百分比。API 發生錯誤時保留最後一個已完成階段，並顯示失敗訊息。

### 未儲存提醒

追蹤以下輸入：

- 疑點決策類型
- 疑點決策理由
- 「另訂正式內容」的正式採用值
- 案件決策類型
- 案件決策理由

只有值相對於初始快照發生變化才算 dirty；改回原值後應恢復 clean。成功儲存後清除對應表單的 dirty 狀態，API 失敗時不得清除。

提醒涵蓋：

- 瀏覽器重新整理、關閉分頁或離開頁面
- 切換案件
- 切換會重新渲染案件內容的頁籤
- 登出
- 開始審查或執行複查
- 產生報告後重新載入案件內容
- Demo 修正版送出後重新載入案件內容

提醒文字：`尚有未儲存的審查內容，確定離開嗎？`

## 實作工作

### Task 1：將開始審查拆成可觀察的 preflight 階段

**修改檔案**

- `app/review/workbench_service.py`
- `app/review/workbench_schemas.py`
- `app/review/router.py`
- `app/review/tests/test_workbench_service.py`
- `app/review/tests/test_workbench_api.py`

**步驟**

1. 先新增失敗測試，涵蓋：
   - `RECEIVED` 案件執行 preflight 後轉為 `READY_FOR_REVIEW` 或 `PENDING_MATERIALS`。
   - `RETURNED_FOR_REVISION`、`SUPPLEMENT_REQUIRED` 案件可先轉為 `PREPROCESSING` 再檢查完整性。
   - preflight 通過時不建立 Run。
   - preflight 被阻擋時回傳缺件與受影響規則，且不建立 Run。
   - 既有 `/start` 仍可一次完成 preflight 與 Run，避免破壞既有呼叫端。
2. 在 `WorkbenchService` 抽出共用 preflight 方法，集中處理狀態轉換及 `check_completeness`。
3. 新增 `WorkbenchPreflightRead`，結果只允許 `READY` 或 `BLOCKED`，並帶回 completeness。
4. 新增端點：
   `POST /api/v1/review/workbench/cases/{review_id}/start/preflight`。
5. 讓既有 `start()` 重用 preflight 方法，再建立首次 Run 或 rerun；不得複製兩套狀態轉換。
6. 執行目標測試：

```powershell
rtk pytest app/review/tests/test_workbench_service.py app/review/tests/test_workbench_api.py -q
```

### Task 2：工作台顯示實際里程碑進度

**修改檔案**

- `app/review/test_ui/index.html`
- `app/review/tests/test_ui_behavior.mjs`
- `app/review/tests/test_test_ui.py`
- `app/review/tests/test_workbench_demo.py`

**步驟**

1. 先替純前端邏輯新增失敗測試：
   - 各階段只可前進至 0、25、75、90、100。
   - BLOCKED 停在 25，且不呼叫 Run。
   - API 失敗保留最後完成階段。
   - 不存在計時器模擬進度。
2. 在案件操作區加入原生 `<progress max="100">`、階段文字與 `aria-live` 狀態。
3. 將目前單次 `/start` UI 呼叫改為：
   - 呼叫 `/start/preflight`，成功後設為 25%。
   - 若 BLOCKED，重新載入 detail/summary 後停止，不建立 Run。
   - 首次執行呼叫 `/review/cases/{review_id}/runs`；有歷史 Run 時呼叫 `/review/cases/{review_id}/rerun`。
   - Run 成功後設為 75%，detail 完成後設為 90%，summary 完成後設為 100%。
4. 全程沿用既有 `busy` 防重複送出；任何階段失敗都恢復按鈕操作能力。
5. 保留 `/workbench/.../start` 供 API 與既有整合測試使用，但工作台 UI 改用分段流程。
6. 執行目標測試：

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk pytest app/review/tests/test_test_ui.py app/review/tests/test_workbench_demo.py -q
```

### Task 3：建立可比較初始值的 dirty-state

**修改檔案**

- `app/review/test_ui/index.html`
- `app/review/tests/test_ui_behavior.mjs`

**步驟**

1. 先新增失敗測試，涵蓋：
   - 修改後 dirty。
   - 改回初始值後 clean。
   - 不同 finding 的 dirty 狀態互不覆蓋。
   - 成功儲存只清除對應 finding。
   - 儲存失敗仍 dirty。
2. 在 `state` 中保存表單初始快照與 dirty keys；key 至少區分 `finding:{id}` 與 `case:{review_id}`。
3. 使用事件委派監聽 `input` 與 `change`，每次變更重新序列化目前表單並與初始快照比較。
4. `renderDetail()` 建立表單後登錄初始快照，但不得在未經確認的重新渲染前直接清空 dirty 狀態。
5. 疑點或案件決策 API 成功後先清除相對應 dirty key，再重新載入 detail；catch 路徑不清除。
6. 執行：

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

### Task 4：攔截瀏覽器離開與工作台內部導覽

**修改檔案**

- `app/review/test_ui/index.html`
- `app/review/tests/test_ui_behavior.mjs`
- `app/review/tests/test_test_ui.py`

**步驟**

1. 先新增失敗測試，涵蓋：
   - 有 dirty 狀態時 `beforeunload` 會阻擋。
   - clean 狀態不阻擋。
   - 內部導覽選擇「留下」時不執行原動作。
   - 選擇「離開」時清除相關 draft 並執行原動作。
2. 新增 `hasUnsavedChanges()` 與 `confirmDiscardChanges()` 純函式／薄封裝，所有內部操作共用同一判斷。
3. 註冊 `beforeunload`；僅在 dirty 時呼叫 `preventDefault()` 並設定 `returnValue`。
4. 在切換案件、切換頁籤、登出、開始檢核、產生報告與 Demo revise 前套用 guard。
5. 使用者取消離開時保留輸入值、目前案件、頁籤與展開狀態。
6. 不攔截不會銷毀表單的操作，避免過度提醒。
7. 執行：

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk pytest app/review/tests/test_test_ui.py -q
```

### Task 5：整體回歸與人工驗收

1. 完整測試必須使用目前工作區原始碼，不直接依賴可能過期的常駐 API image：

```powershell
rtk docker compose --env-file .env.example run --rm --no-deps -v "C:\Users\User\project\LandValuationAssistant:/app" api pytest tests app/review/tests -q
```

2. 人工驗收流程：
   - 缺件案件執行審查：進度停在 25%，顯示缺件，沒有新增 Run。
   - 完整案件首次審查：依序顯示 0、25、75、90、100，且只新增一個 Run。
   - 退回修正後複查：相同階段完成，Run 編號加一，舊 Run 保留。
   - 修改疑點理由後切換案件：選擇留下時內容不消失。
   - 再次切換並選擇離開：正常開啟新案件。
   - 修改後重新整理頁面：瀏覽器顯示原生離開提醒。
   - 儲存成功後切換案件：不再提醒。
   - 模擬儲存 API 失敗：內容保留且仍會提醒。
3. 最後確認 `git diff` 只包含 `app/review/**`，不提交、不合併、不推送，除非另有指示。

## 驗收標準

- 進度只由完成的 API 階段推進，沒有假百分比或定時器。
- 完整性未通過時絕不建立 Run。
- 首次檢核與複查都只建立一個新 Run，並保留既有 run-scoped 結果。
- 既有 `/workbench/.../start` 行為保持相容。
- 尚未儲存的內容在所有會銷毀表單的離開路徑前都會提醒。
- 改回原值或成功儲存後不出現多餘提醒。
- 不新增資料表、migration、背景 worker 或新前端依賴。
- 完整測試通過，且無本功能造成的新 warning。
