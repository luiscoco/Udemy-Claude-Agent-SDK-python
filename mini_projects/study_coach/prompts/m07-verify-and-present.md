# M07 · Verify and present

**Goal:** Collect reproducible evidence for the finished application.

## Implement

No new functions. Set `STAGE = 7`, run `uv run agent-lab coach check`, and complete [docs/evidence-template.md](../docs/evidence-template.md).

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Record a completed answer, a same-conversation follow-up, an accepted and a rejected plan, and a recovered turn.
2. Label local fixture checks, mocked checks and any real live run separately.
3. Note what remains unverified.

## Expected result

All your stage checks pass, and your evidence says exactly what ran and whether a live call occurred.

## Check

```shell
uv run agent-lab coach check
```

## Hints

1. `coach check --reference` checks the reference, not your work; only `coach check` verifies your coach.py.
2. Reference and learner evidence must stay separate.

## Quiz

- **Does a passing reference check prove your stage works?**
  No: it checks reference/coach.py, not your file.
- **What makes evidence reproducible?**
  The exact command, inputs and observed result, so someone else can rerun it.

Related lesson: [lesson 12](http://127.0.0.1:8080/?lesson=12).
