# Task 6 Report: Server-owned trusted run execution

## RED

- Replaced the run and rerun API tests with an original-document, completed-extraction,
  official-field, selected-rule and published-source fixture.
- Rebuilt the API container and ran the focused tests before implementation.
- Result: `15 failed, 11 passed`; valid `{}` requests were rejected by the former
  required `RunCreate` fields, while the former caller-supplied payload still drove
  the old execution path.

## GREEN

- `RunCreate` is now an empty command with `extra="forbid"`.
- `TrustedRunContext` holds server-selected document, extraction, fields, rule version,
  active rules and source.
- The service resolves document, extraction, fields, case/form context, selected rule,
  usable source, active rules and required fields before changing review state or
  creating a run.
- The repository creates runs from server-selected rule IDs and server-built snapshots.
- Findings and legal basis derive from trusted field rows and the selected rule source;
  only `ADJUSTMENT_RATE` and `EXPERT_GRADE` execute.
- Reruns keep the same server-owned command boundary.

## Verification

```text
rtk docker compose --env-file .env.example exec -T api pytest \
  app/review/tests/test_completeness_api.py \
  app/review/tests/test_runs_api.py \
  app/review/tests/test_rerun.py -q

31 passed, 1 warning in 2.57s
```

The sole warning is the existing Starlette `TestClient` / httpx deprecation warning.
`rtk git diff --check` completed without output.

## Follow-up

`test_workflow_e2e.py` still contains the former caller-payload helper and is outside
Task 6's permitted test-file scope. Update it in the planned E2E task before running
the full suite.

## Review security follow-up

- Added one shared, mutation-free trusted-rule preflight used by both completeness
  and run execution. It validates supported rule code, non-null expected target field,
  field value type, JSON-object configuration, finite adjustment decimals and typed
  expert grades before a run can be created.
- Added API coverage for null/bool/list/non-finite and mismatched typed values, null
  targets, invalid configuration objects and values, and all former request-owned
  fields. Every run-preflight failure asserts no new run and unchanged review state.
- Completeness now turns the same errors into stable missing items, so it cannot mark
  an invalid configuration or trusted normalized value as `READY_FOR_REVIEW`.
- Verification after the review follow-up:

```text
50 passed, 1 existing Starlette TestClient/httpx deprecation warning
```

- Requested legacy check: `app/review/tests/test_missing_items_api.py` produced
  `2 passed, 1 failed`. Its recheck fixture adds only general documents/parcels and
  no trusted extraction/rule/source context, so it is correctly no longer ready under
  the current fail-closed boundary. Update that legacy fixture in Task 7 or Task 8.

## Review security follow-up r2

### RED

- The new focused cases initially produced `6 failed, 51 passed`: a reported extreme
  finite decimal was still quantized during execution, extreme system/tolerance
  values and negative tolerance were accepted, and missing fields incorrectly won
  over an invalid rule contract.
- A controlled second `create_finding` failure already rolled back through the API
  transaction, proving the test can assert persistence rollback rather than only a
  preflight rejection.

### GREEN

- Added a shared, mutation-free rule-contract pass before field availability in both
  completeness and run resolution. It rejects null, unsupported, or wrong targets and
  invalid rule configuration with `RULE_CONFIGURATION_INVALID`, even when the target
  field is absent.
- Adjustment rules now validate system rate and tolerance with the same
  `recalculate_adjustment_rate`/quantize path used for execution. Tolerance must be
  finite and non-negative. Trusted reported rates are also precomputed into an
  immutable `AdjustmentResult`; execution only consumes that result.
- Focused cases cover extreme finite reported/system/tolerance decimals, negative
  tolerance, unsupported/wrong/null targets with missing fields, and completeness
  fail-closed behavior.
- The persistence-failure test monkeypatches the second `create_finding` call to
  raise a controlled `AppError`, then asserts zero persisted validation runs,
  findings, and risk summaries, plus the review status restored to `READY_FOR_REVIEW`.

### Verification

```text
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest \
  app/review/tests/test_completeness_api.py \
  app/review/tests/test_runs_api.py \
  app/review/tests/test_rerun.py -q

57 passed, 1 existing Starlette TestClient/httpx deprecation warning
```
