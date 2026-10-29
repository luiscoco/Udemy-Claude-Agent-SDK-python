# Lesson 54: Designing tools the model uses well

Use clear descriptions, bounded input schemas and actionable validation failures.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 54
uv run python -m agent_lab.lessons.lesson_54
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 54](http://127.0.0.1:8080/?lesson=54).

## The concept in code

```python
from typing import Any

from claude_agent_sdk import tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class AddInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: float = Field(ge=-1e9, le=1e9, description="First number to add")
    b: float = Field(ge=-1e9, le=1e9, description="Second number to add")


def feedback(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}. Fix: send only a and b, numbers in [-1e9, 1e9]."
        for e in error.errors()
    )


@tool(
    "add",
    "Add two numbers a and b and return the exact sum. Use it for arithmetic, not for counting text.",
    AddInput.model_json_schema(),
)
async def add(args: dict[str, Any]) -> dict[str, Any]:
    try:
        data = AddInput.model_validate(args)
    except ValidationError as error:
        return {
            "content": [{"type": "text", "text": feedback(error)}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": str(data.a + data.b)}]}
```

The @tool call pairs a precise description with AddInput.model_json_schema(), and the handler turns a Pydantic ValidationError into `is_error` feedback naming the field, the problem and the fix.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `tool_design` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 459); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 54 --live
```

Suggested prompt:

> Use the calculator to add 12.5 and 29.5.

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
| `GET /api/lessons/54` | Lesson metadata |
| `POST /api/lessons/54/run` | Collected JSON events |
| `POST /api/lessons/54/stream` | Server-Sent Events |
| `/api/lessons/54/ws` | WebSocket events and cancellation |

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
