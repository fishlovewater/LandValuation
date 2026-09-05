# Valuation Test UI and Correction Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a development-only Valuation test page that supports intake through first submission, shows Review correction or supplement requirements, and resubmits a corrected report without manual ID handoff.

**Architecture:** Serve one static HTML page from the existing FastAPI application. Add a narrow appraiser-readable handoff projection over existing Valuation and Review records, and make a revision submission register the new report on the active correction request inside the same database transaction. Reuse all existing extraction, formal calculation, validation, report, Submission, and Review recheck services.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, PostgreSQL, MinIO, plain HTML/CSS/JavaScript, pytest, Node built-in test runner.

## Global Constraints

- Target only `feature/integrate-valuation-review`; do not modify, merge, or push `feature/review` or `origin/feature/valuation`.
- This is a development test UI, not a Vue/React production frontend.
- Only `APP_ENV=development` may serve the page or run the Demo account command.
- Valuation remains authoritative for case data, APPLIED values, forms, calculations, validations, and reports.
- Review owns correction requests, findings, decisions, and recheck results; Review never writes Valuation formal values.
- A revision submission and its correction-response registration succeed or roll back together.
- Never overwrite old Submissions, Runs, findings, decisions, documents, or fingerprints.
- Never expose passwords, JWTs, Submission snapshots, internal Review notes, MinIO bucket names, object keys, or presigned URLs in the UI projection or request log.
- Keep the existing server-side Decimal calculations and submission readiness gates unchanged.

---

## File Structure

- `app/valuation/submissions/schemas.py`: public appraiser-facing handoff, correction, missing-item, and submission response shapes.
- `app/valuation/submissions/handoff_service.py`: ownership checks and the read-only Valuation-to-Review status projection.
- `app/valuation/submissions/router.py`: handoff-status route and the existing submit route.
- `app/valuation/submissions/service.py`: revision-submission orchestration hook.
- `app/review/correction_service.py`: server-side registration of the latest sent correction request, while retaining the legacy explicit-ID method.
- `app/valuation/demo.py`: development-only APPRAISER account seed/reset command.
- `app/valuation/router.py`: development-only HTML route.
- `app/valuation/test_ui/index.html`: the entire dependency-free test page.
- `tests/test_valuation_handoff_status.py`: projection, ownership, and data-leak tests.
- `tests/test_submission_service.py`: atomic corrected-submission behavior.
- `tests/test_submission_api.py`: route and permission contract.
- `tests/test_valuation_demo.py`: Demo account command contract.
- `tests/test_valuation_test_ui.py`: route, environment guard, and HTML contract.
- `tests/test_valuation_ui_behavior.mjs`: browser-independent UI state and request-building tests.
- `tests/integration/test_valuation_review_handoff.py`: real PostgreSQL/MinIO correction-loop proof.
- `app/valuation/TEST_UI_GUIDE.md`: short runbook and acceptance checklist.

### Task 1: Add the appraiser-readable handoff projection

**Files:**
- Modify: `app/valuation/submissions/schemas.py`
- Create: `app/valuation/submissions/handoff_service.py`
- Modify: `app/valuation/submissions/router.py`
- Create: `tests/test_valuation_handoff_status.py`

**Interfaces:**
- Consumes: `CaseRecord.created_by_user_id`, `Review.latest_submission_id`, `CorrectionRepository.active_for_review()`, `CorrectionRepository.list_items()`, and `ReviewRepository.list_missing_items()`.
- Produces: `ValuationReviewHandoffService.get(case_id, actor)` and `GET /api/v1/valuation/cases/{case_id}/review-handoff` returning `ValuationReviewHandoffRead`.

- [ ] **Step 1: Write failing response-shape and ownership tests**

