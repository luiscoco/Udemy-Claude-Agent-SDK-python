# Lesson 63: A safe database agent

Use parameterized SQLite reads and validate versioned write proposals before approval.

This lesson is part of **Permissions and security**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 63
uv run python -m agent_lab.lessons.lesson_63
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 63](http://127.0.0.1:8080/?lesson=63).

## The concept in code

```python
import json
import sqlite3
from contextlib import closing
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, tool


def build_options(db_path: str, tenant: str) -> ClaudeAgentOptions:
    @tool(
        "list_orders", "List the signed-in customer's orders. Takes no arguments.", {}
    )
    async def list_orders(args: dict[str, Any]) -> dict[str, Any]:
        with closing(sqlite3.connect(db_path)) as db:
            rows = db.execute(
                "SELECT id, status, version FROM orders WHERE tenant = ? LIMIT 10",
                (tenant,),
            ).fetchall()
        return {"content": [{"type": "text", "text": json.dumps(rows)}]}

    server = create_sdk_mcp_server(name="db", tools=[list_orders])
    return ClaudeAgentOptions(
        tools=[], mcp_servers={"db": server}, allowed_tools=["mcp__db__list_orders"]
    )


def cancel_order(
    db_path: str, tenant: str, order_id: str, version: int, approved: bool
) -> bool:
    """A write the model can only propose; the host runs it after human approval."""
    if not approved:
        raise PermissionError("Host approval required.")
    with closing(sqlite3.connect(db_path)) as db, db:
        cursor = db.execute(
            "UPDATE orders SET status = 'cancelled', version = version + 1"
            " WHERE tenant = ? AND id = ? AND version = ? AND status = 'pending'",
            (tenant, order_id, version),
        )
    return cursor.rowcount == 1
```

`list_orders` has an empty `{}` schema and runs a `?`-parameterized query for the host's tenant, while `cancel_order` writes only with `approved=True` and a matching `version`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `database` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1474); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 63 --live
```

Suggested prompt:

> List pending orders using the database tool.

The live profile is `database`. Its tools and configuration are in
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
| `GET /api/lessons/63` | Lesson metadata |
| `POST /api/lessons/63/run` | Collected JSON events |
| `POST /api/lessons/63/stream` | Server-Sent Events |
| `/api/lessons/63/ws` | WebSocket events and cancellation |

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
