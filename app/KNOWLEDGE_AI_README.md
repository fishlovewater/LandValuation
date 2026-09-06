# Knowledge AI 子系統：操作與前端串接指南

## 1. 系統目的與界線

Knowledge AI 是第四子系統。它提供「有來源可查」的法規、規範、作業手冊與案件審查資訊，讓未來前端操作助手可回答使用者問題。

本階段不建立或執行任何 migration、不變更 Valuation 或 Review 的寫入流程，也不會自行繪製地圖、圖表或產生無來源依據的結論。

系統只會使用：

- MinIO `land-valuation` bucket 中 `knowledge/` 前綴的原始知識文件；
- PostgreSQL `knowledge.documents` 中既有 metadata（若存在則沿用）；若已有 `knowledge.chunks` 則可重用；
- PostgreSQL `valuation.cases`、`review.*` 中既有的案件與審查結果（唯讀）。

MinIO 保存原始檔。對沒有 `knowledge.chunks` 的文件，系統會在提問時直接下載、臨時擷取文字並只在記憶體中切成可引用片段；它不會寫入 chunk，也不會改動文件狀態。已存在的 chunks 只作為可重用快取。

為避免一次請求因 MinIO 物件過多或檔案過大耗盡資源，runtime 擷取有明確上限：
`KNOWLEDGE_RUNTIME_MAX_OBJECTS`（預設 100）、
`KNOWLEDGE_RUNTIME_MAX_OBJECT_BYTES`（預設 10 MiB）、
`KNOWLEDGE_RUNTIME_MAX_TOTAL_BYTES`（預設 50 MiB）及
`KNOWLEDGE_RUNTIME_MAX_TOTAL_CHARACTERS`（預設 200,000）。MinIO 列舉 metadata
若提供物件大小，會先在下載前拒絕超限來源；未知大小仍以 defensive read cap
限制下載。超限來源會略過並回傳為 unreadable source，不會改變既有 Valuation／Review
storage contract 或寫入 `knowledge.chunks`。

## 2. 可信來源規則

知識搜尋和問答只納入同時符合下列條件的文件：

1. 原始檔位於系統指定 bucket 的 `knowledge/` 前綴；
2. 若有對應的 `knowledge.documents` metadata，會使用其中的文件類型與生效日；沒有 metadata 時，系統建立暫時的 `OTHER` 類型來源資訊，但不寫回資料庫；
3. 若指定 `as_of_date`，有 metadata 的文件會依其生效期間篩選；
4. 若指定 `document_types`，沒有 metadata 的暫時來源只屬於 `OTHER`。

`PENDING`、`COMPLETED`、`DRAFT`、`PUBLISHED` 不再是問答或下載的存取門檻。它們可保留給既有流程使用，但 Knowledge AI 不會自行更新它們。尚無 chunks 的 PDF 會在請求當下擷取文字；掃描影像型 PDF 必須有可用 OCR，否則系統會略過該來源，不會捏造內容。每個可讀片段都回傳文件、版本、頁碼與節錄，供前端顯示與人工核對。

可用的文件類型是既有資料庫約束定義的：`REGULATION`、`STANDARD`、`MANUAL`、`OTHER`。公式與估價規則應依來源性質放在 `REGULATION`、`STANDARD` 或 `MANUAL`，不可僅因為想得到答案而任意標示。

## 3. 已提供 API

所有 API 均在 `/api/v1/knowledge` 下，且先以 Bearer JWT 驗證帳號。

| API | 用途 | 必要權限 |
|---|---|---|
| `POST /search` | 找出關鍵字相符的候選法規、規則、公式或手冊片段；**不代表答案已被驗證** | `knowledge.read` |
| `POST /ask` | 以選定 provider 依已授權來源產生、驗證證據後的回答與引用；預設為只回傳證據的安全模式；可選擇帶入唯讀案件情境 | `knowledge.read`；帶 `case_id` 時另需 `case.read` |
| `GET /provider-status` | 確認目前選定 provider 的設定與執行環境 | `knowledge.read` |
| `GET /sources/{document_id}/download` | 取得可讀知識來源文件的短效 MinIO 下載網址 | `knowledge.read` |
| `GET /cases/{case_id}/context` | 讀取案件號、基本資料，及依權限可見的最新審查結果 | `knowledge.read` + `case.read`；審查結果另需 `review.read` |