```python
@pytest.mark.asyncio
async def test_handoff_status_returns_only_appraiser_safe_correction_data():
    result = await service.get(case.case_id, owner)

    assert result.case_status == "REVISION_REQUIRED"
    assert result.display_status == "退回補正"
    assert result.latest_submission.submission_no == 1
    assert result.correction.message == "請修正價格日期並補上謄本"
    assert result.correction.items[0].requested_correction == "更正價格日期"
    assert result.missing_items[0].item_name == "土地登記謄本"
    body = result.model_dump(mode="json")
    assert "input_snapshot" not in str(body)
    assert "object_key" not in str(body)
    assert "bucket_name" not in str(body)


@pytest.mark.asyncio
async def test_handoff_status_rejects_another_appraisers_case():
    with pytest.raises(PermissionDeniedError):
        await service.get(case.case_id, other_appraiser)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `rtk pytest tests/test_valuation_handoff_status.py -q`

Expected: collection fails because `ValuationReviewHandoffService` and the response models do not exist.

- [ ] **Step 3: Add explicit safe response models**

```python
class HandoffSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    submission_id: UUID
    submission_no: int
    submitted_at: datetime


class HandoffCorrectionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_code: str
    severity: str
    document_id: UUID | None
    page_number: int | None
    issue_summary: str
    requested_correction: str


class HandoffCorrectionRead(BaseModel):
    correction_request_id: UUID
    request_no: int
    status: str
    due_at: datetime
    message: str
    items: list[HandoffCorrectionItemRead]


class HandoffMissingItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_code: str
    item_name: str
    document_type: str | None
    severity: str
    reason: str | None
    due_at: datetime | None


class ValuationReviewHandoffRead(BaseModel):
    case_id: UUID
    case_status: str
    display_status: str
    review_id: UUID | None
    review_status: str | None
    latest_submission: HandoffSubmissionRead | None
    correction: HandoffCorrectionRead | None
    missing_items: list[HandoffMissingItemRead] = Field(default_factory=list)
```

- [ ] **Step 4: Implement the projection without exposing reviewer-only records**

```python
STATUS_LABELS = {
    "DRAFT": "製作中",
    "PROCESSING": "製作中",
    "IN_REVIEW": "審查中",
    "REVISION_REQUIRED": "退回補正",
    "REVIEW_COMPLETED": "審查完成",
}


class ValuationReviewHandoffService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.corrections = CorrectionRepository(session)
        self.reviews = ReviewRepository(session)

    async def get(self, case_id: UUID, actor: User) -> ValuationReviewHandoffRead:
        case = await self.session.scalar(
            select(CaseRecord).where(CaseRecord.case_id == case_id)
        )
        if case is None:
            raise ResourceNotFoundError("估價案件")
        if case.created_by_user_id != actor.user_id:
            raise PermissionDeniedError("只能查看自己建立的估價案件")

        review = await self.session.scalar(
            select(Review).where(Review.case_id == case_id)
        )
        if review is None:
            return ValuationReviewHandoffRead(
                case_id=case_id,
                case_status=case.case_status,
                display_status=STATUS_LABELS.get(case.case_status, "製作中"),
                review_id=None,
                review_status=None,
                latest_submission=None,
                correction=None,
                missing_items=[],
            )

        submission = None
        if review.latest_submission_id is not None:
            submission = await self.session.scalar(
                select(ReviewSubmissionRecord).where(
                    ReviewSubmissionRecord.submission_id == review.latest_submission_id,
                    ReviewSubmissionRecord.review_id == review.review_id,
                    ReviewSubmissionRecord.case_id == case_id,
                )
            )
        request = await self.corrections.active_for_review(review.review_id)
        correction = None
        if request is not None and request.status in {"SENT", "RESUBMITTED"}:
            items = await self.corrections.list_items(request.correction_request_id)
            correction = HandoffCorrectionRead(
                correction_request_id=request.correction_request_id,
                request_no=request.request_no,
                status=request.status,
                due_at=request.due_at,
                message=request.message,
                items=[HandoffCorrectionItemRead.model_validate(item) for item in items],
            )
        missing = await self.reviews.list_missing_items(review.review_id, open_only=True)
        return ValuationReviewHandoffRead(
            case_id=case_id,
            case_status=case.case_status,
            display_status=STATUS_LABELS.get(case.case_status, case.case_status),
            review_id=review.review_id,
            review_status=review.review_status,
            latest_submission=(
                None if submission is None else HandoffSubmissionRead.model_validate(submission)
            ),
            correction=correction,
            missing_items=[HandoffMissingItemRead.model_validate(item) for item in missing],
        )
