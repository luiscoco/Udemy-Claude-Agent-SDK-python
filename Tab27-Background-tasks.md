# Lesson 27: Background tasks

Own a background Python task and cancel and await it before cleanup.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 27
uv run python -m agent_lab.lessons.lesson_27
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 27](http://127.0.0.1:8080/?lesson=27).

## The concept in code

```python
import asyncio

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk import (
    TERMINAL_TASK_STATUSES,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
)


async def heartbeat() -> None:
    try:
        await asyncio.Event().wait()  # runs until cancelled
    finally:
        print("heartbeat cleaned up")


async def main() -> None:
    running: set[str] = set()
    options = ClaudeAgentOptions(
        tools=["Bash"], allowed_tools=["Bash(pytest:*)"], cwd="workspace"
    )
    async with ClaudeSDKClient(options=options) as client:
        watcher = asyncio.create_task(heartbeat())
        try:
            await client.query("Run pytest in the background and report when it ends.")
            async for message in client.receive_response():
                if isinstance(message, TaskStartedMessage):
                    running.add(message.task_id)
                elif isinstance(message, TaskNotificationMessage):
                    running.discard(message.task_id)
                elif (
                    isinstance(message, TaskUpdatedMessage)
                    and message.patch.get("status") in TERMINAL_TASK_STATUSES
                ):
                    # Some tasks end with only this update, never a notification.
                    running.discard(message.task_id)
        finally:
            for task_id in running:
                await client.stop_task(task_id)
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
```

The host owns both kinds of background work: `watcher.cancel()` then awaiting it via `asyncio.gather(..., return_exceptions=True)` for its asyncio task, and `client.stop_task(task_id)` for agent tasks still in `running`; a task ends on a `TaskNotificationMessage` or on a `TaskUpdatedMessage` whose status is in `TERMINAL_TASK_STATUSES`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `background` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1066); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 27 --live
```

Suggested prompt:

> Use the exercise tool and explain why tasks need an owner.

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
| `GET /api/lessons/27` | Lesson metadata |
| `POST /api/lessons/27/run` | Collected JSON events |
| `POST /api/lessons/27/stream` | Server-Sent Events |
| `/api/lessons/27/ws` | WebSocket events and cancellation |

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
