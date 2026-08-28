# Review Evidence and Document Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Review evidence human-readable in Chinese, localize decisions and document types, collapse API logs, and let reviewers securely compare each finding with the corresponding original PDF page.

**Architecture:** Keep all changes inside `app/review/**`. Add one repository query and one permission-protected Review endpoint for case-owned document content, then fetch that PDF as an authenticated Blob in the existing development workbench. Keep label formatting, structured evidence rendering, decision validation, PDF URL construction, and log summaries as small testable JavaScript helpers inside the current single-file UI.

**Tech Stack:** FastAPI, SQLAlchemy async text queries, existing `StorageService`/MinIO integration, pytest/TestClient, vanilla HTML/CSS/JavaScript, Node built-in test runner.

## Global Constraints

- Modify only `app/review/**`; stop and ask before changing any other path.
- PostgreSQL stores document metadata and object keys; MinIO stores PDF/image bodies.
- Do not expose bucket names, object keys, MinIO credentials, or fixed localhost URLs in the workbench.
- Keep `/api/v1/review/test-ui` and the existing JWT plus `review.execute`/`review.decide` permissions.
- Do not add migrations, Vue/React, npm dependencies, OCR, RAG, or PDF text-coordinate highlighting.
- UI labels may be Chinese, but existing API decision codes remain unchanged.
- `rtk` is required for shell commands when available. This checkout currently reports that `rtk` is unavailable, so execution may use the shown command without the `rtk` prefix only after confirming the same condition.
- Use TDD for every behavior change and commit after every independently testable task.

## File Structure

- Modify `app/review/workbench_repository.py`: retrieve only metadata for a document that belongs to the case attached to a supplied Review.
- Modify `app/review/router.py`: authorize, download, and stream the validated PDF without exposing its object key.
- Modify `app/review/test_ui/index.html`: Chinese mappings, evidence/legal formatting, conditional partial-acceptance field, split PDF preview, Blob cleanup, and collapsible request logs.
- Modify `app/review/tests/test_workbench_api.py`: database-backed ownership tests for the document-content endpoint.
- Modify `app/review/tests/test_ui_behavior.mjs`: pure JavaScript behavior tests.
- Modify `app/review/tests/test_test_ui.py`: static HTML/security contract assertions.

---

### Task 1: Secure Review-owned document content endpoint

**Files:**
- Modify: `app/review/workbench_repository.py`
- Modify: `app/review/router.py`
- Test: `app/review/tests/test_workbench_api.py`

**Interfaces:**
- Consumes: `Storage.download(object_key: str)`, existing `DbSession`, and `require_permissions("review.execute")`.
- Produces: `WorkbenchRepository.get_document_for_review(review_id: UUID, document_id: UUID) -> dict | None` and `GET /review/workbench/cases/{review_id}/documents/{document_id}/content`.

- [ ] **Step 1: Write failing repository and endpoint tests**

Add a fake downloadable object and fake storage to `test_workbench_api.py`, then add a test document owned by `workbench_records.reviewed_case_id`:

```python
class DownloadObject:
    def __init__(self, content: bytes):
        self.content = content
        self.closed = False

    def stream(self, amt: int):
        for offset in range(0, len(self.content), amt):
            yield self.content[offset : offset + amt]

    def close(self):
        self.closed = True

    def release_conn(self):
        pass


class DocumentStorage:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    async def download(self, object_key: str):
        return DownloadObject(self.objects[object_key])
```

Create one `valuation.documents` row for the reviewed case and one for a different case. Override `get_storage_service`, request the owned document, and assert:

```python
response = workbench_client.get(
    f"/api/v1/review/workbench/cases/{records.review_id}/documents/{owned_id}/content"
)
assert response.status_code == 200
assert response.content == b"%PDF-review-owned"
assert response.headers["content-type"] == "application/pdf"
assert response.headers["content-disposition"].startswith("inline;")

cross_case = workbench_client.get(
    f"/api/v1/review/workbench/cases/{records.review_id}/documents/{other_id}/content"
)
assert cross_case.status_code == 404

missing = workbench_client.get(
    f"/api/v1/review/workbench/cases/{records.review_id}/documents/{uuid4()}/content"
)
assert missing.status_code == 404
```

