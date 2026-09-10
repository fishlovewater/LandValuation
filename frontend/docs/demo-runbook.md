# Persistent four-subsystem Demo runbook

This runbook covers the persistent browser journey across Valuation, Assistant,
Review, and History. Mocked Playwright responses, fixture-only records, and an
API that was not started are not acceptance evidence.

Never paste generated passwords, bearer tokens, MinIO object keys, presigned
URLs, or full question payloads into this file, screenshots, or a report.

## Scope and gates

The shared development lifecycle is `app.demo`. It creates one F03 case, the
three Demo users, the persistent Assistant source, and the pre-submission
evidence chain. It does not submit the case and it does not create a Review.
The real-browser journey now completes the handoff: the APPRAISER clicks the
existing Valuation `submit-for-review` button, waits for the real HTTP 201
response, reads its `review_id`, and passes that ID in test-local state to the
REVIEWER. The seed output never supplies a Review ID.
Swagger is for route inspection only, never the submission step. The REVIEWER
then opens the Review created by that browser submission, and the INSPECTOR
reads the same case in History.

Formal APPRAISER, REVIEWER, and INSPECTOR grants are migration-owned and are
not changed by the lifecycle. The permission check operates on the current
effective permission code (for example `knowledge.read` or `case.read`), not
on a role name. Local `evidence_only` answers cannot close `SUPPORTED`
acceptance: a supported answer needs a traceable citation from the persistent
source. A source-free question must remain a refusal with zero citations.

After submission, `app.demo reset` is fail-closed and leaves submitted data in
place for Task 6 to validate the Compose container names/labels before
teardown. Do not use `down -v` for acceptance cleanup.

## 1. Start an isolated Compose project

Run from the repository root. The override gives every service a unique
`land_valuation_persistent_demo_*` container name and keeps the base named
volumes project-scoped. These commands do not stop or reuse the default
`land_valuation_*` containers.

```powershell
docker compose -p landvaluation-persistent-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.example build migrate api
docker compose -p landvaluation-persistent-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.example up -d db db-role-init migrate minio minio-init api
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18000/health/ready
```

Readiness must report PostgreSQL and MinIO ready before treating the browser
journey as started. Verify the five mounted routes directly from the running
image:

```powershell
docker compose -p landvaluation-persistent-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.example exec -T api python -c "from app.main import app; p=app.openapi()['paths']; assert all(x in p for x in ['/api/v1/valuation/cases/{case_id}/submit-for-review','/api/v1/ai-assistant/sessions','/api/v1/ai-assistant/sessions/{session_id}/questions','/api/v1/review/workbench/cases/{review_id}','/api/v1/history/cases/{case_id}'])"
```

The API key, AWS credentials, Bedrock region/model, Codex credential/model,
and other external-provider secrets remain blank in tracked configuration.
Configure secrets only through the operator-owned local environment when a
provider-backed run is explicitly available.

## 2. Seed and capture credentials without printing them

The normal command is the shared lifecycle entry point:

```powershell
docker compose -p landvaluation-persistent-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.example exec -T api python -m app.demo seed
docker compose -p landvaluation-persistent-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.example exec -T api python -m app.demo status
```

For a shell-local run, discard seed output and parse only the safe `status` JSON
for the case identifiers. The fixed local Demo credentials are
`valuation_demo` / `Demo1234!`, `review_demo` / `Demo1234!`, and
`inspector_demo` / `Demo1234!`; they are forbidden in staging, production, and
AWS:

```powershell
$compose = @('-p', 'landvaluation-persistent-demo', '-f', 'docker-compose.yml', '-f', 'docker-compose.demo.yml', '--env-file', '.env.example')
docker compose @compose exec -T api python -m app.demo seed | Out-Null
$status = docker compose @compose exec -T api python -m app.demo status | ConvertFrom-Json
$env:E2E_APPRAISER_USERNAME = 'valuation_demo'
$env:E2E_APPRAISER_PASSWORD = 'Demo1234!'
$env:E2E_REVIEWER_USERNAME = 'review_demo'
$env:E2E_REVIEWER_PASSWORD = 'Demo1234!'
$env:E2E_INSPECTOR_USERNAME = 'inspector_demo'
$env:E2E_INSPECTOR_PASSWORD = 'Demo1234!'
$env:E2E_CASE_ID = [string]$status.case.case_id
$env:E2E_CASE_NO = 'DEMO-F03-PERSISTENT-001'
$env:E2E_F03_FORM_ID = [string]$status.case.form_id
Remove-Variable status
```

The `status` result is safe to record because it contains readiness and counts,
not passwords, tokens, bucket names, object keys, or presigned URLs.

Seed intentionally has no `review_id`. The browser obtains the ID dynamically
from the real HTTP 201 submission response; do not preseed a Review ID in the
browser environment.

