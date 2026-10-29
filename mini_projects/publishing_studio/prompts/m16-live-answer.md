# M16 · Add a consented live answer

**Goal:** Validate every request and add an explicitly authorized live SDK answer.

## Implement

`parse_answer_request(prompt, model, mode, budget_usd, consent)` accepts only MODELS keys, prepared or live, and the BUDGETS (0.20, 0.50, 1.00, 2.00 USD; no booleans); live needs consent exactly True. `summarize_answer(messages)` collects top-level text, counts MCP tool calls and marks the answer complete only for a clean `success` result. Set `STAGE = 2`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Optional: set `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true` in `.env` and restart.
2. Choose **Live SDK answer**, a model and a spending cap. Changing the cap clears the consent box.
3. Tick consent and send once: the badge says LIVE SDK ANSWER with turns and reported cost.
4. Try sending without consent: it is refused before any SDK call.

## Expected result

A live answer that hits its budget or turn limit is explained and never saved as a completed answer.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. The browser sends a model *key*; the server never accepts an arbitrary model string.
2. Consent covers one call; the box clears after every attempt.

## Quiz

- **The result subtype is error_max_budget_usd but text arrived. Save it?**
  No: it is incomplete; explain the limit instead.
- **Can the budget be True?**
  No: booleans are rejected even though True == 1 in Python.

Related lesson: [lesson 15](http://127.0.0.1:8080/?lesson=15).
