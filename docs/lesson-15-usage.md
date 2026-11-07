# Lesson 15: Cost and usage

Run a usage example, then try a recorded limit stop and the separate session meter. The host separates assistant-message usage, final `ResultMessage.usage`, final per-model `model_usage` and `total_cost_usd`. Assistant blocks with the same message ID are grouped; they are not counted as separate calls. Missing IDs remain unidentified. Intermediate message usage is not substituted for final totals, and absent or invalid counters remain **Unknown**.

The bounded automatic check requires an initialized, matching parent session, successful final result, finite nonnegative cost and input/output token counts, and confirmed connection closure. It does not predict future billing or cache savings. Recorded missing-final, mismatched-identity, missing-usage, invalid-counter, turn-limit, budget-limit and interruption examples intentionally need review. Live checks use actual SDK messages; unsupported settings and authentication errors do not trigger host retries.

Optional turn/dollar limits map to `max_turns` and `max_budget_usd`. The bounded integer `task_budget.total` is planning guidance, not an enforced billing limit. The optional Agent tool uses a restricted helper with no tools. Omitted SDK limits still leave the host deadline in place. Dollar thresholds are not guaranteed final prices. Never infer a successful stop merely because the reported cost resembles a configured threshold.

## Session meter and inspection

The separate **Session meter (completed results)** owns one SDK connection in one task, accepts up to four messages and closes on End, failure, cancellation, page disconnect or ten-minute inactivity. At most four sessions and 32 archived records are retained per app instance. Live opening and each live send require explicit authorization. Opening connects without submitting a prompt. A live context inspection calls the public `get_context_usage`; usage inspection only reads saved observations. Neither submits a user message or completes the automatic exercise check.

For comparable cumulative totals from one session, the meter subtracts the previous total before updating its baseline: recorded 0.010 and 0.025 yield deltas 0.010 and 0.015, not 0.035 in new spend. Unknown values, decreasing totals or unrelated identities break comparability. The meter does not silently bridge missing observations. Offline accounting uses labelled recorded SDK payloads, including recorded monetary values; those values are teaching fixtures, not incurred charges or estimated live prices. The meter updates after terminal results, not on individual streamed blocks.

`POST /api/c15/run` shares the normal lesson runner. `POST /api/c15/session` opens the separate session. `/send`, `/context`, `/usage` and `/end` require its application handle and control token. `/send` accepts a nonempty bounded prompt and fresh live consent. Strict inputs reject foreign fields, nonfinite numbers and invalid planning budgets before model work. A busy session rejects overlapping commands. Inspection and mutation remain separate.

```shell
uv run agent-lab lesson 15
uv run agent-lab lesson 15 --scenario budget-limit
uv run agent-lab lesson 15 --lesson-options-file usage-options.json
```

For the options file, `{"task_tokens":2048,"allow_agent":false}` supplies planning guidance while retaining the default turn and dollar thresholds. Negative scenarios are offline only.

Seven explained questions, two hints, a worked explanation, saved attempts, distinct concept/lab briefs and three exact source excerpts accompany the seven-section Learning Guide. The concept code keeps a host ledger example but rejects unknown actual cost instead of recording zero. The original simple budget exercise remains available as a separate source reference; it is not substituted for live final usage.

This adapts the pinned [lesson 15 teaching contract](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/blob/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts/l15-lesson-15-cost-usage.md). Tests use injected live streams and recorded offline producers. Paid-account acceptance, authored media and recorded narration remain separate. Continue with [lesson 16, Settings and environment](lesson-16-settings.md).
