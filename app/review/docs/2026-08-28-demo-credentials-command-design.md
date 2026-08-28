# Demo 測試帳密指令設計

## 目標

讓開發測試人員在審查工作台登入首頁直接複製 Demo seed 指令，到 PowerShell 執行後取得當次產生的測試帳號與密碼。

## 畫面與互動

- 登入卡片在登入表單上方顯示「取得測試帳密」區塊。
- 區塊顯示完整指令：

  ```powershell
  rtk docker exec land_valuation_api python -m app.review.demo seed
  ```

- 「複製指令」按鈕使用瀏覽器 Clipboard API 複製完整指令。
- 複製成功後，按鈕文字暫時顯示「已複製」；複製失敗時顯示可理解的錯誤訊息，指令本身仍可手動選取。
- 說明文字明確指出：將指令貼到 PowerShell 執行，終端機輸出會包含 `username` 與當次隨機產生的 `password`。

## 安全與範圍

- 不在 HTML 中保存固定密碼，也不新增回傳明文密碼的 HTTP API。
- `demo seed` 既有 development-only 防護維持不變。
- 只修改 `app/review/test_ui/index.html`、對應測試與 `app/review` 文件。

## 驗收

- 登入首頁可看見完整且正確的 Demo seed 指令。
- 點擊複製按鈕後，Clipboard 收到完全相同的指令。
- 複製成功與失敗都有使用者可見回饋。
- 現有登入、工作台及後端測試不受影響。