```

- [ ] **Step 5: Add the protected route**

```python
@router.get(
    "/cases/{case_id}/review-handoff",
    response_model=ValuationReviewHandoffRead,
)
async def get_review_handoff(
    case_id: UUID,
    session: DbSession,
    user=Depends(require_permissions("case.read")),
) -> ValuationReviewHandoffRead:
    return await ValuationReviewHandoffService(session).get(case_id, user)
```

- [ ] **Step 6: Run focused tests and commit**

Run: `rtk pytest tests/test_valuation_handoff_status.py tests/test_submission_api.py -q`

Expected: all tests pass.

Commit: `rtk git add app/valuation/submissions tests/test_valuation_handoff_status.py tests/test_submission_api.py && rtk git commit -m "feat: expose safe valuation review handoff status"`

### Task 2: Register corrected submissions atomically

**Files:**
- Modify: `app/review/correction_service.py`
- Modify: `app/valuation/submissions/service.py`
- Modify: `tests/test_submission_service.py`
- Modify: `tests/test_correction_service_locking.py`

**Interfaces:**
- Consumes: existing `CorrectionService.register_resubmission()` validation and existing `SubmissionService.submit()` locks/readiness gates.
- Produces: `CorrectionService.register_latest_resubmission(review_id, payload, actor_id)`; a revision call to `SubmissionService.submit()` creates Submission N+1 and marks the active request `RESUBMITTED` in one transaction.

- [ ] **Step 1: Write failing service tests for success, rollback, and retry**

```python
@pytest.mark.asyncio
async def test_revision_submission_registers_active_correction_response():
    service, state, owner, first = setup_service()
    await service.submit(state.case.case_id, first, owner)
    state.case.case_status = "REVISION_REQUIRED"
    newer = prepare_newer_command_and_inputs(state, first)
    registrar = FakeRevisionRegistrar()

    result = await SubmissionService(
        None,
        repository=StatefulRepository(state),
        revision_registrar=registrar,
    ).submit(state.case.case_id, newer, owner)

    assert result.submission_no == 2
    assert registrar.calls == [
        (state.review.review_id, newer.source_report_document_id, 2, owner.user_id)
    ]


@pytest.mark.asyncio
async def test_revision_registration_failure_does_not_commit_partial_state(db_session):
    with pytest.raises(AppError):
        await submit_revision_with_wrong_document_lineage(db_session)
    await db_session.rollback()
    assert await count_submission_rows(db_session) == 1
    assert await correction_status(db_session) == "SENT"
```

- [ ] **Step 2: Verify RED**

Run: `rtk pytest tests/test_submission_service.py tests/test_correction_service_locking.py -q`

Expected: failures for the missing registrar interface and method.

- [ ] **Step 3: Refactor correction registration into one shared validator**

```python
async def register_latest_resubmission(
    self,
    review_id: UUID,
    payload: CorrectionResubmissionCreate,
    actor_id: UUID,
):
    request = await self.corrections.active_for_review(review_id, for_update=True)
    if request is None or request.status != "SENT":
        raise AppError(
            "CORRECTION_RESUBMISSION_INVALID",
            "找不到等待補正的修正通知",
            409,
        )
    return await self._register_locked_resubmission(request, payload, actor_id)
```

Move the existing ownership, lineage, version, timestamps, and `RESUBMITTED` mutation into `_register_locked_resubmission()`. Keep `register_resubmission(request_id, ...)` calling the same helper so the Review route remains compatible.

- [ ] **Step 4: Invoke the registrar only for a real revision**

```python
was_revision = case.case_status == "REVISION_REQUIRED"
# existing readiness, snapshot, Submission, pointers, event, and flush logic stay unchanged
if was_revision:
    registrar = self.revision_registrar or self._build_revision_registrar()
    await registrar.register_latest_resubmission(
        review.review_id,
        CorrectionResubmissionCreate(
            document_id=command.source_report_document_id,
            document_version=inputs.source_report_document.version_no,
        ),
        actor.user_id,
    )
```

Build the default registrar with the same request-scoped session:

```python
def _build_revision_registrar(self) -> CorrectionService:
    return CorrectionService(
        ReviewRepository(self.repository.session),
        CorrectionRepository(self.repository.session),
    )
