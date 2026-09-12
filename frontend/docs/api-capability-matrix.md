# Demo API capability matrix

This matrix freezes the API boundary used by the Vue demo. The full prefix is
`/api/v1`: `app/main.py:34` mounts the API router with
`app/core/config.py:22`'s `/api/v1` default, and `app/api/router.py:19-40`
mounts the Auth, History, Valuation, Review, and Assistant routers.

## OpenAPI artifact and provenance

[`openapi-target.json`](./openapi-target.json) is a scoped, valid OpenAPI
artifact derived from the real `app.openapi()` document in an isolated one-off
API container with this worktree mounted read-only on 2026-09-08. It contains
38 Demo paths, 39 operations, and only their 83 transitively referenced
schemas (plus `HTTPBearer`). The source provenance is:

- source branch: `codex/frontend-demo`
- source commit: `f3bb8d02c4f95e671d39010e51baf0226c2ae0ef` (`fix(demo): scope rule-source cleanup by validated id`)
- generation method: `from app.main import app; app.openapi()` from the
committed backend source, then mechanically retain the existing Demo path
allowlist plus the mounted Assistant question and progress routes and their complete
transitive `$ref` closure
- runtime boundary: the isolated Compose `api` image was used only for this
  source-derived document; the primary API service and existing containers were
  not changed

Every structured row below is backed by the corresponding path/method and
`$ref` in the artifact. The router and service references explain permissions
and runtime invariants. `VERIFIED` means present in the artifact and mounted
through the target app; no required router is blocked. Download rows explicitly
separate what the generated OpenAPI declares from source/runtime behavior.

