# Review MVP API Capability Matrix

Verified against the current `feature/case-history` working tree before frontend implementation.

| Capability | Method / endpoint | Request | Response | Permission | Evidence |
| --- | --- | --- | --- | --- | --- |
| Login | `POST /api/v1/auth/login` | `LoginRequest { username, password }` | `TokenResponse { access_token, token_type, expires_in }` | public | `app/auth/router.py`, `app/auth/schemas.py` |
| Current user | `GET /api/v1/auth/me` | Bearer token | `CurrentUserResponse` | authenticated | `app/auth/router.py`, `app/auth/schemas.py` |
| Workbench summary | `GET /api/v1/review/workbench/summary` | none | `WorkbenchSummaryRead` | `review.execute` | `app/review/router.py`, `app/review/workbench_schemas.py` |
| Workbench queue | `GET /api/v1/review/workbench/cases` | `q`, `status`, `risk_level`, `status_group`, `limit`, `offset` | `WorkbenchCaseList` | `review.execute` | `app/review/router.py`, `app/review/workbench_schemas.py` |
| Workbench detail | `GET /api/v1/review/workbench/cases/{review_id}` | path id | `WorkbenchCaseDetailRead` | `review.execute` | same |
| PDF content | `GET /api/v1/review/workbench/cases/{review_id}/documents/{document_id}/content` | path ids | PDF stream | `review.execute` | `app/review/router.py:197-236` |
| Start review | `POST /api/v1/review/workbench/cases/{review_id}/start` | no body | `WorkbenchStartRead` | `review.execute` | `app/review/router.py`, `app/review/workbench_schemas.py` |
| Finding triage | `POST /api/v1/review/findings/{finding_id}/triage` | `{ review_id, decision, reason }` | `DecisionRead` | `review.decide` | `app/review/router.py`, `app/review/schemas.py` |
| Correction draft | `POST /api/v1/review/cases/{review_id}/correction-requests` | `{ message, due_at }` | `CorrectionRequestRead` | `review.decide` | `app/review/router.py`, `app/review/schemas.py` |
| Correction send | `POST /api/v1/review/correction-requests/{id}/send` | empty object | `CorrectionRequestRead` | `review.decide` | `app/review/router.py`, `app/review/schemas.py` |
| Complete review | `POST /api/v1/review/cases/{review_id}/complete-review` | `{ reason }` | `DecisionRead` | `review.decide` | `app/review/router.py`, `app/review/schemas.py` |
| Structured report | `GET /api/v1/review/runs/{run_id}/report` | path id | `ReviewReport` | `review.execute` | `app/review/router.py`, `app/review/reports.py` |
| Generate PDF | `POST /api/v1/review/runs/{run_id}/report/pdf` | none | `GeneratedReportRead` | `review.execute` | `app/review/router.py`, `app/review/schemas.py` |
| Generate final XLSX/DOCX | `POST /api/v1/review/runs/{run_id}/reports` | `{ format: "xlsx" | "docx" }` | `GeneratedReportRead` | `review.execute` | `app/review/router.py`, `app/review/schemas.py` |
| Download report | `GET /api/v1/review/reports/{document_id}/download` | path id | file stream | `review.execute` | `app/review/router.py:865-891` |

## Contract adjustments from the implementation plan

- The queue endpoint exposes no client-selectable `sort` parameter. The frontend therefore uses server filtering and pagination while preserving the backend's canonical ordering.
- The legacy finding `/decisions` write endpoint and case `/decision` write endpoint are explicitly disabled with HTTP 409. The frontend uses `/findings/{finding_id}/triage`, correction-request endpoints, and `/complete-review` only.
- The verified seeded role is `REVIEWER`; there is no verified `SUPERVISOR` role in the current migrations. Route access is permission-driven (`review.execute` / `review.decide`) rather than trusting a role label alone.