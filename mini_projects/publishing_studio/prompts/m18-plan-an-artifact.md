# M18 · Plan a document or infographic

**Goal:** Turn one selected answer into a validated document or infographic plan.

## Implement

`split_fences`, `prepared_plan`, `validate_plan` and `reconcile_code`: parse fenced code before prose, build a free plan, validate every field strictly (no extra keys, bounded lengths, rectangular tables) and keep only code that appears in the trusted answer. Set `STAGE = 4`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Select an answer and read **Source** under Build: it names the answer id and hash.
2. Choose another answer: the source id changes and the old preview disappears.
3. Optional: **Live plan** asks Claude for a structured plan; it needs its own consent and budget.

## Expected result

Plans come from the server's copy of the answer, never from text the browser sends, and invalid plans save nothing.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. Live planning is a second paid call: it never reuses the answer's consent.
2. Restore omitted code and discard invented code; the selected answer is the trusted source.

## Quiz

- **The planner flattened a code block's indentation. What do you keep?**
  The answer's exact snippet, matched ignoring whitespace.
- **A plan contains an unknown block type. Build anyway?**
  No: reject the plan and save no artifact.

Related lesson: [lesson 21](http://127.0.0.1:8080/?lesson=21).