| capability | fully mounted OpenAPI path | request schema and parameters | response schema | permission | source verification evidence | Demo status |
| --- | --- | --- | --- | --- | --- | --- |
| Auth | `POST /api/v1/auth/login` | JSON `LoginRequest` (`username: string`, `password: string`) | `TokenResponse` | Public | artifact path; `app/api/router.py:19`; `app/auth/router.py:13`; `app/auth/schemas.py:6-14` | VERIFIED |
| Auth | `GET /api/v1/auth/me` | No body or query parameters | `CurrentUserResponse` | Authenticated bearer (`HTTPBearer`) | artifact path/security; `app/api/router.py:19`; `app/auth/router.py:20`; `app/auth/dependencies.py:24-31` | VERIFIED |
| Valuation | `GET /api/v1/valuation/form-types` | No body or query parameters | `list[FormRequirementResponse]`; form type enum `FormCode` = `F01`, `F02`, `F03`, `F04`, `S01`, `F02-RF` | `valuation.read` | artifact path; `app/valuation/router.py:75-78`; `app/valuation/schemas.py:181-189`; `app/api/router.py:22` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases` | Query `case_status?: CaseStatus` (`DRAFT`, `PROCESSING`, `REVIEWING`, `CORRECTION`, `COMPLETED`, `ARCHIVED`, `IN_REVIEW`, `REVISION_REQUIRED`, `REVIEW_COMPLETED`), `offset?: integer >= 0` default `0`, `limit?: integer 1..100` default `50` | `list[CaseResponse]` | `case.read` | artifact parameters/security; `app/valuation/router.py:175-190`; `app/valuation/schemas.py:8-19,64-82`; `tests/test_valuation_routes.py:6-65` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}` | Path `case_id: UUID` | `CaseResponse` | `case.read` | artifact path/parameter/security; `app/valuation/router.py:192-200`; `tests/test_valuation_routes.py:8,65` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}/forms` | Path `case_id: UUID`; no body/query | `list[FormResponse]` (each item exposes `form_instance_id` and `form_code`) | `valuation.read` | artifact path/response/security; `app/valuation/router.py:308-315`; `app/valuation/schemas.py:209-226`; `tests/test_valuation_routes.py:19,65` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}/forms/{form_id}` | Path `case_id: UUID`, `form_id: UUID` | `FormResponse` | `valuation.read` | artifact path/parameters/security; `app/valuation/router.py:318-327`; `tests/test_valuation_routes.py:20,65` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}/forms/{form_id}/f03` | Path `case_id: UUID`, `form_id: UUID` | `F03DraftResponse` (includes `form_instance_id: UUID | null`) | `valuation.read` | artifact `$ref`/security; `app/valuation/router.py:330-340`; `app/valuation/f03_schemas.py:56-82` | VERIFIED |
| Valuation | `PATCH /api/v1/valuation/cases/{case_id}/forms/{form_id}/f03` | Path `case_id: UUID`, `form_id: UUID`; JSON `F03DraftUpdate` (`benchmark_land_id`, `comparison_analysis_id`, `valuation_base_date`, `comparison_price`, `comparison_weight`, `income_price`, `income_weight`, `market_period_start`, `market_period_end`, `market_condition`, `selection_scope_reason`, `decision_reason`; at least one field required) | `F03DraftResponse` | `valuation.update` | artifact `$ref`/security; `app/valuation/router.py:407-419`; `app/valuation/f03_schemas.py:31-54` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}/benchmark-lands` | Path `case_id: UUID`; no body/query | `list[BenchmarkLandResponse]` | `case.read` | artifact path/response/security; `app/valuation/router.py:280-290`; `app/valuation/f03_schemas.py:17-28` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}/documents` | Path `case_id: UUID`; no body/query | `list[DocumentResponse]`; each item contains document metadata (`document_id`, `document_group_id`, `case_id`, `document_type`, filename/MIME, storage metadata, version, uploader, timestamp, active flag), never PDF/image bytes | `document.download` | artifact path/response/security; `app/valuation/documents/router.py:49-54`; `app/valuation/documents/schemas.py:20-37`; mounted by `app/api/router.py:23` | VERIFIED |
| Valuation | `POST /api/v1/valuation/cases/{case_id}/calculations` | Path `case_id: UUID`; JSON `CalculationRequest` (`form_instance_id: UUID`) | `CalculationResponse` | `valuation.update` | artifact path/$ref/security; `app/valuation/operations/router.py:37-52`; `app/valuation/operations/schemas.py:8-24` | VERIFIED |
| Valuation | `POST /api/v1/valuation/cases/{case_id}/validations` | Path `case_id: UUID`; JSON `ValidationRequest` (`form_instance_id: UUID`) | `ValidationResponse` | `valuation.update` | artifact path/$ref/security; `app/valuation/operations/router.py:67-83`; `app/valuation/operations/schemas.py:26-56` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}/validations/{validation_run_id}` | Path `case_id: UUID`, `validation_run_id: UUID`; no body/query | `ValidationResponse` | `valuation.read` | artifact path/parameters/security; `app/valuation/operations/router.py:85-99`; `tests/test_valuation_routes.py:46,65` | VERIFIED |
| Valuation | `GET /api/v1/valuation/cases/{case_id}/report-progress` | Path `case_id: UUID`; no body/query | `ReportProgressResponse` (`report_id: UUID \| null`, `report_type: ReportType`, `version_no: integer \| null`, `completion_rate: string`, `sections: list[ReportProgressSectionResponse]`, `blocking_errors: list[string]`) | `valuation.read` | artifact path/$ref/security; `app/valuation/report_packages/router.py:128-135`; `app/valuation/report_packages/schemas.py:62-76`; mounted by `app/api/router.py:26-29` | VERIFIED |
| Valuation | `POST /api/v1/valuation/cases/{case_id}/reports` | Path `case_id: UUID`; JSON `ReportRequest` (`form_instance_id: UUID`) | `ReportResponse` | `valuation.update` | artifact path/$ref/security; `app/valuation/operations/router.py:101-117`; `app/valuation/operations/schemas.py:58-73` | VERIFIED |
| Valuation | `POST /api/v1/valuation/cases/{case_id}/reports/{report_id}/formal-validation` | Path `case_id: UUID`, `report_id: UUID`; no request body (the server reads request context for idempotency) | `FormalValidationResponse` (`validation_run_id`, `case_id`, `report_id`, completed status/counts, `can_generate_formal_report`, optional fingerprint, findings, completion time) | `valuation.update` | artifact path/$ref/security; `app/valuation/report_packages/router.py:387-399`; `app/valuation/report_packages/formal_schemas.py:39-59`; mounted by `app/api/router.py:26-29` | VERIFIED |
| Valuation | `POST /api/v1/valuation/cases/{case_id}/reports/{report_id}/formal-pdf` | Path `case_id: UUID`, `report_id: UUID`; JSON `FormalReportRequest` (`confirm_generate: boolean` must be `true`, `acknowledged_warning_codes: list[string]`) | `FormalReportResponse` (`document_id`, `case_id`, `report_id`, authoritative `validation_run_id`, PDF filename/MIME/version, storage metadata, `download_path`, optional request ID); successful generation transitions the report forms to `FINAL` and binds the returned document as their output | `valuation.update` | artifact path/$ref/security; `app/valuation/report_packages/router.py:400-420`; `app/valuation/report_packages/formal_schemas.py:68-96`; mounted by `app/api/router.py:26-29` | VERIFIED |
| Valuation | `POST /api/v1/valuation/cases/{case_id}/forms/{form_id}/submit` | Path `case_id: UUID`, `form_id: UUID`; no body/query | `FormResponse` | `valuation.update` | artifact path/parameters/security; `app/valuation/router.py:476-487`; `tests/test_valuation_routes.py:21,65` | VERIFIED |
| Valuation | `POST /api/v1/valuation/cases/{case_id}/submit-for-review` | Path `case_id: UUID`; JSON `SubmitForReviewCommand` (`request_id: UUID`, `expected_case_version: integer >= 1`, `source_validation_run_id: UUID`, `source_report_document_id: UUID`) | `SubmitForReviewResult` | `valuation.submit_review` | artifact path/$ref/security; `app/api/router.py:38`; `app/valuation/submissions/router.py:17-29`; `app/valuation/submissions/schemas.py:7-20`; `tests/test_integration_surface.py:6-7` | VERIFIED |
| Review | `GET /api/v1/review/workbench/summary` | No body or query parameters | `WorkbenchSummaryRead` | `review.execute` | artifact path/security; `app/review/router.py:152-157`; `app/review/workbench_schemas.py:23-27` | VERIFIED |
| Review | `GET /api/v1/review/workbench/cases` | Query `q?: string`, `status?: ReviewStatus` (`RECEIVED`, `PREPROCESSING`, `PENDING_MATERIALS`, `READY_FOR_REVIEW`, `ANALYZING`, `REVIEW_REQUIRED`, `RETURNED_FOR_REVISION`, `SUPPLEMENT_REQUIRED`, `EXPERT_REVIEW`, `APPROVED`, `REVIEW_COMPLETED`), `risk_level?: RiskLevel` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), `status_group?: WorkbenchStatusGroup` (`pending`, `in_progress`, `needs_input`, `completed`, `risk`), `limit?: integer 1..100` default `50`, `offset?: integer >= 0` default `0` | `WorkbenchCaseList` | `review.execute` | artifact parameters/security; `app/review/router.py:160-183`; `app/review/workbench_schemas.py:36-63`; `app/review/tests/test_workbench_api.py:522-538` | VERIFIED |
| Review | `GET /api/v1/review/workbench/cases/{review_id}` | Path `review_id: UUID` | `WorkbenchCaseDetailRead` (nested findings, documents, runs, decisions, reports) | `review.execute` | artifact path/parameter/security; `app/review/router.py:186-194`; `app/review/workbench_schemas.py:145-163`; `app/review/tests/test_workbench_api.py:548-550` | VERIFIED |
| Review | `GET /api/v1/review/workbench/cases/{review_id}/documents/{document_id}/content` | Path `review_id: UUID`, `document_id: UUID`; no body/query | OpenAPI 200 observed: `application/json` with empty schema `{}`; source/runtime: `StreamingResponse`, PDF only (`application/pdf`) | `review.execute` | artifact path/parameters/security; source route `app/review/router.py:197-218`; runtime stream test `app/review/tests/test_workbench_api.py:1409-1427` | VERIFIED (frontend handles as blob; OpenAPI binary type is unresolved) |
| Review | `GET /api/v1/review/runs/{validation_run_id}/findings` | Path `validation_run_id: UUID` | `list[FindingRead]` | `review.execute` | artifact path/parameter/security; `app/review/router.py:408-415`; `app/review/schemas.py:162-194`; `app/review/tests/test_report_api.py:100-104` | VERIFIED |
| Review | `POST /api/v1/review/findings/{finding_id}/triage` | Path `finding_id: UUID`; JSON `FindingTriageRequest` (`review_id: UUID`, `decision: FindingTriageDecision`, `reason: string`, 1..2000 characters) | `DecisionRead` | `review.decide` | artifact path/$ref/security; `app/review/router.py:458-472`; `app/review/schemas.py:236-249,267-279`; `app/review/tests/test_report_api.py:104-113` | VERIFIED |
| Review | `POST /api/v1/review/cases/{review_id}/complete-review` | Path `review_id: UUID`; JSON `ReviewCompletionRequest` (`reason: string`, 1..2000 characters) | `DecisionRead` | `review.decide` | artifact path/$ref/security; `app/review/router.py:630-645`; `app/review/schemas.py:328-339,267-279`; `app/review/tests/test_report_api.py:187-205` | VERIFIED |
| Review | `GET /api/v1/review/runs/{validation_run_id}/report` | Path `validation_run_id: UUID`; no body/query | `ReviewReport` | `review.execute` | artifact path/$ref/security; `app/review/router.py:664-670`; `app/review/reports.py:134-145`; `app/review/tests/test_report_api.py:56-64` | VERIFIED |
| Review | `POST /api/v1/review/runs/{validation_run_id}/report/pdf` | Path `validation_run_id: UUID`; no body/query | `ReportDocumentRead` (alias of `GeneratedReportRead`) | `review.execute` | artifact path/$ref/security; `app/review/router.py:673-715`; `app/review/schemas.py:385-403`; `app/review/tests/test_report_api.py:65-88` | VERIFIED |
| Review | `POST /api/v1/review/runs/{validation_run_id}/reports` | Path `validation_run_id: UUID`; JSON `GeneratedReportCreate` (`format: ReportFormat`, enum `xlsx` or `docx`) | `GeneratedReportRead` | `review.execute` | artifact path/$ref/security; `app/review/router.py:781-820`; `app/review/schemas.py:385-408`; `app/review/tests/test_report_api.py:223-239` | VERIFIED |
| Review | `GET /api/v1/review/reports/{document_id}/download` | Path `document_id: UUID`; no body/query | OpenAPI 200 observed: `application/json` with empty schema `{}`; source/runtime: binary `Response` using stored report `mime_type` and `Content-Disposition` | `review.execute` | artifact path/parameter/security; source route `app/review/router.py:865-889`; report API exercise `app/review/tests/test_report_api.py:223-239` | VERIFIED (frontend handles as blob; OpenAPI binary type is unresolved) |
| History | `GET /api/v1/history/cases` | Query `keyword?: string` max 200, `city_code?: string` max 20, `district_code?: string` max 20, `section_name?: string` max 100, `result?: HistoryResult` (`PASSED`, `CORRECTION`, `RETURNED`, `SUPPLEMENT_REQUIRED`, `IN_PROGRESS`), `date_field?: DateField` (`updated_at`, `received_at`, `completed_at`) default `updated_at`, `date_from?: date`, `date_to?: date`, `sort?: HistorySort` (`updated_at`, `received_at`, `risk_level`) default `updated_at`, `order?: SortOrder` (`asc`, `desc`) default `desc`, `offset?: integer >= 0` default `0`, `limit?: integer 1..100` default `20` | `HistoryCasePage` | Authenticated bearer (`CurrentUser`) | artifact parameters/security; `app/api/router.py:20`; `app/history/router.py:36-67`; `app/history/schemas.py:5-46`; `tests/test_integration_surface.py:11` | VERIFIED |
| History | `GET /api/v1/history/cases/{case_id}` | Path `case_id: UUID`; no body/query | `HistoryCaseDetail` | Authenticated bearer (`CurrentUser`) | artifact path/parameter/security; `app/history/router.py:70-76`; `app/history/schemas.py:68-74` | VERIFIED |
| History | `GET /api/v1/history/documents/{document_id}/download` | Path `document_id: UUID`; no body/query | OpenAPI 200 observed: `application/json` with empty schema `{}`; source/runtime: `StreamingResponse` using stored document `mime_type` and attachment filename; missing object maps to `DOCUMENT_OBJECT_MISSING` 404 | Authenticated bearer (`CurrentUser`) | artifact path/parameter/security; route behavior `app/history/router.py:79-108` (including `StreamingResponse`) | VERIFIED (frontend handles as blob; OpenAPI binary type is unresolved) |
| Assistant | `POST /api/v1/ai-assistant/sessions` | JSON `AssistantSessionCreate` (`case_id: UUID`, `form_instance_id: UUID`, `selected_form_type: string`, fixed pattern `F03`) | `AssistantSessionResponse` | `assistant.use + valuation.read` | artifact path/$ref/security; `app/ai_assistant/router.py:22-32,51-57`; `app/ai_assistant/schemas.py:11-29`; `tests/test_integration_surface.py:8-9` | VERIFIED |
| Assistant | `GET /api/v1/ai-assistant/sessions/{session_id}` | Path `session_id: UUID`; no body/query | `AssistantSessionResponse` | `assistant.use + valuation.read` | artifact path/parameter/security; `app/ai_assistant/router.py:61-68,22-25`; `app/ai_assistant/service.py:129-134`; `tests/test_valuation_routes.py:40-41,65` | VERIFIED |
| Assistant | `GET /api/v1/ai-assistant/sessions/{session_id}/progress` | Path `session_id: UUID`; no body/query | `AssistantProgressResponse` | `assistant.use + valuation.read` | artifact path/parameter/security; `app/ai_assistant/router.py:74-79`; `app/ai_assistant/schemas.py:38-46`; `app/ai_assistant/service.py:136-140` | VERIFIED |
| Assistant | `POST /api/v1/ai-assistant/sessions/{session_id}/messages` | Path `session_id: UUID`; JSON `AssistantMessageRequest` (`content` 1..4000, optional confirmations/actions; `nearest_facility` requires `confirm_action=true`) | `AssistantMessageResponse` (citation-free workflow response) | `assistant.use + valuation.read`; workflow mutation tools additionally require `valuation.update` | artifact path/$ref/security; `app/ai_assistant/router.py:105-119`; `app/ai_assistant/schemas.py:92-126`; `app/ai_assistant/service.py:541-661` | VERIFIED |
| Assistant | `POST /api/v1/ai-assistant/sessions/{session_id}/questions` | Path `session_id: UUID`; JSON `AssistantQuestionRequest` (`question` 2..2000, optional `as_of_date`, `document_types` max 10, `limit` 1..10) | `AssistantQuestionResponse` (`answer_status`, `claims: list[AssistantClaim]`, `citations: list[AssistantCitation]`, `unreadable_sources`) | `assistant.use + valuation.read + knowledge.read + case.read` | artifact path/$ref/security; `app/ai_assistant/router.py:86-100,26-39`; `app/ai_assistant/schemas.py:49-90`; `app/ai_assistant/service.py:142-163` | VERIFIED |

