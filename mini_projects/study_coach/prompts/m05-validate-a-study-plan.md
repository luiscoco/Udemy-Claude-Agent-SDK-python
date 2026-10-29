# M05 · Validate a structured study plan

**Goal:** Accept exactly the requested days within the daily time limit.

## Implement

`validate_plan(plan, days, minutes)` returns a list of readable errors (empty when valid). Limits: days 1-7, minutes 5-120, whole numbers. The plan (dict, or JSON text from the model) is `{"days": [...]}` with exactly `days` rows of `{"day", "topic", "minutes"}`: days count 1, 2, 3..., topics have 1-200 characters, minutes are whole numbers from 1 to the limit. Reject extra fields, malformed rows and non-JSON. Set `STAGE = 5`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Create study plan: ACCEPTED.
2. Try invalid prepared plan: REJECTED with a day-specific error, and the rejected output stays visible.
3. Optional live: Ask Claude for a plan; the same validator judges it.

## Expected result

The valid example is accepted; the over-budget example is rejected with a day-specific error.

## Check

```shell
uv run agent-lab coach check
```

## Hints

1. JSON syntax alone does not establish the plan contract: check shape, count, order and limits.
2. Use one validator for prepared and live plans so both meet the same rules.

## Quiz

- **The model returns valid JSON with 4 days for a 3-day request. Valid?**
  No: the day count must match exactly.
- **Why return a list of errors instead of raising on the first?**
  The student sees every problem at once and can fix the plan in one pass.

Related lesson: [lesson 10](http://127.0.0.1:8080/?lesson=10).