```

- [ ] **Step 5: Preserve idempotent retry behavior**

Keep the existing `find_by_request()` early return before revision registration. Add an assertion that retrying the same `request_id` returns the same Submission and does not call the registrar twice.

- [ ] **Step 6: Run service and real handoff tests, then commit**

Run: `rtk pytest tests/test_submission_service.py tests/test_correction_service_locking.py tests/integration/test_valuation_review_handoff.py -q`

Expected: all tests pass; the real test observes Submission 2, correction `RESUBMITTED`, matching response document, and unchanged Submission 1 fingerprint.

Commit: `rtk git add app/review/correction_service.py app/valuation/submissions/service.py tests/test_submission_service.py tests/test_correction_service_locking.py tests/integration/test_valuation_review_handoff.py && rtk git commit -m "feat: link corrected valuation submissions to review"`

### Task 3: Add a development APPRAISER login command

**Files:**
- Create: `app/valuation/demo.py`
- Create: `tests/test_valuation_demo.py`

**Interfaces:**
- Consumes: the existing auth tables, password hashing, APPRAISER role, and existing permissions.
- Produces: `python -m app.valuation.demo seed` and `python -m app.valuation.demo reset`.

- [ ] **Step 1: Write failing command tests**

```python
def test_seed_prints_login_without_persisting_plaintext_password(monkeypatch):
    result = demo.seed(password="ValuationDemo123!")
    assert result["username"] == "valuation_demo"
    assert result["password"] == "ValuationDemo123!"
    assert "valuation.submit_review" in result["permissions"]
    assert "ValuationDemo123!" not in captured_database_values()


def test_demo_command_refuses_non_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(demo.DemoError, match="development"):
        demo.seed()