## Assistant authorization and Demo isolation

Assistant authorization is permission-code-only. The route dependencies evaluate
the current effective permission set on every request; revoking a code therefore
blocks the next request immediately, without relying on a role name or a cached
frontend gate. Session ownership is also checked server-side: a session is bound
to its creating `user_id`, and another user receives a safe denial.

The cited question endpoint accepts only `session_id` plus the question payload.
The service loads the case context stored on that session, so callers cannot
substitute an arbitrary `case_id`. A question additionally requires
`knowledge.read` and `case.read`. Workflow mutation tools remain behind the
same Assistant session permissions and check `valuation.update` immediately
before execution; read-only tools do not inherit that mutation permission.

Migration `20260908_0015` registers `assistant.use` without granting it to any
production role. The development seed never edits `APPRAISER` role permissions:
it owns the `DEMO_ASSISTANT_APPRAISER` companion role, replaces only that role's
permissions with `assistant.use`, and links that companion role to all three owned
Demo personas (`valuation_demo`, `review_demo`, and `inspector_demo`) alongside
their normal `APPRAISER`, `REVIEWER`, or `INSPECTOR` role. This keeps the same AI
assistant shell available in Valuation, Review, and History without changing any
production-role grants. Seed/status output contains only the safe username, role
codes, and permission codes; the generated password is returned only by the
one-time `seed` command. Reset removes only the Demo users' links/users and drops
the companion role only when no external user link or unexpected permission
ownership makes deletion unsafe.

