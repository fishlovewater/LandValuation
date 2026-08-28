# Demo 測試帳密指令 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在審查工作台登入首頁顯示可直接貼到 PowerShell 的 Demo seed 指令，並提供有成功／失敗回饋的一鍵複製按鈕。

**Architecture:** 沿用既有單檔 `test_ui/index.html`，將固定指令與 Clipboard 操作封裝在既有 testable workbench logic 區段。靜態 pytest 驗證登入頁契約，零相依 Node 測試執行實際複製邏輯；不新增 API 或保存固定密碼。

**Tech Stack:** 原生 HTML/CSS/JavaScript、Node `node:test`、pytest。

## Global Constraints

- 所有修改只位於 `app/review/**`。
- 不新增外部前端依賴、FastAPI route、migration 或固定密碼。
- 指令固定為 `rtk docker exec land_valuation_api python -m app.review.demo seed`。
- `demo seed` 既有 development-only 防護維持不變。

---

### Task 1: 登入首頁 Demo 指令與複製互動

**Files:**
- Modify: `app/review/tests/test_test_ui.py`
- Modify: `app/review/tests/test_ui_behavior.mjs`
- Modify: `app/review/test_ui/index.html`
- Modify: `app/review/CHANGELOG.md`

**Interfaces:**
- Consumes: 瀏覽器 `navigator.clipboard.writeText(text)`。
- Produces: `DEMO_SEED_COMMAND: string` 與 `copyDemoCommand(writeText): Promise<{message: string, error: boolean}>`。

- [ ] **Step 1: 寫入失敗的登入頁契約測試**

在 `test_test_ui.py` 新增：

```python
def test_test_ui_shows_copyable_demo_seed_command(client):
    html = client.get("/api/v1/review/test-ui").text
    assert "取得測試帳密" in html
    assert "rtk docker exec land_valuation_api python -m app.review.demo seed" in html
    assert 'id="copy-demo-command"' in html
    assert "終端機輸出" in html
```

- [ ] **Step 2: 寫入失敗的可執行 Clipboard 行為測試**

擴充 `test_ui_behavior.mjs` 的匯出函式清單，並新增：

```javascript
test("demo seed command is copied with visible success feedback", async () => {
  let copied = "";
  const result = await logic.copyDemoCommand(async (value) => { copied = value; });
  assert.equal(copied, "rtk docker exec land_valuation_api python -m app.review.demo seed");
  assert.deepEqual(result, { message: "指令已複製，請貼到 PowerShell 執行。", error: false });
});

test("clipboard failure keeps a manual-copy fallback", async () => {
  const result = await logic.copyDemoCommand(async () => { throw new Error("denied"); });
  assert.deepEqual(result, { message: "無法自動複製，請手動選取上方指令。", error: true });
});
```

- [ ] **Step 3: 執行聚焦測試並確認紅燈**

Run:

```powershell
rtk docker exec land_valuation_api pytest app/review/tests/test_test_ui.py::test_test_ui_shows_copyable_demo_seed_command -q
rtk proxy node --test app/review/tests/test_ui_behavior.mjs
```

Expected: pytest 因首頁缺少「取得測試帳密」而失敗；Node 因 `copyDemoCommand` 尚未定義而失敗。

- [ ] **Step 4: 加入最小登入頁與複製實作**

在登入卡片加入：

```html
<section class="demo-login-help" aria-labelledby="demo-login-help-title">
  <p class="kicker" id="demo-login-help-title">取得測試帳密</p>
  <p>複製到 PowerShell 執行；終端機輸出會包含 username 與當次產生的 password。</p>
  <code id="demo-seed-command">rtk docker exec land_valuation_api python -m app.review.demo seed</code>
  <button class="btn secondary small" id="copy-demo-command" type="button">複製指令</button>
  <p id="copy-demo-feedback" role="status" aria-live="polite"></p>
</section>
```

在 testable logic 區段加入：

```javascript
const DEMO_SEED_COMMAND="rtk docker exec land_valuation_api python -m app.review.demo seed";
async function copyDemoCommand(writeText){
  try{
    await writeText(DEMO_SEED_COMMAND);
    return{message:"指令已複製，請貼到 PowerShell 執行。",error:false};
  }catch{
    return{message:"無法自動複製，請手動選取上方指令。",error:true};
  }
}
```

按鈕事件將 `navigator.clipboard.writeText.bind(navigator.clipboard)` 傳入函式，並把回傳訊息顯示在 `copy-demo-feedback`；失敗時不隱藏可手動選取的 `<code>`。

- [ ] **Step 5: 執行聚焦測試並確認綠燈**

Run:

```powershell
rtk docker cp app\review land_valuation_api:/app/app/
rtk docker exec land_valuation_api pytest app/review/tests/test_test_ui.py::test_test_ui_shows_copyable_demo_seed_command -q
rtk proxy node --test app/review/tests/test_ui_behavior.mjs
```

Expected: pytest 通過；Node 6 tests 通過。

- [ ] **Step 6: 更新變更紀錄並執行完整驗證**

在 `CHANGELOG.md` 的 2026-08-28 工作台段落記錄登入首頁 Demo seed 指令與 Clipboard 回饋。執行：

```powershell
rtk docker exec land_valuation_api pytest app/review/tests -q
rtk proxy node --test app/review/tests/test_ui_behavior.mjs
rtk proxy node -e "const fs=require('fs');const h=fs.readFileSync('app/review/test_ui/index.html','utf8');const a=h.indexOf('<script>')+8;const b=h.indexOf('</script>',a);new Function(h.slice(a,b));"
rtk git diff --check
```

Expected: pytest 無失敗；Node 6 tests 通過；JavaScript 語法與 Git whitespace 檢查 exit 0。

- [ ] **Step 7: 提交實作**

```powershell
rtk git add app/review
rtk git commit -m "feat(review): show demo seed command on login"
```