搜尋／問答的 request body：

```json
{
  "question": "比較法的因素修正率依據是什麼？",
  "case_id": "463250e2-2519-43ac-b29f-89a04ec2bf1",
  "as_of_date": "2026-09-01",
  "document_types": ["REGULATION", "STANDARD", "MANUAL"],
  "limit": 5
}
```

回應中的 citation 一定含有 `document_id`、文件版本、頁碼／章節和 `quoted_text`。前端應使用該 `document_id` 再呼叫來源下載 API；不要把 MinIO endpoint 或長效下載網址寫進前端資料庫。

### `/search` 與 `/ask` 的判讀差異（重要）

`POST /search` 的用途是讓使用者或前端看到「可能相關」的候選片段。它只回傳：

```json
{
  "retrieval_status": "CANDIDATES_FOUND",
  "retrieval_notice": "這是關鍵字相符的候選來源，尚未經 AI 逐項驗證是否支持答案；請使用 /ask 取得具證據核對的回答。",
  "citations": []
}
```

因此 `/search` 的候選中即使出現「土地徵收」、「市價」等字，也**不可**解讀為系統已判定該頁就是法源依據。要取得真正可用的答案，請以完全相同的 request body 呼叫 `POST /ask`。

`POST /ask` 的 `EVIDENCE_ONLY` 表示已有關鍵字相符的來源，但尚未由 AI
驗證答案；它不是 `SUPPORTED`。`SUPPORTED` 只會在 AI 回傳下列完整證據鏈時出現：

1. `answer` 的每個重要結論都附有 `【來源1】`、`【來源2】` 等標記；
2. 每個 citation 的 `supporting_quote` 是該 chunk 原文中可逐字找到、至少八個字的連續文字；後端只正規化 CRLF/LF 行尾表示，不會移除語義空白或段落邊界；
3. 每個 citation 的 `supported_claim` 說明它支持答案中的哪一項主張；
4. 後端確認 citation 的 chunk ID 是本次經權限篩選後提供給模型的來源，且 `supporting_quote` 確實存在於該 chunk；
5. 若模型只能找到程序、經費、表單或關鍵字相近文字，而不是問題所問的法源／條件／公式，必須回傳 `CLARIFICATION_REQUIRED`，不能標為 `SUPPORTED`。

例如使用者問「土地徵收的市價查估依據是什麼？」時，只有提到作業費、資料提供期限、申訴程序，或泛稱「依據本基準」的段落，都不能作為法定查估依據。系統必須找到載有可核對的法規名稱、條號或規範內容的來源；找不到時應回覆來源不足並要求補充，而非自行補寫答案。

### AI Provider 架構

AI provider 可由 `KNOWLEDGE_ANSWER_PROVIDER` 切換，所有 provider 都使用相同的來源封包、JSON 回應契約與 citation 驗證：

| 設定值 | 用途 | 是否可用外部搜尋／工具 |
|---|---|---|
| `evidence_only` | 預設安全模式；只回傳已授權的候選證據，不宣稱 AI 支持答案 | 不適用；不啟動模型。 |
| `codex_cli` | 明確選用的 development/test provider；使用已登入的 Codex CLI | 由 CLI sandbox、approval、config 與環境白名單共同限制；不提供外部搜尋、shell tool、apps/connectors 或 multi-agent。 |
| `bedrock` | 未來 AWS 正式環境；使用 Amazon Bedrock Converse | 不可。程式不傳遞 `toolConfig`，只傳來源封包。 |