The legacy-compatible command is still available for scripts that already use
the Review module. It is a narrow adapter to the same persistent lifecycle;
it does not contain a second seed or cross-subsystem SQL path:

```powershell
docker compose -p landvaluation-persistent-demo -f docker-compose.yml -f docker-compose.demo.yml --env-file .env.example exec -T api python -m app.review.demo handoff-seed
```

## 3. Permission-code check

After the Assistant session is created by the browser, use only the approved
development command and an effective permission code. Run the browser command
from `frontend/`; its fixed project directory, Compose files, env-file, and
`api` service keep the operator inside the isolated persistent Demo stack. The
test supplies only the action and code through its controlled environment
variables. Revoke and restore the same code around the next question on the
same session; do not redeploy the frontend between requests.

```text
docker compose --project-directory .. -p landvaluation-persistent-demo -f ../docker-compose.yml -f ../docker-compose.demo.yml --env-file ../.env.example exec -T api python -m app.demo permission %E2E_PERMISSION_ACTION% %E2E_PERMISSION_CODE%
```

Set `E2E_PERMISSION_OPERATOR_COMMAND` to exactly that wrapper and keep
`E2E_PERMISSION_GATE_ENABLED=false` until it can run in the same development
API environment. On shells that do not use `%NAME%` expansion, use that
shell's equivalent references to the same two variables; do not put a literal
action, role name, SQL expression, session ID, or secret in the command. The
frontend contract rejects any extra shell suffix or changed project/file
argument.

```powershell
cd frontend
$env:E2E_PERMISSION_ACTION = 'revoke'
$env:E2E_PERMISSION_CODE = 'knowledge.read'
docker compose --project-directory .. -p landvaluation-persistent-demo -f ../docker-compose.yml -f ../docker-compose.demo.yml --env-file ../.env.example exec -T api python -m app.demo permission $env:E2E_PERMISSION_ACTION $env:E2E_PERMISSION_CODE
$env:E2E_PERMISSION_ACTION = 'restore'
docker compose --project-directory .. -p landvaluation-persistent-demo -f ../docker-compose.yml -f ../docker-compose.demo.yml --env-file ../.env.example exec -T api python -m app.demo permission $env:E2E_PERMISSION_ACTION $env:E2E_PERMISSION_CODE
```

The command must be run only for the owned development APPRAISER and returns a
non-zero result for an unsupported code or an ineffective revoke. It never
modifies the formal production role grants.

## 4. Browser order and acceptance evidence

The real browser spec uses the persistent API and must not register
`page.route` handlers:

1. APPRAISER opens the seeded F03 case, completes the server-backed Valuation
   flow, asks the Assistant questions, and clicks the existing Valuation
   `submit-for-review` button. Wait for the real POST whose pathname ends with
   `/valuation/cases/{case_id}/submit-for-review`, require HTTP 201, parse a
   non-empty `review_id`, and retain it in test-local state. Do not use a
   preseeded Review ID, direct SQL, `page.request`, or Swagger to bypass this
   browser boundary.
2. REVIEWER receives that dynamically captured `review_id`, opens the created
   Review, verifies the same server `case_id`/`case_no`, processes the server
   findings, and completes the review.
3. INSPECTOR searches the same case number in History and opens the row keyed
   by the same server case ID.

The persistent spec reads the variables exported above:

```powershell
cd frontend
$env:VITE_API_BASE_URL = "/api/v1"
npm.cmd run dev -- --host 127.0.0.1
```

During local development only, Vite forwards `/api/*` to
`http://127.0.0.1:18000`. AWS deployment can override `VITE_API_BASE_URL` with
the deployed API URL.

The browser must show server-produced case/calculation/validation state, the
real submission response and dynamic Review handoff, a completed Review, and
the same case identity in History. Assistant outcomes depend on the provider
boundary:

- Local `KNOWLEDGE_ANSWER_PROVIDER=evidence_only`: report Knowledge candidate
  evidence separately when present, but require the Assistant safe refusal
  (`EVIDENCE_ONLY` for a matched candidate or `NO_RELEVANT_SOURCE` for no
  source) with zero Assistant citations. This run is never `SUPPORTED`.
- AWS/provider-backed: only when a real provider is configured by the operator
  outside tracked configuration, require the supported question to return
  `SUPPORTED` with a citation from the current source. The source-free question
  must still be a safe refusal with zero citations.

Any skipped, mocked, fixture-only, or static result is not acceptance evidence.

## 5a. Login diagnostics artifact handoff and cleanup

Playwright tracing is disabled because a browser trace can contain the seeded
username/password in DOM snapshots or network details. A login failure may
produce only the attached, sanitized JSON boundary report; it must never read
or include request bodies, response bodies, authorization headers, tokens,
storage URLs, or object keys.

