# Task 5 Report: Block Completeness on Missing or Unverified Trusted Inputs

## Scope

- Modified `app/review/completeness.py`
- Modified `app/review/service.py`
- Created `app/review/tests/test_completeness_api.py`

## RED

After adding the three API cases and rebuilding the API image, ran:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_completeness_api.py -q
```

Result: `2 failed, 1 passed`.

- A base-complete case without a completed extraction was incorrectly returned as
  `READY_FOR_REVIEW`.
- A base-complete case with `AUTO_EXTRACTED` high-impact `adjustment_rate` was
  incorrectly returned as `READY_FOR_REVIEW`.

## Implementation

- Added an explicit `trusted_problem_to_missing()` converter.
- Kept document/base-field completeness as the first gate.
- Once the base gate passes, the service resolves only server-owned data:
  active original document, exact-version completed extraction, official fields,
  case/form context, applicable published rule version, active applicable rules,
  and their required target-field codes.
- Missing context or extraction produces `TRUSTED_INPUT_MISSING`; field policy
  problems are converted to stable missing-item codes such as
  `TRUSTED_INPUT_UNVERIFIED_ADJUSTMENT_RATE`.
- The trusted missing items are merged before missing-item synchronization and
  the state transition. No validation run is created by this flow.

## GREEN

After rebuilding and recreating the API container, ran:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_completeness.py app/review/tests/test_completeness_api.py -q
```

Result: `6 passed, 1 warning`.

The warning is the pre-existing Starlette TestClient/httpx deprecation warning.

## Self-review

```powershell
rtk git diff --check
```

Result: clean.

## Concern for follow-up

`app/review/tests/test_missing_items_api.py::test_recheck_resolves_open_items_without_deleting_history`
currently seeds only the legacy document/base-field data and expects readiness.
With the new trusted-input gate it correctly remains pending; the isolated run
was `1 failed, 2 passed`. This task's allowed file list excludes that test, so
it was not changed. Update its fixture/assertion in a later integration task to
seed completed extraction, official fields, published source, applicable rule
version, and active rules.

## Commit

`f68ccf9 feat(review): require verified formal inputs`

## Review correction: usable rule source required

Code review found that completeness selected a rule version without retaining
its `source_document_id`, so draft or unextracted legal sources could be
silently accepted.

### RED

Added independent API cases for a verified, otherwise complete case whose
selected rule source is either:

- `publication_status = 'DRAFT'` and `extraction_status = 'COMPLETED'`; or
- `publication_status = 'PUBLISHED'` and `extraction_status = 'PENDING'`.

After rebuilding the API image, ran:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_completeness_api.py -q
```

Result: `2 failed, 3 passed`. Both new cases were incorrectly returned as
`READY_FOR_REVIEW`.

### Fix

The service now retains the selected candidate row by rule-version ID. It
fails closed with `TRUSTED_INPUT_MISSING` when the selected rule version has no
source document ID or `get_rule_source()` rejects the source because it is not
both published and extraction-complete.

### GREEN

After rebuilding and recreating the API container, ran:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_completeness.py app/review/tests/test_completeness_api.py -q
```

Result: `8 passed, 1 warning`.

The verified-source readiness case still passes. The warning remains the
pre-existing Starlette TestClient/httpx deprecation warning.
Both unusable-source API tests also query `valuation.validation_runs` and
assert that the count remains zero.

### Commit

`e03ae88 fix(review): require usable rule source`
