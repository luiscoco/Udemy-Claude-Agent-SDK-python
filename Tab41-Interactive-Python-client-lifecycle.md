# Lesson 41: Interactive Python client lifecycle

Manage interactive sessions with ClaudeSDKClient query and receive_response.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 41
uv run python -m agent_lab.lessons.lesson_41
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 41](http://127.0.0.1:8080/?lesson=41).

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage


async def one_turn(client: ClaudeSDKClient, prompt: str) -> ResultMessage:
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, ResultMessage):
            return message
    raise RuntimeError("No terminal result")


async def base_and_resume(session_home: str) -> None:
    options = ClaudeAgentOptions(tools=[], setting_sources=[], max_turns=3)
    async with ClaudeSDKClient(options) as client:
        for prompt in ("Remember Ana teaches Python", "Suggest a title", "Recall the name"):
            result = await one_turn(client, prompt)
            if result.subtype != "success" or result.is_error:
                raise RuntimeError("Turn failed")
        session_id = result.session_id

    resumed = ClaudeAgentOptions(resume=session_id, tools=[], setting_sources=[], max_turns=1)
    async with ClaudeSDKClient(resumed) as client:
        result = await one_turn(client, "Recall the name and subject")
        if result.session_id != session_id or result.is_error:
            raise RuntimeError("Resume identity or result failed")

# This Python lifecycle example is an adaptation, not the historical JavaScript V2 API.
```

One connected Python client handles three sequential turns. A fresh client resumes the validated session ID, and every terminal subtype and identity is checked.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `client_lifecycle` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 765); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 41 --live
```

Suggested prompt:

> Introduce yourself as a Python teaching assistant.

The live profile is `conversation`. Its tools and configuration are in
[agent_lab/client_lifecycle_lab.py](agent_lab/client_lifecycle_lab.py). Three fixed prompts run sequentially through one connected Python ClaudeSDKClient. A completed owned manifest records the session ID; a fresh client resumes that same ID and must return a successful terminal. Prepared mode uses ScriptedCLI and is labelled as a fixture. The historical JavaScript V2 API is not a Python SDK export.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

This lesson uses Python's public interactive client lifecycle.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/41` | Lesson metadata |
| `POST /api/lessons/41/run` | Collected JSON events |
| `POST /api/lessons/41/stream` | Server-Sent Events |
| `/api/lessons/41/ws` | WebSocket events and cancellation |

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
