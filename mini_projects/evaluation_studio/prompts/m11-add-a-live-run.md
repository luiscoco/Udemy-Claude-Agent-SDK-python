# M11 · Add one bounded live run

**Goal:** Add one explicitly authorized live SDK run from the server, distinct from prepared evidence.

## Implement

`parse_run_options(depth, max_turns, max_budget_usd, specialist_review, question)`: accept only the offered depths, turns (1, 3, 5, 8, 12) and budgets (0.05, 0.15, 0.3, 0.5), never booleans as numbers. A specialist needs 5+ turns and 0.15 USD. Trim the question (max 2000). Set `STAGE = 4`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Optional: set `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true` in `.env`, restart, choose **Live SDK run**.
2. Pick bounds, tick the consent box and run once. The badge says LIVE SDK RUN with cost and turns.
3. Try 1 turn on a case that needs tools and read the `error_max_turns` result honestly.

## Expected result

Live runs need fresh consent each time and stay labelled apart from prepared fixtures.

## Check

```shell
uv run agent-lab studio check
```

## Hints

1. The budget is a threshold that stops the run, not an exact billing cap.
2. Never start a bigger run automatically after a limit; suggest it and let the student choose.

## Quiz

- **Can a student pass max_turns=True?**
  No: booleans are rejected even though True == 1 in Python.
- **Where is the API key?**
  Only on the server; the page and studio.py never see it.

Related lesson: [lesson 15](http://127.0.0.1:8080/?lesson=15).
