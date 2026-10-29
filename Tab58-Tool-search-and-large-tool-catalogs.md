# Lesson 58: Tool search and large tool catalogs

Select a bounded relevant tool set from a labelled catalog.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 58
uv run python -m agent_lab.lessons.lesson_58
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 58](http://127.0.0.1:8080/?lesson=58).

## The concept in code

```python
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, SdkMcpTool, create_sdk_mcp_server, tool


def make_tool(name: str, description: str) -> SdkMcpTool[Any]:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": f"{name} ran with {args}"}]}

    return tool(name, description, {"query": str})(handler)


CATALOG = [
    make_tool("orders_read", "read customer orders"),
    make_tool("policy_search", "search refund policy"),
    make_tool("sales_analyze", "compute sales totals"),
]


def options_for(request: str, limit: int = 2) -> ClaudeAgentOptions:
    terms = set(request.lower().split())

    def score(item: SdkMcpTool[Any]) -> int:
        return len(terms & set(item.description.split()))

    selected = [
        item
        for item in sorted(CATALOG, key=score, reverse=True)[:limit]
        if score(item) > 0
    ]
    server = create_sdk_mcp_server("shop", tools=selected)
    return ClaudeAgentOptions(
        mcp_servers={"shop": server},
        tools=[],  # no built-ins: the model sees only the subset
        allowed_tools=[f"mcp__shop__{item.name}" for item in selected],
    )
```

`options_for()` scores CATALOG against the request, registers only the top matches with `create_sdk_mcp_server`, sets tools=[] to hide built-ins and pre-approves exactly those mcp__shop__ names in `allowed_tools`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `tool_search` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1592); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 58 --live
```

Suggested prompt:

> Use the exercise tool to search the tool catalog.

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
| `GET /api/lessons/58` | Lesson metadata |
| `POST /api/lessons/58/run` | Collected JSON events |
| `POST /api/lessons/58/stream` | Server-Sent Events |
| `/api/lessons/58/ws` | WebSocket events and cancellation |

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
