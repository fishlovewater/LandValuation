# LandValuationAssistant Frontend

Vue 3 + TypeScript + Vite 前端，提供角色導向的土地估價、智慧審查、案件歷程與 AI Assistant 工作流程。

## 開發

```powershell
npm install
npm run dev
```

開發模式會顯示 Demo 快速登入按鈕，方便直接以估價人員、審查人員或案件查詢角色進入系統。

## 驗證

```powershell
npm test -- --run
npm run build
```

## Demo build

```powershell
npm run build:demo
```

`build:demo` 使用 Vite `demo` mode，會顯示三個一鍵登入按鈕。登入後 Header 會標示 `DEMO`，使用者選單也可直接在估價人員、審查人員、案件查詢三個展示角色間切換，不必先登出。後端必須同步開啟 `DEMO_QUICK_LOGIN_ENABLED=true`；專案的 `docker-compose.demo.yml` 已設定此 Demo-only 開關。

一般 `npm run build` 不會因 Demo mode 自動開啟一鍵登入；若部署流程需要自行控制，也可在 build environment 設定 `VITE_DEMO_QUICK_LOGIN=true`。

本機完整 Demo 後端建議從 repository root 使用：

```powershell
.\scripts\demo-up.ps1
```

腳本使用獨立 `landvaluation-persistent-demo` Compose project，會等待 API ready 並在安全的 pre-submission 狀態準備三個 Demo 帳號與示範案件；已送審／已進 Review 的 Demo 不會被自動 reseed。後端 ready 後回到 `frontend/` 執行 `npm run dev` 即可。若映像已建置，可用 `..\scripts\demo-up.ps1 -SkipBuild`。

## 主要畫面

- 估價案件 Dashboard 與 Wizard
- 文件上傳、PDF／圖片／XLSX／DOCX 文字預覽與 AI/OCR extraction
- 擷取候選資料確認與估價表單
- 正式檢核、PDF 產出與送審
- Review Dashboard / Workbench / Result
- History 查詢、文件預覽與版本比較
- Persistent AI Assistant drawer