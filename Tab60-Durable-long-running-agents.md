# Lesson 60: Durable long-running agents

Journal completed steps, replay after interruption and deduplicate side effects.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 60
uv run python -m agent_lab.lessons.lesson_60
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 60](http://127.0.0.1:8080/?lesson=60).

## The concept in code

```python
import json
import os
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def completed(self) -> set[str]:
        lines = (
            self.path.read_text(encoding="utf-8").splitlines()
            if self.path.exists()
            else []
        )
        return {json.loads(line)["key"] for line in lines}

    def append(self, key: str, session_id: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"key": key, "session_id": session_id}) + "\n")
            file.flush()
            os.fsync(file.fileno())


async def run_job(journal: Journal, job_id: str) -> None:
    for step in ("prepare", "compute", "verify"):
        if (key := f"{job_id}:{step}") in journal.completed():
            continue  # idempotency key already journaled: never repeat its side effects
        prompt = f"Run the {step} step of job {job_id}."
        async for message in query(
            prompt=prompt, options=ClaudeAgentOptions(max_turns=4)
        ):
            if isinstance(message, ResultMessage) and not message.is_error:
                journal.append(key, message.session_id)
```

run_job() skips any idempotency key already in journal.completed() and appends a step only after a successful ResultMessage, with flush() and os.fsync() making the record durable.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `durable` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1659); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 60 --live
```

Suggested prompt:

> Use the exercise tool to inspect the resumed journal.

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
| `GET /api/lessons/60` | Lesson metadata |
| `POST /api/lessons/60/run` | Collected JSON events |
| `POST /api/lessons/60/stream` | Server-Sent Events |
| `/api/lessons/60/ws` | WebSocket events and cancellation |

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
