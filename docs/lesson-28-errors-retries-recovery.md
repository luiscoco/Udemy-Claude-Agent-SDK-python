# Lesson 28: Errors, retries and recovery

The lesson uses a fixed in-memory refund for order `A-100` and a host-derived idempotency key. No payment service is contacted. A real SDK MCP tool reports selected outcomes while the host owns the retry loop. The host sends at most three turns on one SDK session, waits 0.01 and 0.02 seconds between transient attempts, and keeps the whole sequence inside a 90-second deadline.

The recovery path first applies the key but returns an ambiguous post-write error, then returns a transient timeout, then confirms the key is already applied. The permanent path rejects on its first attempt without a write. The exhaustion path stops after three transient responses with one ledger effect but no confirmation. Only transient statuses cause another host turn.

The automatic check correlates each actual SDK MCP tool call and result ID with the fixed handler outcome, verifies each successful SDK turn belongs to the initialized session, checks the host decisions and backoff, and requires at most one ledger effect. A successful SDK terminal result alone does not prove the refund state; the handler and ledger supply that evidence. The [official SDK custom-tool implementation](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/__init__.py) maps handler `is_error` to MCP tool results.

Run the offline exercise with `uv run agent-lab lesson 28`. Run the three bounded provider-backed cases with `uv run python scripts/lesson_live_smoke.py 28 --live` after the live environment is configured. Reports are saved under `.lab-data/lesson-live-smoke/`.
