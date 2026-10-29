# Lesson 50: Full-stack support capstone

Bind a support tool to a host-selected customer and require approval before refunding.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 50
uv run python -m agent_lab.lessons.lesson_50
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 50](http://127.0.0.1:8080/?lesson=50).

## The concept in code

```python
import time
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server, tool


@dataclass
class Approval:
    customer_id: str
    amount: float
    expires_at: float


def support_server(
    customer_id: str, approvals: dict[str, Approval]
) -> McpSdkServerConfig:
    @tool(
        "list_orders", "List the orders of the customer signed in to this session.", {}
    )
    async def list_orders(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Orders for {customer_id}: A1 40.00"}]
        }

    @tool(
        "refund",
        "Refund an order that staff approved.",
        {"order_id": str, "amount": float},
    )
    async def refund(args: dict[str, Any]) -> dict[str, Any]:
        a = approvals.get(args["order_id"])
        if (
            a is None
            or time.time() > a.expires_at
            or (a.customer_id, a.amount) != (customer_id, args["amount"])
        ):
            return {
                "content": [
                    {"type": "text", "text": "No valid approval for this exact refund."}
                ],
                "is_error": True,
            }
        del approvals[args["order_id"]]  # single use: the approval is consumed
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Refunded {a.amount:.2f} on {args['order_id']}.",
                }
            ]
        }

    return create_sdk_mcp_server("support", tools=[list_orders, refund])
```

`support_server` closes over the host's `customer_id`, so `list_orders` takes no customer argument, and refund only runs, and then deletes the approval, when an unexpired Approval for that order matches the customer and amount.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `support` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1762); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 50 --live
```

Suggested prompt:

> Use the support tools to inspect my orders; propose a refund without executing it.

The live profile is `support`. Its tools and configuration are in
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
| `GET /api/lessons/50` | Lesson metadata |
| `POST /api/lessons/50/run` | Collected JSON events |
| `POST /api/lessons/50/stream` | Server-Sent Events |
| `/api/lessons/50/ws` | WebSocket events and cancellation |

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
