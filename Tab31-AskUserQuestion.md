# Lesson 31: AskUserQuestion

Validate the tool's question shape and route a response through the permission callback.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 31
uv run python -m agent_lab.lessons.lesson_31
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 31](http://127.0.0.1:8080/?lesson=31).

## The concept in code

```python
import asyncio
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ToolPermissionContext
from claude_agent_sdk import (
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
)
from pydantic import BaseModel, Field


class Question(BaseModel):
    question: str
    header: str = Field(max_length=30)
    options: list[dict[str, str]] = Field(min_length=2, max_length=4)


async def can_use_tool(
    name: str, tool_input: dict[str, Any], _: ToolPermissionContext
) -> PermissionResult:
    if name != "AskUserQuestion":
        return PermissionResultDeny(message="Only AskUserQuestion is enabled.")
    answers: dict[str, str] = {}
    for q in (Question.model_validate(item) for item in tool_input["questions"]):
        labels = ", ".join(option["label"] for option in q.options)
        answers[q.question] = await asyncio.to_thread(
            input, f"{q.question} ({labels}): "
        )
    return PermissionResultAllow(updated_input={**tool_input, "answers": answers})


async def main() -> None:
    options = ClaudeAgentOptions(tools=["AskUserQuestion"], can_use_tool=can_use_tool)
    async with ClaudeSDKClient(options) as client:
        await client.query("Use AskUserQuestion to ask which response style I prefer.")
        async for message in client.receive_response():
            print(message)
```

The can_use_tool callback catches AskUserQuestion, validates each question with the Question model, and returns PermissionResultAllow(updated_input={..., "answers": answers}).

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `questions` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1156); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 31 --live
```

Suggested prompt:

> Use AskUserQuestion to ask which response style I prefer.

The live profile is `questions`. Its tools and configuration are in
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
| `GET /api/lessons/31` | Lesson metadata |
| `POST /api/lessons/31/run` | Collected JSON events |
| `POST /api/lessons/31/stream` | Server-Sent Events |
| `/api/lessons/31/ws` | WebSocket events and cancellation |

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
