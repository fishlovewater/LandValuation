# Review 正式採用內容與單一核定設計

## 1. 目標

將抽象的「採納疑點／部分採納／不採納」改成審查人員可直接理解的「本項最後採用哪個內容」，並把「核定通過」與「完成審查」合併為一次、不可分割的案件操作。

本設計解決以下問題：

- 「部分採納」無法直接說明最後採用的是哪個值。
- 「採納疑點」容易被誤解為只承認問題存在，未表明正式採用內容。
- 「核定通過」與「完成審查」同時顯示，但目前沒有第二位簽核人或獨立行政結案程序。
- 現行核定門檻只檢查部分高風險狀態，未要求最新 Run 的所有疑點均有明確處理結果。

## 2. 範圍與限制

- 修改範圍限於 `app/review/**`。
- 沿用既有 Finding decision 值、`after_value` JSON 與案件 decision API；不新增 migration。
- 不修改 Valuation、Document、Auth 或其他子系統。
- 正式採用內容記錄在 Review decision 中，不回寫或覆蓋原始查估文件。
- 既有 `APPROVED`、`REVIEW_COMPLETED` 與歷史 Finding decision 必須維持可讀。

## 3. 疑點決策畫面

疑點展開後，將決策欄標題改為「本項最後採用哪個內容？」。畫面同時顯示原申報內容與系統建議內容，提供以下選項：

| 畫面選項 | 既有 decision 值 | 正式採用內容 |
| --- | --- | --- |
| 維持原申報內容 | `REJECTED` | 原申報內容 |
| 採用系統建議內容 | `ACCEPTED` | 系統建議內容 |
| 另訂正式內容 | `PARTIALLY_ACCEPTED` | 審查人員輸入內容 |
| 資料不足，要求補件 | `REQUIRES_SUPPLEMENT` | 無正式採用內容 |

「另訂正式內容」被選取時才顯示「正式採用內容」輸入框；切換到其他選項時隱藏並清除自訂輸入。所有選項都必須填寫決策理由。

畫面不得再以「部分採納」作為主要操作文字，但既有歷史資料仍可依 decision 與 `after_value` 顯示為可讀的正式採用結果。

## 4. 決策資料

三種有正式採用內容的選項都在 `after_value` 保存一致結構：

```json
{
  "selection_source": "REPORTED | SYSTEM | REVIEWER",
  "field_path": "comparables[0].adjustment_rate",
  "value": "-7"
}
```

- `REPORTED`：取 Finding 的原申報內容。
- `SYSTEM`：依 Finding 類型取系統調整率、系統級距或其他系統建議內容。
- `REVIEWER`：取審查人員在「正式採用內容」欄位輸入的值。
- `REQUIRES_SUPPLEMENT` 不建立正式採用內容，維持待處理狀態。

後端必須從該 Finding 取得原申報與系統建議內容，不信任前端自行傳入的原值或系統值。只有 `REVIEWER` 的自訂內容由前端提供。

## 5. 疑點是否完成

最新 Run 的 Finding 依下列規則判定：

- `ACCEPTED`：已有正式採用內容，視為完成。
- `REJECTED`：已有正式採用內容，視為完成。
- `PARTIALLY_ACCEPTED`：具有非空白的正式採用內容時視為完成。
- `OPEN`、`REQUIRES_SUPPLEMENT`、`EXPERT_REVIEW`：視為尚未完成。

核定門檻必須檢查最新 Run 的每一筆 Finding，不因風險為 MEDIUM 或 LOW 而略過。舊 Run 的疑點與決策保留在歷程中，但不阻擋目前案件。

## 6. 案件操作

工作台的案件決策只顯示：

- 退回修正。
- 要求補件。
- 核定並完成審查。

不再提供獨立的「核定通過」與「完成審查」選項。「核定並完成審查」在同一筆資料庫交易中：