```

- [ ] **Step 2: Verify RED**

Run: `rtk pytest tests/test_valuation_demo.py -q`

Expected: import fails because `app.valuation.demo` does not exist.

- [ ] **Step 3: Implement a narrowly scoped account seed**

The command must upsert one active `valuation_demo` user, attach only the active APPRAISER role, verify the required permission set, print the generated password once, and make `reset` delete only this fixed user and its role association. It must not seed a case because the UI tests case creation itself.

Required permission check:

```python
REQUIRED_PERMISSIONS = {
    "case.create",
    "case.read",
    "case.update",
    "valuation.read",
    "valuation.update",
    "valuation.submit_review",
    "document.upload",
    "document.download",
}
```

- [ ] **Step 4: Run tests and commit**

Run: `rtk pytest tests/test_valuation_demo.py tests/test_permissions.py -q`

Expected: all tests pass.

Commit: `rtk git add app/valuation/demo.py tests/test_valuation_demo.py && rtk git commit -m "feat: add valuation demo login command"`

### Task 4: Serve the development-only test page

**Files:**
- Modify: `app/valuation/router.py`
- Create: `app/valuation/test_ui/index.html`
- Create: `tests/test_valuation_test_ui.py`

**Interfaces:**
- Consumes: `get_settings().app_env` and the existing Valuation router prefix.
- Produces: `GET /api/v1/valuation/test-ui`.

- [ ] **Step 1: Write failing route and HTML contract tests**

```python
def test_valuation_test_ui_is_available_only_in_development(monkeypatch):
    monkeypatch.setattr(
        "app.valuation.router.get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )
    response = TestClient(app).get("/api/v1/valuation/test-ui")
    assert response.status_code == 200
    assert "估價製作測試台" in response.text
    assert 'id="login-view"' in response.text
    assert 'id="case-list"' in response.text
    assert 'id="intake-step"' in response.text
    assert 'id="candidate-step"' in response.text
    assert 'id="formal-step"' in response.text
    assert 'id="correction-panel"' in response.text


def test_valuation_test_ui_is_404_in_production(monkeypatch):
    monkeypatch.setattr(
        "app.valuation.router.get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )
    assert TestClient(app).get("/api/v1/valuation/test-ui").status_code == 404
```

- [ ] **Step 2: Verify RED**

Run: `rtk pytest tests/test_valuation_test_ui.py -q`

Expected: 404 in development because the route and HTML do not exist.

- [ ] **Step 3: Add the guarded route**

```python
TEST_UI_PATH = Path(__file__).with_name("test_ui") / "index.html"


@router.get("/test-ui", include_in_schema=False)
async def valuation_test_ui() -> FileResponse:
    if get_settings().app_env.lower() != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(TEST_UI_PATH, media_type="text/html; charset=utf-8")
```

- [ ] **Step 4: Build the accessible page shell**

Use semantic forms, visible labels, `aria-live="polite"`, keyboard focus styles, `prefers-reduced-motion`, responsive single-column fallback, and a collapsed `<details id="developer-drawer">`. The shell must contain only Chinese business labels; IDs remain hidden in the developer drawer.

- [ ] **Step 5: Run tests and commit**

Run: `rtk pytest tests/test_valuation_test_ui.py -q`

Expected: both environment tests and the HTML contract pass.

Commit: `rtk git add app/valuation/router.py app/valuation/test_ui/index.html tests/test_valuation_test_ui.py && rtk git commit -m "feat: add development valuation test page"`

### Task 5: Implement intake, confirmation, formal report, and first submission UI

**Files:**
- Modify: `app/valuation/test_ui/index.html`
- Create: `tests/test_valuation_ui_behavior.mjs`
- Modify: `tests/test_valuation_test_ui.py`

**Interfaces:**
- Consumes: `/auth/login`, `/auth/me`, `/valuation/cases`, `auto-workflows/intake`, `auto-workflow/review`, `auto-workflow/confirm`, formal calculation/validation/PDF endpoints, complete-report download, and `submit-for-review`.
- Produces: client functions `request()`, `submitIntake()`, `confirmCandidates()`, `runFormalWorkflow()`, `submitForReview()`, `downloadAuthorizedBlob()`, and pure `window.valuationUiLogic` helpers.

- [ ] **Step 1: Write failing JavaScript tests for labels, request bodies, and redaction**

```javascript
test("builds an explicit confirmation request", () => {
  assert.deepEqual(logic.buildConfirmationRequest([
    {document_id:"d1", extracted_field_id:"f1", choice:"CONFIRM", corrected_value:"120"},
    {document_id:"d2", extracted_field_id:"f2", choice:"REJECT", corrected_value:"ignored"}
  ]), {
    confirm_apply:true,
    confirmations:[
      {document_id:"d1", extracted_field_id:"f1", decision:"CONFIRM", corrected_value:"120"},
      {document_id:"d2", extracted_field_id:"f2", decision:"REJECT", corrected_value:null}
    ]
  });
});

test("redacts credentials and storage internals", () => {
  const safe = logic.redactForLog({password:"secret", access_token:"jwt", object_key:"cases/a.pdf"});
  assert.deepEqual(safe, {password:"[REDACTED]", access_token:"[REDACTED]", object_key:"[REDACTED]"});
});
```

- [ ] **Step 2: Verify RED**

Run: `rtk test node --test tests/test_valuation_ui_behavior.mjs`

Expected: failure because `valuationUiLogic` is not exported.

- [ ] **Step 3: Implement one authenticated request wrapper**

```javascript
async function request(path,{method="GET",body,formData}={}){
  const headers={};
  if(state.token)headers.Authorization=`Bearer ${state.token}`;
  if(body!==undefined)headers["Content-Type"]="application/json";
  const response=await fetch(`/api/v1${path}`,{
    method,headers,body:formData||(
      body===undefined?undefined:JSON.stringify(body)
    )
  });
  const payload=response.headers.get("content-type")?.includes("json")
    ?await response.json():null;
  logRequest(method,path,response.status,redactForLog(payload));
  if(!response.ok)throw new UiError(response.status,payload);
  return payload;
}
```

- [ ] **Step 4: Build multipart intake from normal form controls**

`submitIntake()` must create `intake_manifest_json` from named case, parcel, benchmark, prepared-date, commercial-report, and category-override controls, append every selected file, and save the returned `case_id`, `report_id`, forms, documents, and candidates in page state. Users never type JSON.

- [ ] **Step 5: Render candidates and require a decision on every pending item**

Show Chinese field label, extracted and normalized value, filename, page, evidence text, and confidence. Never preselect CONFIRM. Disable apply until every `NEEDS_CONFIRMATION` item has an explicit choice.

- [ ] **Step 6: Run the existing formal sequence and preserve server gates**

Call, in order:

```text
POST /valuation/cases/{case_id}/reports/{report_id}/formal-calculation
POST /valuation/cases/{case_id}/reports/{report_id}/formal-validation
POST /valuation/cases/{case_id}/reports/{report_id}/formal-pdf
```

Pass `{confirm_calculation:true}` and `{confirm_generate:true, acknowledged_warning_codes:[...]}` only after an explicit user click. Store `validation_run_id`, `document_id`, `version_no`, and `download_path` from server responses. Display blockers and warnings in Chinese.

- [ ] **Step 7: Submit the exact server-produced IDs**

```javascript
function buildSubmitCommand(reportPackage,formalValidation,formalReport){
  return {
    request_id:crypto.randomUUID(),
    expected_case_version:reportPackage.version_no,
    source_validation_run_id:formalValidation.validation_run_id,
    source_report_document_id:formalReport.document_id
  };
}
```

Keep one request ID for retries until the server confirms success. After success, refresh `/valuation/cases/{case_id}/review-handoff` and lock the editing controls while status is `IN_REVIEW`.

- [ ] **Step 8: Download PDFs through authenticated fetch**

Fetch the server path with the Authorization header, turn the response into a Blob URL, trigger the download, then call `URL.revokeObjectURL()`. Do not put object keys or storage URLs into anchors.

- [ ] **Step 9: Run tests and commit**

Run: `rtk test node --test tests/test_valuation_ui_behavior.mjs`

Run: `rtk pytest tests/test_valuation_test_ui.py tests/test_auto_workflow.py tests/test_submission_api.py -q`

Expected: all tests pass.

Commit: `rtk git add app/valuation/test_ui/index.html tests/test_valuation_ui_behavior.mjs tests/test_valuation_test_ui.py && rtk git commit -m "feat: support valuation intake and first submission in test UI"`

### Task 6: Implement the returned-correction and supplement UI

**Files:**
- Modify: `app/valuation/test_ui/index.html`
- Modify: `tests/test_valuation_ui_behavior.mjs`
- Modify: `tests/test_valuation_test_ui.py`

**Interfaces:**
- Consumes: `GET /valuation/cases/{case_id}/review-handoff`, existing document/version APIs, formal workflow endpoints, and the atomically extended `submit-for-review` behavior.
- Produces: `renderHandoff()`, `renderCorrectionItems()`, `renderMissingItems()`, `startRevision()`, and `resubmitForReview()`.

- [ ] **Step 1: Write failing UI-state tests**

```javascript
test("maps returned cases to a clear action",()=>{
  assert.deepEqual(logic.handoffView({case_status:"REVISION_REQUIRED",correction:{status:"SENT"}}),{
    label:"退回補正",editable:true,primaryAction:"開始補正"
  });
});

test("separates content corrections from missing materials",()=>{
  const groups=logic.groupRevisionNeeds({
    correction:{items:[{finding_code:"DATE",requested_correction:"更正價格日期"}]},
    missing_items:[{item_code:"LAND_REGISTER",item_name:"土地登記謄本"}]
  });
  assert.equal(groups.content.length,1);
  assert.equal(groups.materials.length,1);
});
```

- [ ] **Step 2: Verify RED**

Run: `rtk test node --test tests/test_valuation_ui_behavior.mjs`

Expected: failures for missing handoff helpers.

- [ ] **Step 3: Render the correction notice as read-only Review content**

Show the notice message, due date, issue summary, requested correction, document name/page when available, and two separate headings: `內容需要修改` and `需要補充資料`. Do not provide controls that alter the correction request or Review finding.

- [ ] **Step 4: Re-enable only Valuation editing actions**

When `case_status === "REVISION_REQUIRED"`, allow form edits, new document versions, extraction, candidate confirmation, calculation, validation, and report generation. Continue disabling edit actions for `IN_REVIEW` and `REVIEW_COMPLETED`.

- [ ] **Step 5: Reuse the formal workflow for the corrected version**

Require a new report version and a newer expected case version. Keep Submission 1 details visible in history. `resubmitForReview()` uses a fresh request ID, the new validation Run, and the new report document; it never asks for correction-request ID, Review ID, document ID, or version in a text box.

- [ ] **Step 6: Refresh both sides after resubmission**

After success, reload the Valuation case, document/form progress, and handoff projection. The expected view is `已重新送審`, correction status `RESUBMITTED`, and Submission number 2 or greater.

- [ ] **Step 7: Run tests and commit**

Run: `rtk test node --test tests/test_valuation_ui_behavior.mjs`

Run: `rtk pytest tests/test_valuation_test_ui.py tests/test_valuation_handoff_status.py tests/test_submission_service.py -q`

Expected: all tests pass.

Commit: `rtk git add app/valuation/test_ui/index.html tests/test_valuation_ui_behavior.mjs tests/test_valuation_test_ui.py && rtk git commit -m "feat: support returned valuation corrections and resubmission"`

### Task 7: Prove the complete loop and publish the test guide

**Files:**
- Modify: `tests/integration/test_valuation_review_handoff.py`
- Create: `app/valuation/TEST_UI_GUIDE.md`

**Interfaces:**
- Consumes: all prior tasks and the existing Review workbench correction/recheck APIs.
- Produces: one repeatable automated end-to-end test, one real-browser acceptance record, and a copyable local runbook.

- [ ] **Step 1: Extend the real integration test**

The test must assert this exact sequence:

```python
assert first_submission.submission_no == 1
await review_run_and_triage()
assert await status_pair() == ("REVIEW_REQUIRED", "IN_REVIEW")
assert await send_correction() == ("RETURNED_FOR_REVISION", "REVISION_REQUIRED")
assert (await appraiser_handoff()).correction.status == "SENT"
assert revised_submission.submission_no == 2
assert (await appraiser_handoff()).correction.status == "RESUBMITTED"
assert rechecked_run.submission_id == revised_submission.submission_id
assert first_submission.input_fingerprint == original_fingerprint
```

Run one scenario correcting a content value and one scenario uploading a newer document in the same document group.

- [ ] **Step 2: Run the full relevant suite**

Run: `rtk pytest tests app/review/tests -q`

Expected: zero failures. Record the exact passed/skipped counts in the guide instead of predicting them.

- [ ] **Step 3: Run the isolated PostgreSQL/MinIO suite**

Run: `rtk proxy pwsh -File scripts/run-integration-tests.ps1 -PytestArgs "tests/integration/test_valuation_review_handoff.py tests/integration/test_submission_command.py"`

Expected: exit code 0, no leftover test database, and no leftover test objects.

- [ ] **Step 4: Perform real-browser acceptance**

Start the existing Compose services, seed `valuation_demo` and the Review demo user, then complete:

```text
Valuation login
→ intake and upload
→ candidate decisions
→ formal calculation, validation, and PDF
→ first submission
→ Review sends correction
→ Valuation reads the reason and changes data or uploads a new version
→ corrected formal report and resubmission
→ Review sees the corrected version without ID entry
→ Review rechecks
```

Inspect the browser console and network panel for errors. Verify password/JWT/object key values are absent from rendered logs.

- [ ] **Step 5: Write the concise operating guide**

Document the page URL, two Demo seed commands, the six visible case statuses, the normal path, the returned-correction path, reset commands, and the recorded automated/browser verification. Clearly label draft PDFs versus formal submission reports.

- [ ] **Step 6: Final verification and commit**

Run: `rtk git diff --check`

Run: `rtk git status --short`

Expected: only the intended guide and test changes remain; unrelated `.serena/` and `app/review/MANUAL_INTEGRATION_TEST_GUIDE.md` stay untracked and unstaged.

Commit: `rtk git add tests/integration/test_valuation_review_handoff.py app/valuation/TEST_UI_GUIDE.md && rtk git commit -m "test: verify valuation correction loop"`

## Completion Criteria

- A non-technical tester completes first submission from `/api/v1/valuation/test-ui` without Swagger or manual JSON.
- An appraiser sees Review correction reasons and missing-material requests on the same page.
- A corrected report creates a new immutable Submission and automatically registers the response on the active correction request.
- Review can recheck the corrected Submission without manually entering document IDs.
- Old submissions, runs, findings, decisions, files, and fingerprints remain unchanged.
- Development guards, permission checks, redaction tests, the relevant full suite, isolated PostgreSQL/MinIO tests, and one real-browser run all pass.
