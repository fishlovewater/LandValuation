# Case-history subsystem

Production History endpoints are read-only and do not create database tables or
write to Valuation, Review, or MinIO. The opt-in development demo command writes
only the deterministic test rows and object documented below.

## Exported router

Import `router` explicitly with `from app.history.router import router`. It exposes:

- `GET /history/cases` — authorized search, filters, sorting, and pagination.
- `GET /history/cases/{case_id}` — case, parcels, documents, and authorized
  structured Valuation/Review JSON.
- `GET /history/documents/{document_id}/download` — authorized MinIO download.
- `GET /history/test-ui` — development-only manual API console.

The application currently mounts routers explicitly from `app/api/router.py`.
The integrated application includes this router, so these endpoints are
available below `/api/v1/history` when the main API is running.

## Visibility rules

- `APPRAISER`: Valuation data only.
- `REVIEWER`: Review data only.
- both roles: both modules.
- `INSPECTOR`, `ADMIN`, `SYSTEM_ADMIN`, `SUPERADMIN`: both modules.

A case remains searchable when authorized structured SQL data exists even if no
document metadata exists. Missing MinIO content never removes a case from search;
it only makes the requested download unavailable.

## Demo data and storage locations

Run inside the API environment:

```text
python -m app.history.demo seed
python -m app.history.demo status
python -m app.history.demo reset
```

The command requires the same complete runtime dependencies as the API,
including a working `psycopg` driver and the `minio` Python package. A partial
local venv should use the API container instead.

Inside Compose, the demo prefers `POSTGRES_HOST=db` and
`MINIO_ENDPOINT=minio:9000` supplied by the API service. This prevents a mounted
host `.env` value containing `localhost` from pointing back at the one-off
container itself.

Windows Command Prompt (`cmd.exe`) example using the current source tree with
the API runtime:

```bat
docker compose --env-file .env up -d db minio minio-init
docker compose --env-file .env run --rm -v "%CD%:/app" api python -m app.history.demo seed
docker compose --env-file .env run --rm -v "%CD%:/app" api python -m app.history.demo status
docker compose --env-file .env run --rm -v "%CD%:/app" api python -m app.history.demo reset
```

PowerShell example:

```powershell
docker compose --env-file .env up -d db minio minio-init
docker compose --env-file .env run --rm -v "$((Get-Location).Path):/app" api python -m app.history.demo seed
docker compose --env-file .env run --rm -v "$((Get-Location).Path):/app" api python -m app.history.demo status
docker compose --env-file .env run --rm -v "$((Get-Location).Path):/app" api python -m app.history.demo reset
```

`seed` creates only these deterministic records in existing tables:

| username | password | role | expected History visibility |
|---|---|---|---|
| `history_appraiser` | `HistoryDemo123!` | `APPRAISER` | Valuation cases/data only |
| `history_reviewer` | `HistoryDemo123!` | `REVIEWER` | Review cases/data only |

These accounts are for local manual testing only. They are inserted into the
existing `auth.users` and `auth.user_roles` tables and use the project's normal
password hashing. `seed` requires the existing active `APPRAISER` and `REVIEWER`
roles; it never creates or changes roles. `reset` removes only the two users with
the fixed demo UUIDs and their role mappings.

| case_no | case_id | location | scenario |
|---|---|---|---|
| `HIST-VAL-001` | `71000000-0000-4000-8000-000000000001` | 新北市板橋區 (`31/3101`) | Valuation structured SQL data without document metadata |
| `HIST-REV-001` | `71000000-0000-4000-8000-000000000002` | 新北市三重區 (`31/3102`) | Review SQL data and metadata whose MinIO object is deliberately missing |
| `HIST-BOTH-001` | `71000000-0000-4000-8000-000000000003` | 新北市中和區 (`31/3104`) | both-role visibility and a downloadable generated report |

SQL rows use the existing `valuation.cases`, `valuation.parcels`,
`valuation.form_instances`, `valuation.valuations`, `valuation.documents`,
`review.reviews`, and `review.risk_summaries` tables. No schema is created.

The demo and History queries intentionally use the Review columns shared by the
base and expanded schemas. On a base schema, `started_at` is exposed as
`received_at`, and current risk is read from the latest
`review.risk_summaries.overall_risk_level` row.

The downloadable MinIO object key is:

```text
cases/71000000-0000-4000-8000-000000000003/generated/77000000-0000-4000-8000-000000000001/v1/history-demo-report.pdf
```

The deliberately missing object metadata points to:

```text
cases/71000000-0000-4000-8000-000000000002/generated/77000000-0000-4000-8000-000000000002/v1/history-demo-missing.docx
```

No object is uploaded for the second key. `reset` deletes only these fixed demo
rows and the one uploaded demo PDF; it does not touch non-demo cases.

The machine-readable expected results are kept at
`app/history/test_data/expected_cases.json`. The manual frontend source is at
`app/history/test_ui/index.html` and is available at
`/api/v1/history/test-ui` in the development environment.

## Standalone manual frontend

The integrated API exposes the same manual frontend at
`/api/v1/history/test-ui`. To run an isolated test app from Windows Command
Prompt instead, use:

```bat
docker compose --env-file .env run --rm -v "%CD%:/app" -p 8001:8000 api uvicorn app.history.test_app:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8001/api/v1/history/test-ui`. The page can call the
existing Auth login endpoint, retain the returned JWT in page memory, search
History, inspect structured JSON, and test downloads. Stop it with `Ctrl+C`.