Also insert a same-case document with `mime_type='text/html'` and assert the endpoint returns `415`; active content must never be embedded at the workbench origin. Ensure fixture cleanup deletes the inserted documents before their cases.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_workbench_api.py -q
```

Expected: FAIL with `404` for the new content route or missing `get_document_for_review`.

- [ ] **Step 3: Add the ownership-scoped repository query**

Add to `WorkbenchRepository`:

```python
async def get_document_for_review(
    self, review_id: UUID, document_id: UUID
) -> dict | None:
    row = (
        await self.session.execute(
            text(
                """
                SELECT d.document_id, d.original_filename, d.mime_type,
                       d.object_key
                FROM review.reviews r
                JOIN valuation.documents d ON d.case_id = r.case_id
                WHERE r.review_id = :review_id
                  AND d.document_id = :document_id
                """
            ),
            {"review_id": review_id, "document_id": document_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row else None
```

Do not return `bucket_name`; the router needs only the existing storage service's `object_key`.

- [ ] **Step 4: Add the protected streaming route**

In `router.py`, import `quote`, `StreamingResponse`, and `ResourceNotFoundError`. Add:

```python
@router.get(
    "/workbench/cases/{review_id}/documents/{document_id}/content"
)
async def get_workbench_document_content(
    review_id: UUID,
    document_id: UUID,
    session: DbSession,
    storage: Storage,
    user=Depends(require_permissions("review.execute")),
) -> StreamingResponse:
    del user
    metadata = await WorkbenchRepository(session).get_document_for_review(
        review_id, document_id
    )
    if metadata is None:
        raise ResourceNotFoundError("案件原文件")
    if metadata["mime_type"] != "application/pdf":
        raise AppError(
            "REVIEW_DOCUMENT_PREVIEW_UNSUPPORTED",
            "此文件格式不支援內嵌預覽",
            415,
        )
    downloaded = await storage.download(metadata["object_key"])

    def chunks():
        try:
            yield from downloaded.stream(amt=64 * 1024)
        finally:
            downloaded.close()
            downloaded.release_conn()

    filename = quote(metadata["original_filename"], safe="")
    return StreamingResponse(
        chunks(),
        media_type=metadata["mime_type"],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )
```

The SQL join is the authorization boundary for case ownership; do not accept an object key from the client.

- [ ] **Step 5: Run focused backend tests**

Run:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_workbench_api.py app/review/tests/test_report_api.py -q
```

Expected: all selected tests PASS, including owned PDF download, cross-case 404, missing 404, active-content 415, and existing report PDF behavior.

- [ ] **Step 6: Commit the endpoint**

```powershell
rtk git add app/review/workbench_repository.py app/review/router.py app/review/tests/test_workbench_api.py
rtk git commit -m "feat(review): secure case document preview"
```

---

### Task 2: Human-readable Chinese evidence and decision controls

**Files:**
- Modify: `app/review/test_ui/index.html`
- Test: `app/review/tests/test_ui_behavior.mjs`
- Test: `app/review/tests/test_test_ui.py`

**Interfaces:**
- Consumes: existing finding properties `source_evidence`, `legal_basis`, `reported_text`, `document_version`, `page_number`, and `field_path`.
- Produces: `documentTypeLabel(value)`, `findingDecisionLabel(value)`, `caseDecisionLabel(value)`, `flattenDisplayData(value)`, `renderStructuredContent(value, emptyText)`, and `requiresAfterValue(decision)`.

- [ ] **Step 1: Write failing JavaScript helper tests**

Export the new helpers from the testable logic marker and add tests:

```javascript
test("review codes have Chinese display labels", () => {
  assert.equal(logic.documentTypeLabel("cadastral-map"), "地籍圖");
  assert.equal(logic.documentTypeLabel("land-register"), "土地登記謄本");
  assert.equal(logic.findingDecisionLabel("PARTIALLY_ACCEPTED"), "部分採納");
  assert.equal(logic.caseDecisionLabel("APPROVED"), "核定通過");
  assert.equal(logic.documentTypeLabel("custom"), "其他文件（custom）");
});

test("structured evidence becomes readable rows instead of JSON", () => {
  assert.deepEqual(
    logic.flattenDisplayData([
      { document_version: 2, page_number: 3, verification_status: "VERIFIED" },
    ]),
    [
      { label: "文件版本", value: "2" },
      { label: "頁碼", value: "3" },
      { label: "確認狀態", value: "已確認" },
    ],
  );
});

test("only partial acceptance requires an after value", () => {
  assert.equal(logic.requiresAfterValue("PARTIALLY_ACCEPTED"), true);
  assert.equal(logic.requiresAfterValue("ACCEPTED"), false);
});
```

- [ ] **Step 2: Run Node tests and verify they fail**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: FAIL because the new helpers are undefined.

- [ ] **Step 3: Implement label and evidence helpers**

Inside `TESTABLE_WORKBENCH_LOGIC_START`, add fixed maps and pure helpers:

```javascript
const documentTypeLabels={
  original:"原始查估文件",
  "land-register":"土地登記謄本",
  "cadastral-map":"地籍圖",
};
const findingDecisionLabels={
  ACCEPTED:"採納疑點",
  PARTIALLY_ACCEPTED:"部分採納",
  REJECTED:"不採納",
  REQUIRES_SUPPLEMENT:"要求補件",
  EXPERT_REVIEW:"轉專家覆核",
};
const caseDecisionLabels={
  RETURNED_FOR_REVISION:"退回修正",
  SUPPLEMENT_REQUIRED:"要求補件",
  EXPERT_REVIEW:"轉專家覆核",
  APPROVED:"核定通過",
  REVIEW_COMPLETED:"完成審查",
};
const evidenceKeyLabels={
  document_version:"文件版本",
  page_number:"頁碼",
  verification_status:"確認狀態",
  raw_text:"原始文字",
  field_path:"欄位位置",
  title:"法規名稱",
  article:"條文",
  section:"章節",
  excerpt:"引用內容",
  effective_from:"生效日期",
  applicability:"適用說明",
};
const displayValue=value=>value===null||value===undefined||value===""
  ?"未提供"
  :value==="VERIFIED"?"已確認":String(value);
const documentTypeLabel=value=>documentTypeLabels[value]||`其他文件（${value||"未提供"}）`;
const findingDecisionLabel=value=>findingDecisionLabels[value]||value;
const caseDecisionLabel=value=>caseDecisionLabels[value]||value;
const requiresAfterValue=decision=>decision==="PARTIALLY_ACCEPTED";
function flattenDisplayData(value,rows=[]){
  if(Array.isArray(value)){value.forEach(item=>flattenDisplayData(item,rows));return rows}
  if(value&&typeof value==="object"){
    Object.entries(value).forEach(([key,item])=>{
      if(item&&typeof item==="object")flattenDisplayData(item,rows);
      else rows.push({label:evidenceKeyLabels[key]||key,value:displayValue(item)});
    });
    return rows;
  }
  rows.push({label:"內容",value:displayValue(value)});
  return rows;
}
```

Keep `renderStructuredContent` outside the test marker because it calls `esc`; render rows as `<dl>` or two-column records, never with `JSON.stringify`.

- [ ] **Step 4: Render Chinese document, evidence, legal, and decision content**

Replace document type codes with `documentTypeLabel(x.document_type)`. Replace both decision `<option>` sets with explicit values and Chinese labels, for example:

```html
<option value="PARTIALLY_ACCEPTED">部分採納</option>
```

Replace the evidence/legal `<pre>${JSON.stringify(...)}</pre>` blocks with:

```javascript
function renderStructuredContent(value,emptyText){
  const rows=flattenDisplayData(value);
  return rows.length
    ?`<dl class="evidence-list">${rows.map(row=>
      `<div><dt>${esc(row.label)}</dt><dd>${esc(row.value)}</dd></div>`
    ).join("")}</dl>`
    :`<p>${esc(emptyText)}</p>`;
}
```

Add `data-partial-value-box` around the formal-value input. It starts hidden and is revealed only when its paired select value is `PARTIALLY_ACCEPTED`; set both `required` and `aria-required` at the same time. Continue using `findingDecisionBody` as the final validation before request submission.

- [ ] **Step 5: Strengthen static UI assertions**

In `test_test_ui.py`, assert the HTML contains `地籍圖`, `土地登記謄本`, `採納疑點`, `部分採納`, `核定通過`, `renderStructuredContent`, and `data-partial-value-box`. Assert the finding renderer no longer contains:

```python
assert "JSON.stringify(f.source_evidence" not in response.text
assert "JSON.stringify(f.legal_basis" not in response.text
```

- [ ] **Step 6: Run focused UI tests**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_test_ui.py -q
```

Expected: all Node tests and `test_test_ui.py` PASS.

- [ ] **Step 7: Commit readable evidence and controls**

```powershell
rtk git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs app/review/tests/test_test_ui.py
rtk git commit -m "feat(review): localize evidence and decisions"
```

---

### Task 3: Authenticated split-pane PDF preview and Blob lifecycle

**Files:**
- Modify: `app/review/test_ui/index.html`
- Test: `app/review/tests/test_ui_behavior.mjs`
- Test: `app/review/tests/test_test_ui.py`

**Interfaces:**
- Consumes: Task 1 content endpoint and existing `request(path, {binary: true})`.
- Produces: `documentContentPath(reviewId, documentId)`, `pdfPageTarget(url, pageNumber)`, `releaseDocumentPreview()`, and `loadDocumentPreview(finding)`.

- [ ] **Step 1: Write failing URL helper tests**

Add:

```javascript
test("document preview path is review scoped and page aware", () => {
  assert.equal(
    logic.documentContentPath("review-1", "document-2"),
    "/review/workbench/cases/review-1/documents/document-2/content",
  );
  assert.equal(logic.pdfPageTarget("blob:preview", 7), "blob:preview#page=7");
  assert.equal(logic.pdfPageTarget("blob:preview", null), "blob:preview#page=1");
});
```

- [ ] **Step 2: Run Node tests and verify they fail**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: FAIL because `documentContentPath` and `pdfPageTarget` are undefined.

- [ ] **Step 3: Add pure preview helpers and state**

Inside the test marker add:

```javascript
const documentContentPath=(reviewId,documentId)=>
  `/review/workbench/cases/${reviewId}/documents/${documentId}/content`;
const pdfPageTarget=(url,pageNumber)=>`${url}#page=${pageNumber||1}`;
```

Extend `state` with `previewUrl:""` and `previewKey:""`. Add:

```javascript
function releaseDocumentPreview(){
  if(state.previewUrl)URL.revokeObjectURL(state.previewUrl);
  state.previewUrl="";
  state.previewKey="";
}
```

Call it before rendering a different case and during logout.

- [ ] **Step 4: Add split-pane markup and styles**

Render the findings panel as:

```html
<div class="finding-workspace">
  <aside class="source-preview" aria-label="原文件預覽">
    <p id="source-preview-status">請選擇疑點查看原文件。</p>
    <iframe id="source-pdf" class="hidden" title="原文件 PDF 預覽"></iframe>
    <a id="source-pdf-open" class="btn secondary small hidden" target="_blank" rel="noopener">另開原文件</a>
  </aside>
  <div id="finding-list">…</div>
</div>
```

Use a two-column desktop grid with a sticky preview pane. Under the existing mobile breakpoint, switch to one column and keep the explicit 「查看原文件第 N 頁」 button in each finding.

- [ ] **Step 5: Fetch and display the authenticated PDF**

Add `data-view-source` to each finding with a document. Implement:

```javascript
async function loadDocumentPreview(finding){
  const status=$("#source-preview-status"),frame=$("#source-pdf"),open=$("#source-pdf-open");
  if(!finding.document_id){
    status.textContent="此疑點未連結原文件。";
    return;
  }
  const key=`${finding.document_id}:${finding.page_number||1}`;
  if(state.previewKey===key)return;
  status.textContent="正在載入原文件…";
  const blob=await request(documentContentPath(
    state.current.review.review_id,finding.document_id
  ),{binary:true});
  releaseDocumentPreview();
  state.previewUrl=URL.createObjectURL(blob);
  state.previewKey=key;
  const target=pdfPageTarget(state.previewUrl,finding.page_number);
  frame.src=target;
  frame.classList.remove("hidden");
  open.href=target;
  open.classList.remove("hidden");
  status.textContent=finding.page_number
    ?`已開啟原文件第 ${finding.page_number} 頁。`
    :"未提供對應頁碼，已開啟文件第一頁。";
}
```

On failure, retain all decision textareas and inputs, show the existing error banner, and keep a retry-capable source button. Do not rerender the finding list merely because preview loading failed.

- [ ] **Step 6: Add static PDF security/lifecycle tests**

In `test_test_ui.py`, assert the response includes `finding-workspace`, `source-pdf`, `data-view-source`, `/documents/`, `/content`, `URL.createObjectURL`, and `URL.revokeObjectURL`. Also assert it does not contain `bucket_name`, `object_key`, `minio`, or a hard-coded MinIO URL in the preview code.

- [ ] **Step 7: Run focused PDF UI tests**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_test_ui.py app/review/tests/test_workbench_api.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 8: Commit the preview UI**

```powershell
rtk git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs app/review/tests/test_test_ui.py
rtk git commit -m "feat(review): compare findings with source pdf"
```

---

### Task 4: Collapsible developer request evidence

**Files:**
- Modify: `app/review/test_ui/index.html`
- Test: `app/review/tests/test_ui_behavior.mjs`
- Test: `app/review/tests/test_test_ui.py`

**Interfaces:**
- Consumes: existing redaction and request wrapper.
- Produces: `requestLogSummary(method, path, status, elapsed)` and one closed `<details class="log-entry">` per request.

- [ ] **Step 1: Write the failing request-summary test**

```javascript
test("request log summary keeps request identity while collapsed", () => {
  assert.equal(
    logic.requestLogSummary("GET", "/review/workbench/summary", 200, 42),
    "GET /review/workbench/summary · 200 · 42 ms",
  );
});
```

- [ ] **Step 2: Run Node tests and verify the helper is missing**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: FAIL because `requestLogSummary` is undefined.

- [ ] **Step 3: Render each log entry as a closed details element**

Add the pure helper:

```javascript
const requestLogSummary=(method,path,status,elapsed)=>
  `${method} ${path} · ${status} · ${elapsed} ms`;
```

Change `log` to create `details` without setting `open`:

```javascript
const item=document.createElement("details");
item.className=`log-entry ${ok?"":"fail"}`;
item.innerHTML="<summary class=\"log-meta\"></summary><pre></pre>";
$("summary",item).textContent=requestLogSummary(method,path,status,elapsed);
```

Pass a redacted object containing separate `request` and `response` keys for JSON requests. For binary PDF responses, log only `{response: "application/pdf · N bytes"}`; never serialize the Blob.

- [ ] **Step 4: Add static collapsed-log assertions**

In `test_test_ui.py`, assert the log template contains `<summary class=\"log-meta\">` and that the implementation creates a `details` element. Preserve assertions for `redactForLog` and `[REDACTED]`.

- [ ] **Step 5: Run focused UI tests**

Run:

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_test_ui.py -q
```

Expected: all selected tests PASS; each request remains identifiable without expanding its payload.

- [ ] **Step 6: Commit collapsible logs**

```powershell
rtk git add app/review/test_ui/index.html app/review/tests/test_ui_behavior.mjs app/review/tests/test_test_ui.py
rtk git commit -m "feat(review): collapse developer request evidence"
```

---

### Task 5: Full Review regression and manual acceptance

**Files:**
- Modify only if a verified defect is found: files already listed in Tasks 1-4
- Test: `app/review/tests/**`

**Interfaces:**
- Consumes: all deliverables from Tasks 1-4.
- Produces: a verified Review workbench with no regression in the existing Review flows.

- [ ] **Step 1: Run the complete Review test suite**

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests -q
```

Expected: all Review tests PASS. Record the exact pass/skip/warning counts; do not reuse a historical count.

- [ ] **Step 2: Run the standalone browser-logic suite**

```powershell
rtk test node --test app/review/tests/test_ui_behavior.mjs
```

Expected: every Node subtest PASS.

- [ ] **Step 3: Run whitespace and scope checks**

```powershell
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors and no modified path outside `app/review/**`.

- [ ] **Step 4: Perform the development workbench smoke test**

Run the existing Demo seed command, sign in at `/api/v1/review/test-ui`, and verify:

1. 摘要與文件顯示「原始查估文件」「土地登記謄本」「地籍圖」。
2. 疑點證據與法規為中文欄位和值，不是 JSON。
3. 疑點和案件決策顯示中文，request payload 仍使用英文代碼。
4. 正式值欄位只在「部分採納」時顯示；空白理由或正式值不可送出。
5. 原 PDF 在左側開啟對應頁；Demo PDF 僅視為測試素材。
6. 窄螢幕可用按鈕另開原文件。
7. 開發資訊預設關閉，每筆請求也預設收合；展開後敏感欄位已遮罩。

- [ ] **Step 5: Commit only verified follow-up corrections**

If Step 1-4 required a correction, rerun the affected focused test and the complete Review suite, then commit only those corrections:

```powershell
rtk git add app/review
rtk git commit -m "fix(review): finish evidence preview acceptance"
```

If no correction was needed, do not create an empty commit.
