# Lesson 28: Errors, retries and recovery

Retry transient operations within a deadline and avoid blindly repeating writes.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 28
uv run python -m agent_lab.lessons.lesson_28
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 28](http://127.0.0.1:8080/?lesson=28).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `retry`, line 613). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("retry")
async def retry(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Retry transient failures with backoff inside a deadline, without repeating a write."""
    applied: dict[str, str] = {}  # idempotency key -> result: the host's write ledger
    attempts: list[dict[str, Any]] = []

    async def write_refund(key: str, attempt: int) -> str:
        if key not in applied:
            applied[key] = "refund A-100 for 500 cents"
        if attempt == 1:
            # The write succeeded, but its response was lost: the classic ambiguous failure.
            raise ConnectionError("Connection reset after the request was sent")
        if attempt == 2:
            raise TimeoutError("Upstream timed out")
        return applied[key]

    key = "refund-A-100-500"
    delays = [0.01, 0.02]
    result = None
    try:
        async with asyncio.timeout(2):
            for attempt in range(1, 4):
                try:
                    result = await write_refund(key, attempt)
                    attempts.append({"attempt": attempt, "outcome": "succeeded"})
                    break
                except (ConnectionError, TimeoutError) as exc:
                    attempts.append({"attempt": attempt, "outcome": type(exc).__name__})
                    if attempt == 3:
                        raise
                    await asyncio.sleep(delays[attempt - 1])
    except TimeoutError as exc:
        raise LessonError("The retry deadline expired before the write was confirmed.") from exc
    return {
        "deadline_seconds": 2,
        "backoff_seconds": delays,
        "attempts": attempts,
        "result": result,
        "idempotency_key": key,
        "writes_applied": len(applied),
        "duplicate_write_prevented": len(applied) == 1 and len(attempts) > 1,
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 28 --live
```

Suggested prompt:

> Use the exercise tool and explain bounded retries.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/28` | Lesson metadata |
| `POST /api/lessons/28/run` | Collected JSON events |
| `POST /api/lessons/28/stream` | Server-Sent Events |
| `/api/lessons/28/ws` | WebSocket events and cancellation |

Pydantic validates the request before the run starts:

```json
{"mode": "offline", "prompt": "", "max_turns": 4, "max_budget_usd": 0.10}
```

All transports use [RunService](agent_lab/runtime.py). It bounds concurrency,
owns the producer task and closes the SDK connection in the task that opened
it. A run emits one terminal `done` event. Cancellation awaits cleanup before
releasing the run slot.

## Practice

1. Identify trusted host inputs and untrusted model or source data.
2. Change one bounded input and predict whether validation accepts it.
3. Add a failure case and explain how the host should report it.
4. Compare offline evidence with a live run without mistaking fixtures for model output.

## Verification and references

`uv run pytest` executes every offline lesson and checks host policies, tenant
isolation, approvals, dependency failures, cancellation and API validation.
Paid calls are separate, opt-in checks.

- [Official Python Agent SDK reference](https://code.claude.com/docs/en/agent-sdk/python)
- [Python SDK source](https://github.com/anthropics/claude-agent-sdk-python)
- [Setup and migration coverage](README.md)
