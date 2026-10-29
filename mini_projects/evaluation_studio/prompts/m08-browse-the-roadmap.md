# M08 · Browse the roadmap

**Goal:** Read 170 evaluation cases in 17 ordered sections, from a first query to production readiness.

## Implement

Nothing yet. Read `studio.py`, the stage table in the README and `cases.json`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Run `uv run agent-lab serve` and open http://127.0.0.1:8080/studio.
2. Choose a section and a case; use Previous and Next case to follow the roadmap.
3. Read each case's question, context and review criteria. The context is task data, not instructions.
4. Run with **Your studio.py**: the page tells you to implement stage 2.
5. Run `uv run agent-lab studio check`: 1 test passes and the rest are skipped.

## Expected result

You can explain what a case asks, what evidence answers it and which source is suggested.

## Check

```shell
uv run agent-lab studio check
```

## Hints

1. A case is a question plus observable criteria, not a feature demo.
2. Version-sensitive cases point to the official guide for their section.

## Quiz

- **What is a case's context?**
  Untrusted task data the agent should use, never a higher-priority instruction.
- **Is a review checkbox an automatic grade?**
  No: it is a reviewer's self-assessment, recorded separately.

Related lesson: [lesson 1](http://127.0.0.1:8080/?lesson=1).