未來如要串接其他 AI，只需新增一個 provider adapter，實作 `answer(question, candidates)` 並回傳固定欄位 `answer`、`cited_chunk_ids`、`needs_clarification`、`clarification_question`。adapter 不可自行讀取 MinIO、案件資料、網站或外部 API；它只能接收後端已完成權限與生效日篩選的來源封包。

### Codex 開發測試模式

`POST /ask` 預設使用 `evidence_only`，不啟動模型。只有在 development 或
test 環境明確設定 `KNOWLEDGE_ANSWER_PROVIDER=codex_cli` 時，才會使用已登入的
本機 Codex CLI。它不採用中文關鍵字比對來決定回答內容：後端先依 MinIO
`knowledge/` 前綴、文件類型與生效日過濾資料；已有 chunk 時重用 chunk，沒有
chunk 時才直接從 MinIO 臨時擷取，再把可用來源內容交給 Codex，由 AI 判斷問題、
組織答案並選出實際使用的 chunk。後端會驗證 Codex 回傳的每一個
`cited_chunk_ids` 都確實是本次提供的來源；不符合就拒絕結果。

Codex 子程序使用 `--sandbox read-only` 與 `--ask-for-approval never`，忽略使用者
config／rules，並以 `-c` 明確設定 `web_search="disabled"`、
`features.shell_tool=false`、`features.apps=false`、
`features.multi_agent=false`、`agents.enabled=false`、
`allow_login_shell=false`。子程序只收到跨平台執行環境、家目錄／暫存路徑與
Codex 登入所需的 allowlisted environment；不會收到資料庫、MinIO、AWS、Gemini、
Maps 或其他 API service secrets。這些 CLI、sandbox、環境與後端引用驗證控制
共同界定開發測試邊界；不要將提示詞中的模型指示誤讀為超出這些控制的保證。
這是 development/test 用途，正式環境應維持 `evidence_only` 或改用不配置工具的
Bedrock provider。

### AI 來源驗證提示詞規則

系統會以同一份 provider-neutral 指令傳給 Codex CLI 與 Bedrock。提示詞不是只要求「附引用」，而是要求模型依下列順序自我檢核：

1. 先判斷問題是問法源、程序、公式、操作或案件事實，避免不同問題類型混答。
2. 對「依據／法源／條文／規定」問題，先找明確載有法規名稱、條號或規範內容的段落；標題或文件名稱本身不算證據。
3. 對每一個準備寫入答案的主張，確認其直接回答問題、能找出原文連續引句、且不是只共享幾個關鍵字。
4. 優先採用條文、規則、辦法及明確規範；手冊、作業費、表單、資料提供與申訴程序等旁支內容，除非原文直接支持主張，否則一律排除。
5. 多個法源、條件或公式必須各自有證據，不得把兩段無關文字拼成未明示的結論。
6. 來源不足、版本／適用性不明或僅能回答部分問題時，必須設為 `needs_clarification: true`，說明缺少的具體文件、條文、版本、頁面或案件資料；不得猜測。
7. JSON 中的 `cited_chunk_ids` 與 `evidence` 必須一一對應。每筆 evidence 都含 `chunk_id`、原文 `supporting_quote` 和 `supported_claim`；後端會拒絕任何不在原文內的引句。

提示詞完整文字的唯一程式來源是 `app/knowledge/ai_contract.py` 中的 `source_grounding_instructions()`；修改 provider 時不得複製後自行改寫，以免 Codex 與 Bedrock 的安全規則分歧。

前端頁面的操作說明必須作為版本化 `MANUAL` 文件上傳 MinIO 才可由 AI 說明；若需要文件類型、生效日或版本控管，再建立對應 metadata。尚未建立前端頁面或尚未上傳的說明，不應由 AI 猜測操作步驟。

在 API 所在主機的 `.env` 設定：

