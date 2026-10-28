# Lesson 67: Multi-tenant SaaS architecture

Capture tenant identity in host state and reject cross-tenant access.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 67
uv run python -m agent_lab.lessons.lesson_67
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 67](http://127.0.0.1:8080/?lesson=67).

## The concept in code

```python
import json
import sqlite3
from contextlib import closing
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    create_sdk_mcp_server,
    tool,
)

SESSIONS = {"session-a": "alice", "session-b": "bob"}  # written by the login flow


def options_for(tenant: str, db_path: str) -> ClaudeAgentOptions:
    @tool("list_orders", "List your orders. Takes no arguments.", {})
    async def list_orders(args: dict[str, Any]) -> dict[str, Any]:
        with closing(sqlite3.connect(db_path)) as db:
            rows = db.execute(
                "SELECT id, status FROM orders WHERE tenant = ?", (tenant,)
            ).fetchall()
        return {"content": [{"type": "text", "text": json.dumps(rows)}]}

    server = create_sdk_mcp_server(name="shop", tools=[list_orders])
    return ClaudeAgentOptions(
        tools=[], mcp_servers={"shop": server}, allowed_tools=["mcp__shop__list_orders"]
    )


async def handle(session_id: str, prompt: str) -> None:
    tenant = SESSIONS.get(session_id)
    if tenant is None:
        raise PermissionError("Unauthenticated session.")
    async with ClaudeSDKClient(options=options_for(tenant, "orders.sqlite")) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            print(type(message).__name__)
```

`SESSIONS.get(session_id)` picks the tenant, and `options_for(tenant, ...)` closes over it so `list_orders` has an empty schema and always filters by `tenant = ?`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `tenancy` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1800); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 67 --live
```

Suggested prompt:

> Use the exercise tool to inspect tenant isolation.

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
| `GET /api/lessons/67` | Lesson metadata |
| `POST /api/lessons/67/run` | Collected JSON events |
| `POST /api/lessons/67/stream` | Server-Sent Events |
| `/api/lessons/67/ws` | WebSocket events and cancellation |

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
