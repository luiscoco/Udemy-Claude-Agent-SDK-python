# M14 · Decide a release from regression suites

**Goal:** Turn single runs into a small, repeatable regression suite with a release decision.

## Implement

`release_decision(baseline, candidate, explanations)`: a regression is success to anything else, or passed True to False. Return regressions, missing cases, unexplained regressions and `ready`, true only when nothing is missing and every regression is explained. Set `STAGE = 7`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. **Run prepared suite** twice with different names (for example after changing reviews).
2. Choose a baseline and a candidate, then **Decide release**.
3. Add a one-line explanation per regression (`case-id: reason`) and decide again.

## Expected result

You can write a short release decision that cites specific runs, without calling a prepared suite a live validation.

## Check

```shell
uv run agent-lab studio check
```

## Hints

1. Prepared suites are free and deterministic; live checks stay separate, one consented run at a time.
2. An explanation does not make a regression go away; it makes the decision accountable.

## Quiz

- **A baseline case is missing from the candidate. Ready?**
  No: missing cases block the release.
- **Can a suite make hidden paid calls?**
  No: suites run prepared fixtures only.

Related lesson: [lesson 52](http://127.0.0.1:8080/?lesson=52).
