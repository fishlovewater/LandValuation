# Task 3 report: trusted input policy

## RED

After adding the wished-for trust-policy tests and changing existing callers to
pass a form-code set, the rebuilt API container reported:

```text
ModuleNotFoundError: No module named 'app.review.trusted_inputs'
```

This confirmed the tests failed because the policy module was not implemented.

## GREEN

Implemented the pure trusted-input policy and form-set-aware rule selection.
Focused verification command:

```text
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_inputs.py app/review/tests/test_rule_selection.py -q
7 passed in 0.02s
```

## Files

- `app/review/trusted_inputs.py`
- `app/review/rule_selection.py`
- `app/review/tests/test_trusted_inputs.py`
- `app/review/tests/test_rule_selection.py`

## Commit

`9e4a40712b8b449f2834f875ed3ac49d2a5bf3b0`  
`feat(review): define trusted input policy`

## Self-review

- `trusted_fields_by_code()` excludes nonofficial rows.
- Rejected or absent values produce `TRUSTED_INPUT_MISSING`.
- High-impact values require `VERIFIED`; low-impact official `AUTO_EXTRACTED`
  values remain usable.
- Rule candidates match only when `form_code` is null or belongs to the
  supplied `form_codes` set.
- Only the four files listed in the brief were staged and committed; `.sdd`
  remains untracked and was not staged.

## Concerns

- Local Python does not have pytest installed; verification was run in the API
  container as specified by the brief.

## Follow-up fix: fail closed on ambiguous or unknown trust inputs

### RED

After adding regressions for unknown low-impact status, rejected official and
nonofficial precedence, and duplicate official rows in both input orders, the
rebuilt API test run failed with 2 failures and 10 passes:

```text
FAILED test_unknown_low_impact_status_is_unverified
    IndexError: tuple index out of range
FAILED test_duplicate_official_fields_are_missing_in_either_input_order[ordered_fields1]
    IndexError: tuple index out of range
```

The first failure showed unknown statuses were accepted; the second showed
last-input-wins behavior was order-dependent.

### GREEN

The policy now accepts only `AUTO_EXTRACTED` or `VERIFIED` for low-impact
fields, and omits duplicate official field codes from the trusted mapping.
`select_effective_rule()` now annotates `form_codes` as `typing.AbstractSet[str]`
so both sets and frozensets are accepted at runtime.

Focused verification command:

```text
rtk docker compose --env-file .env.example exec -T api pytest app/review/tests/test_trusted_inputs.py app/review/tests/test_rule_selection.py -q
12 passed in 0.03s
```

### Follow-up commit

`fix(review): fail closed on ambiguous trusted fields`

### Follow-up concerns

- Local Python still does not have pytest installed; verification remains in the
  rebuilt API container.
