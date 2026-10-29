# Lesson 38: Prompt suggestions

Generate host-owned next-action suggestions from a validated task state.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 38
uv run python -m agent_lab.lessons.lesson_38
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 38](http://127.0.0.1:8080/?lesson=38).

## The concept in code

```python
from typing import Literal

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ToolUseBlock,
)
from pydantic import BaseModel


class Todo(BaseModel):
    content: str
    status: Literal["pending", "in_progress", "completed"]


def suggestion(todos: list[Todo]) -> str | None:
    active = [todo.content for todo in todos if todo.status == "in_progress"]
    waiting = [todo.content for todo in todos if todo.status == "pending"]
    if active:
        return f"Finish: {active[0]}"
    return f"Start: {waiting[0]}" if waiting else None


async def main() -> None:
    todos: list[Todo] = []
    async with ClaudeSDKClient(
        ClaudeAgentOptions(tools=["TodoWrite", "Read"])
    ) as client:
        await client.query("Plan the release checklist and track it with TodoWrite.")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name == "TodoWrite":
                        todos = [
                            Todo.model_validate(item) for item in block.input["todos"]
                        ]
    # The host, not the model, derives the next prompt from validated state.
    print("Suggested next prompt:", suggestion(todos))
```

The `receive_response` loop validates each TodoWrite ToolUseBlock into Todo models, and suggestion() derives the next prompt from the in-progress or pending task.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `todos` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1112); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 38 --live
```

Suggested prompt:

> Use the exercise tool and explain the suggested next action.

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
| `GET /api/lessons/38` | Lesson metadata |
| `POST /api/lessons/38/run` | Collected JSON events |
| `POST /api/lessons/38/stream` | Server-Sent Events |
| `/api/lessons/38/ws` | WebSocket events and cancellation |

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
