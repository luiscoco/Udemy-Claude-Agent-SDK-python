# Lesson 12: Streaming input

Produce SDK user-message dictionaries from a Python asynchronous iterable.

This lesson is part of **SDK fundamentals**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 12
uv run python -m agent_lab.lessons.lesson_12
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 12](http://127.0.0.1:8080/?lesson=12).

## The concept in code

```python
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query


async def user_messages(prompts: list[str]) -> AsyncIterator[dict[str, Any]]:
    for text in prompts:
        # Produced lazily: each dict is built only when the SDK pulls the next item.
        yield {
            "type": "user",
            "message": {"role": "user", "content": text},
            "parent_tool_use_id": None,
            "session_id": "default",
        }


async def main() -> None:
    prompts = ["Explain an async iterator.", "Now give a one-line example."]
    options = ClaudeAgentOptions(tools=[], max_turns=4)
    async for message in query(prompt=user_messages(prompts), options=options):
        if isinstance(message, ResultMessage):
            print(message.num_turns, message.result)
```

The compact concept example streams a finite iterable. The expanded experiment in agent_lab/streaming.py keeps a wakeable queue open, records acknowledged controls and checks complete closure; inspect its three exact excerpts below the standard example.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `streaming` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 864); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 12 --live
```

Suggested prompt:

> Explain how an asynchronous input iterator works.

The live profile is `streaming`. Its tools and configuration are in
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
| `GET /api/lessons/12` | Lesson metadata |
| `POST /api/lessons/12/run` | Collected JSON events |
| `POST /api/lessons/12/stream` | Server-Sent Events |
| `/api/lessons/12/ws` | WebSocket events and cancellation |

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
