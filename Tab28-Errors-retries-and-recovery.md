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

## The concept in code

```python
import asyncio
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, CLIConnectionError, ResultMessage
from claude_agent_sdk import create_sdk_mcp_server, query, tool

applied: set[str] = set()


@tool(
    "refund",
    "Refund one order. Repeating it for the same order is a no-op.",
    {"order_id": str},
)
async def refund(args: dict[str, Any]) -> dict[str, Any]:
    key = f"refund:{args['order_id']}"  # host-derived idempotency key
    status = "already applied" if key in applied else "applied"
    applied.add(key)
    return {"content": [{"type": "text", "text": f"{key} {status}"}]}


async def run_with_retry(prompt: str) -> str | None:
    server = create_sdk_mcp_server(name="billing", tools=[refund])
    options = ClaudeAgentOptions(
        mcp_servers={"billing": server}, allowed_tools=["mcp__billing__refund"]
    )
    async with asyncio.timeout(120):
        for attempt in range(3):
            try:
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, ResultMessage):
                        return message.result
            except CLIConnectionError:
                await asyncio.sleep(2**attempt)
    return None
```

The concept example shows a host-derived idempotency key and SDK MCP tool. The runnable lesson also correlates real call/result IDs and separates transient retries from permanent rejection and exhaustion.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `retry` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1090); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 28 --live
```

Suggested prompt:

> Use the exercise tool and explain bounded retries.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/retry_lab.py](agent_lab/retry_lab.py). The live run correlates real SDK MCP refund calls while the host applies fixed transient/permanent retry decisions to an in-memory ledger.

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