1. 鎖定 Review 並重新取得最新 Run 與目前疑點狀態。
2. 執行核定門檻檢查。
3. 建立一筆 `APPROVED` 案件 decision，保留決策理由與最新 Run 識別。
4. 將 Review 狀態直接設為 `REVIEW_COMPLETED`。
5. 設定 `completed_at`。

不得由前端依序送出 `APPROVED` 與 `REVIEW_COMPLETED` 兩次請求，以免只完成一半。既有 API 的 `REVIEW_COMPLETED` 值保留供歷史相容，但不再出現在工作台選單。

## 7. 核定門檻與阻擋提示

同時符合以下條件才可執行「核定並完成審查」：

- 存在最新 Run，且 Run 已成功完成。
- 文件完整性通過，沒有未解決缺件。
- 最新 Run 的每一筆 Finding 均已作成決策。
- 沒有 `OPEN`、`REQUIRES_SUPPLEMENT` 或 `EXPERT_REVIEW` Finding。
- 每個需要正式採用內容的 decision 都有可用值。
- 案件決策理由不是空白。

前端依工作台詳情預先停用按鈕並列出阻擋原因，例如「尚有 2 項疑點未決策」或「仍有 1 項要求補件」。後端仍需在鎖定 Review 後重新驗證；若資料已變動，回傳 409 與可顯示的阻擋項目，不建立 decision，也不改變案件狀態。

## 8. 成功與錯誤狀態

- Finding decision 成功後停留在「疑點與決策」頁籤，保持該 Finding 展開，並顯示正式採用來源、內容與理由。
- 「另訂正式內容」未填值時不送 API，聚焦輸入框並顯示行內錯誤。
- 案件核定前顯示一次確認訊息，明確說明案件將直接結案。
- 核定成功後重新載入摘要、案件清單與案件詳情，案件移至「已完成」。
- 核定失敗時保留畫面資料與理由輸入，顯示後端回傳的阻擋原因。
- 重複提交已完成案件回傳狀態衝突，不新增第二筆 decision。

## 9. 相容性

- 舊 `PARTIALLY_ACCEPTED` decision 若 `after_value` 沒有 `selection_source`，以「另訂正式內容」顯示既有值。
- 舊 `ACCEPTED` 與 `REJECTED` 若沒有一致格式的 `after_value`，仍顯示原決策文字與既有理由，不推測遺失的正式值。
- 舊 `APPROVED` 案件維持可由既有 API 轉為 `REVIEW_COMPLETED`；工作台只顯示「既有案件已核定，待相容流程結案」的唯讀提示，不把「完成審查」放回案件決策選單。
- 已是 `REVIEW_COMPLETED` 的案件只能檢視，不可再作成 Finding 或案件決策。

## 10. 測試與驗收

- UI 測試：顯示四個新選項，不再顯示「部分採納」作為操作選項。
- UI 測試：選擇「另訂正式內容」才顯示必填輸入框，切換選項會清除自訂值。
- 資料測試：三種正式採用來源均建立正確的 `after_value`，原申報值與系統值由後端取得。
- 驗證測試：空白理由、空白自訂內容與不存在的系統建議內容均不得建立 decision。
- 門檻測試：任何風險等級的未決策 Finding 都會阻擋核定。
- 門檻測試：`REQUIRES_SUPPLEMENT` 與 `EXPERT_REVIEW` 會阻擋核定。
- 原子性測試：核定成功只建立一筆案件 decision，並直接成為 `REVIEW_COMPLETED`。
- 回滾測試：核定任一步驟失敗時，不得留下 decision、完成時間或狀態變更。
- 相容測試：既有 Finding decision、`APPROVED` 與 `REVIEW_COMPLETED` 資料仍可顯示。
- 回歸測試：完整 Review pytest 與 Node UI 行為測試通過。

## 11. 不在本次範圍

- 主管第二階段簽核、用印或跨角色行政結案。
- 回寫 Valuation 子系統的正式欄位。
- 修改原始 PDF 或 MinIO object。
- 新增資料表、欄位或 migration。
- 修改 `app/review/**` 以外的檔案。
