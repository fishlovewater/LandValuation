# Review 測試主控台進度紀錄

## 2026-08-27

1. 確認在既有 `feature/review` 分支作業，基線為 141 passed、1 warning。
2. 建立並提交設計：`29e6d96`。
3. 建立並提交實作計畫：`7a21cb7`。
4. 以 TDD 建立 development-only test UI route；RED 1 failed，GREEN 2 passed。
5. 以 TDD 建立 Demo CLI；RED 6 failed，公開契約 GREEN 6 passed。
6. 第一次真實 idempotency 測試抓到所有權查詢 placeholder 參數順序錯誤；修正後完整工作流 2 passed。
7. 補上 MinIO 上傳補償與固定 username 碰撞 fail-closed 測試；聚焦結果 12 passed。
8. 完成五段式手動測試頁與 request evidence log；HTML 契約 2 passed、JavaScript syntax 通過。
9. 完整 Review suite 153 passed、1 warning，建立功能提交 `bd78110`。
10. 使用 `.env.example` 重建 API image；live readiness、OpenAPI 200 契約與 test UI 200 均確認。
11. 建立新 Demo 資料供人工測試；一次性密碼只在 CLI/交付訊息顯示，不寫入版本控制。
12. 瀏覽器控制端因本機執行資源路徑錯誤無法連線，標記為尚未完成自動化視覺驗收，不將其描述為通過。

