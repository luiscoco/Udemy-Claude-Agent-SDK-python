# Lesson 5: Custom tools

Validate arguments inside an SDK MCP tool, independently of the model's input schema.

This lesson is part of **SDK fundamentals**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 5
uv run python -m agent_lab.lessons.lesson_05
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 5](http://127.0.0.1:8080/?lesson=5).

## The concept in code

```python
import json
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query, tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Calculation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    a: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    b: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)


@tool(
    "add", "Add two finite numbers. Returns their sum.", Calculation.model_json_schema()
)
async def add(args: dict[str, Any]) -> dict[str, Any]:
    try:
        # The schema is a hint to the model; this check is what the host enforces.
        parsed = Calculation.model_validate(args)
    except ValidationError as error:
        return {"content": [{"type": "text", "text": str(error)}], "is_error": True}
    return {
        "content": [{"type": "text", "text": json.dumps({"sum": parsed.a + parsed.b})}]
    }


async def main() -> None:
    calc = create_sdk_mcp_server(name="calc", tools=[add])
    options = ClaudeAgentOptions(
        mcp_servers={"calc": calc}, tools=[], allowed_tools=["mcp__calc__add"]
    )
    async for message in query(
        prompt="Use the calculator to add 19 and 23.", options=options
    ):
        print(type(message).__name__)
```

`@tool("add", ...)` turns the function into a tool, `Calculation.model_validate(args)` enforces the input inside it, and `create_sdk_mcp_server` exposes it as `mcp__calc__add`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `calculator` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 433); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 5 --live
```

Suggested prompt:

> Use the calculator to add 19 and 23.

The live profile is `calculator`. Its tools and configuration are in
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
| `GET /api/lessons/5` | Lesson metadata |
| `POST /api/lessons/5/run` | Collected JSON events |
| `POST /api/lessons/5/stream` | Server-Sent Events |
| `/api/lessons/5/ws` | WebSocket events and cancellation |

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