## Frontend route permission boundary

The Vue `valuation-submit` route requires all of `case.read`, `valuation.read`,
`valuation.submit_review`, `valuation.update`, and `document.download`.
`valuation.read` is required because the page reads the case forms and report
progress before it can build the submission source; the API's final
`submit-for-review` operation itself remains protected by
`valuation.submit_review`.

## Server-side Valuation boundary

`POST /api/v1/valuation/cases/{case_id}/validations` is the mounted F03 MVP
validation endpoint. Its OpenAPI body is only `ValidationRequest` with
`form_instance_id`; the concrete F03-only rule is enforced server-side in
`app/valuation/operations/router.py:67-83` calling
`ValidationService.run_f03`, and
`app/valuation/operations/validation_service.py:49-66` rejects any form whose
`form_code` is not `F03` with `FORM_TYPE_MISMATCH` (HTTP 422). The frontend
must send the `form_instance_id` discovered from `GET .../forms`, then read the
server's `ValidationResponse`; it must not reproduce this rule or calculation.

The legacy `POST /api/v1/review/findings/{finding_id}/decisions` and
`POST /api/v1/review/cases/{review_id}/decision` routes remain disabled by the
backend. The demo uses `/triage` and `/complete-review` above.

## Download contract boundary

The generated OpenAPI artifact intentionally preserves FastAPI's observed
declaration for the three download/content operations above: HTTP 200 is
advertised as `application/json` with an empty schema. It does not prove a
binary response. Source inspection and the Review workbench runtime test prove
the current server behavior: the workbench document route streams PDF bytes;
the History route streams the stored document media type; and the generated
Review report route returns stored report bytes. The frontend boundary is to
request these endpoints as a blob and use response headers/content type at
runtime. A History/download runtime smoke test is deferred to the later
integration task because this task has no persistent document fixture; no
OpenAPI row is falsified or treated as binary solely from source behavior.

## Toolchain floor

The installed Vite 8 package declares `node: ^20.19.0 || >=22.12.0` in
`frontend/node_modules/vite/package.json:178-180` and the lockfile. The
frontend package declares the same `engines.node` range; this checkout's
Node `v22.18.0` satisfies it.