Before removing any local Playwright artifacts, verify that the sanitized JSON
has completed its durable handoff to the Task 6 report or other approved
evidence location and that the handoff can be reopened. The directories may be
removed only after the durable handoff is verified, and only as the exact,
resolved worktree directories `frontend/test-results/` and
`frontend/playwright-report/`. Check
that each resolved path is inside this worktree and is exactly one of those
two artifact directories; do not remove any parent, sibling, source, or
unrelated temporary directory. The frontend `.gitignore` rules are a second
boundary so an unfinished artifact cannot be added to a source commit.

## 6. Task 6 post-submission reset and teardown safety

This is the Task 6 post-submission procedure; Task 5 does not claim that the
submitted case has been cleaned up. Use these lifecycle commands only for the
owned development project. First capture status, call public `reset`, and
require a non-zero `DEMO_RESET_REVIEW_STATE` response. Compare the complete
status JSON before and after; any difference is a zero-side-effect failure:

```powershell
$compose = @('-p', 'landvaluation-persistent-demo', '-f', 'docker-compose.yml', '-f', 'docker-compose.demo.yml', '--env-file', '.env.example')
$before = (docker compose @compose exec -T api python -m app.demo status | ConvertFrom-Json | ConvertTo-Json -Compress)
$resetOutput = docker compose @compose exec -T api python -m app.demo reset 2>&1 | Out-String
if ($LASTEXITCODE -eq 0 -or $resetOutput -notmatch 'DEMO_RESET_REVIEW_STATE') { throw 'reset must fail closed after submission' }
$after = (docker compose @compose exec -T api python -m app.demo status | ConvertFrom-Json | ConvertTo-Json -Compress)
if ($before -ne $after) { throw 'DEMO_RESET_REVIEW_STATE changed Demo state' }
```

Next, re-check the exact project, container, and volume labels. Proceed only if
every listed container has project label `landvaluation-persistent-demo` and a
name matching `land_valuation_persistent_demo_*`, and every listed volume has
the same project label and the expected project-scoped name:

```powershell
$project = 'landvaluation-persistent-demo'
$containers = @(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Names}}')
$volumes = @(docker volume ls --filter "label=com.docker.compose.project=$project" --format '{{.Name}}')
$expectedContainers = @('land_valuation_persistent_demo_api', 'land_valuation_persistent_demo_db', 'land_valuation_persistent_demo_db_role_init', 'land_valuation_persistent_demo_migrate', 'land_valuation_persistent_demo_minio', 'land_valuation_persistent_demo_minio_init')
$expectedVolumes = @("${project}_postgres_data", "${project}_minio_data")
$containerInfo = @(docker inspect $containers | ConvertFrom-Json)
$volumeInfo = @(docker volume inspect $volumes | ConvertFrom-Json)
if ((Compare-Object ($containers | Sort-Object) ($expectedContainers | Sort-Object)) -or $containerInfo.Count -ne $expectedContainers.Count) { throw 'unexpected Demo container set' }
if ((Compare-Object ($volumes | Sort-Object) ($expectedVolumes | Sort-Object)) -or $volumeInfo.Count -ne $expectedVolumes.Count) { throw 'unexpected Demo volume set' }
if ($containerInfo | Where-Object { $_.Name.TrimStart('/') -notmatch '^land_valuation_persistent_demo_' -or $_.Config.Labels.'com.docker.compose.project' -ne $project }) { throw 'unexpected Demo container label' }
if ($volumeInfo | Where-Object { $_.Name -notmatch '^landvaluation-persistent-demo_' -or $_.Labels.'com.docker.compose.project' -ne $project }) { throw 'unexpected Demo volume label' }
```

Record the default `land_valuation_*` container names and all unrelated volume
names before teardown. After the label checks pass, run only the explicitly
scoped project command below; never run an unscoped `down -v`:

```powershell
$defaultContainersBefore = @(docker ps -a --format '{{.Names}}' | Where-Object { $_ -match '^land_valuation_' -and $_ -notmatch '^land_valuation_persistent_demo_' })
$unrelatedVolumesBefore = @(docker volume ls --format '{{.Name}}' | Where-Object { $_ -notmatch '^landvaluation-persistent-demo_' })
docker compose @compose down --volumes
$defaultContainersAfter = @(docker ps -a --format '{{.Names}}' | Where-Object { $_ -match '^land_valuation_' -and $_ -notmatch '^land_valuation_persistent_demo_' })
$unrelatedVolumesAfter = @(docker volume ls --format '{{.Name}}' | Where-Object { $_ -notmatch '^landvaluation-persistent-demo_' })
if ((Compare-Object $defaultContainersBefore $defaultContainersAfter) -or (Compare-Object $unrelatedVolumesBefore $unrelatedVolumesAfter)) { throw 'default or unrelated Docker resources changed' }
```

Do not add an admin delete endpoint or backdoor. The public reset refusal and
the verified project-scoped Compose teardown are the only post-submission
cleanup paths.