```text
KNOWLEDGE_ANSWER_PROVIDER=evidence_only
# 僅在 development/test 且已明確確認 CLI 邊界時才改成 codex_cli
CODEX_CLI_COMMAND=codex
# 可留空，讓 Codex 使用登入帳號的預設模型
# CODEX_CLI_MODEL=
CODEX_CLI_TIMEOUT_SECONDS=180
KNOWLEDGE_AI_MAX_SOURCE_CHARACTERS=60000
KNOWLEDGE_RUNTIME_MAX_OBJECTS=100
KNOWLEDGE_RUNTIME_MAX_OBJECT_BYTES=10485760
KNOWLEDGE_RUNTIME_MAX_TOTAL_BYTES=52428800
KNOWLEDGE_RUNTIME_MAX_TOTAL_CHARACTERS=200000
```

先呼叫 `GET /api/v1/knowledge/provider-status`。Codex 模式中，只有
`runtime_available: true` 代表 API 主機可找到 CLI；真正問答還需要該主機可連線
到 OpenAI，且 CLI 已完成登入。若 FastAPI 跑在 Docker 容器內，容器通常無法使用
Windows 主機的 `codex.exe`，應先在 Windows 主機使用 `.venv` 啟動 API 進行測試，
或另行建立受控的 provider proxy。production/staging 明確選用 `codex_cli` 時，
API 會以 provider configuration error fail closed。

### 未來 Amazon Bedrock 模式

Kiro 是建置和協作型的 agentic coding 服務，不是本系統應直接依賴的正式推論 API；它底層使用 Bedrock。正式後端應使用 Bedrock provider，並透過 `BEDROCK_MODEL_ID` 選擇你已在 AWS 啟用、具有存取權的模型。

設定範例：

```text
KNOWLEDGE_ANSWER_PROVIDER=bedrock
BEDROCK_REGION=ap-northeast-1
BEDROCK_MODEL_ID=由 AWS 核准可用的模型 ID 或 inference profile
BEDROCK_TIMEOUT_SECONDS=60
BEDROCK_MAX_TOKENS=1200
BEDROCK_TEMPERATURE=0
```

Bedrock 使用 AWS 標準 credential provider chain，不把 AWS Access Key 寫入程式碼或 Git。部署角色應只授與所選模型所需的 `bedrock:InvokeModel`（如採串流才另加 `bedrock:InvokeModelWithResponseStream`）及必要的 CloudWatch／稽核權限。設定完成後，重啟 API 並檢查 `/provider-status`；沒有有效 AWS 認證或模型權限時，API 會明確回覆 provider 無法使用，不會改用外部搜尋或未驗證答案。

案件情境查詢範例：

```text
GET /api/v1/knowledge/cases/{case_id}/context
```

它回傳案件號 `case_no`、案件狀態、估價基準日等資料。若帳號具備 `review.read`，還會回傳最新一次 review 的風險摘要、疑點與缺件；沒有該權限時，案件資料仍可依 `case.read` 顯示，但 `review_access` 為 `false`，不會外洩審查內容。

## 4. 角色與權限政策

本階段沿用既有資料庫角色與授權，不修改 migration：

| 角色 | 知識檢索 | 案件情境 | 審查結果 |
|---|---:|---:|---:|
| `APPRAISER` | 可以（既有 `knowledge.read`） | 可以（既有 `case.read`） | 不可以，除非未來明確授與 `review.read` |
| `REVIEWER` | 可以 | 可以 | 可以 |
| `INSPECTOR` | 可以 | 可以 | 可以 |

知識文件的上傳、擷取、發布／停用和角色管理尚未在本子系統開放 API。未來應使用獨立的 `knowledge.manage` 權限與知識管理員角色；在該權限經正式資料庫變更與授權流程確認前，不能以 `knowledge.read` 取代管理權限。

目前的案件存取採用既有的全域 RBAC；系統尚沒有案件指派／逐案 ACL 資料，因此不能宣稱已提供「只可看自己案件」的限制。若未來需要，必須先確認既有案件指派資料的權威來源，再新增唯讀授權判斷。

## 5. 未來前端操作助手流程

