# Task 4 Report: Load a Server-Owned Run Context

## Scope

- Modified: `app/review/repository.py`
- Added: `app/review/tests/test_trusted_repository.py`

## TDD evidence

### RED

After rebuilding the API container so the new test file was present:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_repository.py -q
```

Result: `1 failed in 0.36s` with
`AttributeError: 'ReviewRepository' object has no attribute 'get_latest_original_document'`.

Two fixture-only setup issues were corrected before this meaningful RED result:

- The current database requires knowledge documents in bucket `land-valuation`.
- Their object keys must start with `knowledge/`.

These reflect the existing migration `0002` storage contract; no production storage code was changed.

### GREEN

```powershell
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_repository.py -q
```

Result: `1 passed in 0.43s`.

## Implementation

- Added parameter-bound queries for the latest active original document, exact
  completed extraction, official extracted fields, case rule context, rule
  candidates, applicable active rules, and usable rule source documents.
- The test seeds two active original-document versions, an unrelated completed
  extraction, official fields, F01/F02 form states, published/draft rules, and
  published/unpublished source documents.

## Commit

`a9bb46f feat(review): load trusted run context`

## Concerns

- `list_rule_candidates()` intentionally returns version metadata without
  deciding applicability; the service layer applies the case/date/form policy
  and handles selection conflicts in subsequent tasks.

## Reviewer-requested predicate coverage follow-up

The original focused test was run before adding coverage and remained green:

```powershell
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_repository.py -q
```

Result: `1 passed in 0.36s`. This was a coverage-only change, so there was no
meaningful RED state against the existing correct repository implementation.

The fixture now also asserts these predicates with competing rows:

- an inactive original document at version 99 does not supersede active version 2;
- a completed extraction with the selected document ID but a different version,
  plus a higher-run pending extraction at the exact version, are not selected;
- a non-official extracted field is omitted;
- `COMPLETED + DRAFT` and `PENDING + PUBLISHED` rule sources are both unavailable;
- candidate status and effective date metadata are returned.

After rebuilding and recreating the API container:

```powershell
rtk docker compose --env-file .env.example build api
rtk docker compose --env-file .env.example up -d --no-deps --force-recreate api
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_repository.py -q
```

Result: `1 passed in 0.39s`.

Follow-up commit: `ee23216 test(review): cover trusted repository predicates`
