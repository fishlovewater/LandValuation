# 審查 Demo 後端更新（2026-09-13）

本次不修改 schema、migration 或共用 OCR service，也沒有重啟現有服務。

## 人工確認與填表

外部審查確認 API 先使用既有 OCR service 儲存 CONFIRMED，再依既有 F01/F03/F04 草稿欄位契約填入來源文件對應的 form_instances。寫入成功後才設定 APPLIED、真實表單 ID 及套用時間。全部使用同一 request transaction，失敗由既有 session dependency rollback。

F01 沿用交易編號、土地坐落、土地／建物面積的既有別名對應。使用者可修正後再次確認；重複確認沿用同一來源草稿。排除欄位會清除這個候選值寫入的內容，保留其他來源欄位。F01/F04 修改會使舊計算結果失效。

不能明確對應的欄位、關聯 ID、明細列以及其他表單類型保留 CONFIRMED，不虛構關聯或標記 APPLIED；目前尚未實作所有表單／明細的自動對應。F03 本次寫入來源表單草稿，不建立或修改 benchmark_valuations 的關聯估價紀錄。

無疑慮欄位自動填表仍暫緩：現有 APPLIED 約束要求人工確認者，需另行核准 schema 設計。前端本次未修改，成功後仍由既有 API response 更新候選值狀態。

## Demo 缺件放行

新增 DEMO_REVIEW_ALLOW_MISSING_MATERIALS，預設 false，僅 docker-compose.demo.yml 設為 true。只有 development 環境、EXTERNAL_REVIEW、無平台 submission 的案件適用。

土地登記謄本、地籍圖、宗地面積缺少時仍保留缺件清單，但不阻擋智慧審查；原本 PENDING_MATERIALS 案件也可重新執行。原始報告、案件基本識別／日期、正式規則與法規來源仍必須可用。

有資料的規則繼續執行，缺必要資料或依賴缺件的規則不執行。run input snapshot 記錄 skipped_rule_codes 及 Demo 說明，風險摘要明確說明未執行不代表通過。不建立模擬附件、不將缺件假標為已補齊。正式結案的缺件門檻本次未放寬。

## 更新現有 Demo API

在專案根目錄執行（Docker Desktop 必須已啟動）：

```powershell
docker compose --project-name landvaluation-persistent-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.example up -d --build --no-deps api
```

此指令只重建／重啟 API，不啟動 migrate 或重新 seed OCR 案件；API 原有啟動命令仍會執行 history demo seed。不要為本次更新執行 migration 或清除資料卷。已有前端 dev server 可繼續使用。

## 修改檔案

- app/review/workbench_service.py
- app/review/intake_forms.py
- app/review/service.py
- app/review/demo_policy.py
- app/core/config.py
- docker-compose.demo.yml
- tests/test_review_intake_fix.py

## 驗證

```powershell
tmp/review-test-venv/Scripts/python.exe -m pytest tests/test_review_intake_fix.py app/review/tests/test_workbench_service.py app/review/tests/test_service.py app/review/tests/test_completeness.py app/review/tests/test_trusted_inputs.py -q
```

測試使用替身驗證寫入順序、狀態、規則選擇及環境範圍；未對正在使用的 Demo 資料庫執行整合測試。