前端不需要直接連 MinIO。建議依下列流程實作：

1. 使用者登入後，前端保留 JWT，不在前端自行判定權限。
2. 使用者選取案件時，呼叫 `/cases/{case_id}/context`，顯示案件號、狀態與 `review_access`。
3. 使用者問法規／公式／規則問題時，呼叫 `/search` 或 `/ask`，並把案件基準日帶入 `as_of_date`。
4. 顯示引用文件名稱、版本、頁碼、章節與節錄。使用者點擊「查看原文」時才呼叫 `/sources/{document_id}/download`。
5. 回應 `NO_RELEVANT_SOURCE` 或 `CLARIFICATION_REQUIRED` 時，顯示「目前沒有足夠的可讀適用來源」，引導使用者補足問題或請知識管理員檢查 MinIO 文件與 metadata；不可改用猜測答案。
6. 回應 `review_access: false` 時，顯示無權限提示，而非顯示空白的審查結果。

`POST /ask` 現在可選擇帶入 `case_id`。後端會以既有 `case.read` 讀取案件，並只在帳號具備 `review.read` 時附上最新審查結果。回應中的 `case_context` 是**獨立、結構化且唯讀**的案件資料，不會被 AI 當成法規來源，也不會混入 citation；AI 的 `answer` 與 citation 仍只以 MinIO 文件為依據。這使前端可在同一個回應中並列顯示「案件／審查情境」與「有文件證據的規則回答」，但不宣稱模型已使用案件資料推論。

公式問題同樣遵守來源邊界：AI 只能說明 MinIO 原文明確記載的公式、變數與適用條件，不會執行估價計算、調整率計算或跨表檢核。真正的公式引擎必須先由業務確認每一條公式的權威來源、輸入欄位、四捨五入規則與驗收案例，才可另行開發，不能由 AI 自行推導。

## 6. MinIO 與文件操作

系統 bucket 固定為 `land-valuation`：

```text
knowledge/{category}/{document_id}/v{version}/{filename}
cases/{case_id}/{category}/{document_id}/v{version}/{filename}
```

`object_key` 只保存 key，不保存 `localhost`、MinIO 網址或預簽名 URL。下載 API 在完成 JWT、bucket 與 `knowledge/` 前綴檢查後，才建立短效 URL；有效時間由 `MINIO_PRESIGNED_EXPIRY_SECONDS` 控制，預設為 900 秒。

## 7. 開發與驗證

在專案根目錄使用已安裝的虛擬環境執行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### Windows 本機 API 啟動（必要）

在 Windows 以本機 `.venv` 測試 API 時，請**不要**使用
`python -m uvicorn app.main:app`。目前的非同步 PostgreSQL 驅動 `psycopg`
不能使用 Windows 預設的 Proactor event loop，登入會因此出現
`503 DATABASE_ERROR`，即使資料庫主機與密碼正確。

請改用專案提供的入口；它會在 Uvicorn 建立 event loop 前改用相容的
Windows selector loop：

```cmd
cd "D:\master proj\land ai assist\LandValuationAssistant"
.\.venv\Scripts\python.exe scripts\run_local_api.py
```

預設網址為 `http://127.0.0.1:8002/docs`。如果 8002 已被其他服務使用，
可在同一個 cmd 視窗改用 8003：

```cmd
set API_PORT=8003
.\.venv\Scripts\python.exe scripts\run_local_api.py
```

看到 `Application startup complete` 後，先用 Swagger 的
`POST /api/v1/auth/login` 登入，再按 **Authorize** 貼上 access token，最後測試
`GET /api/v1/knowledge/provider-status`。Docker/Linux 部署不需要這個 Windows
本機啟動入口。

本子系統的測試確認：未發布／未擷取／失效文件不會出現在結果、沒有來源時不會編造答案、Codex 來源封包不做中文關鍵字排序、Codex 不可引用未提供的 chunk、路由已註冊、API 必須登入、查看審查結果需要 `review.read`。
