# Lesson 35: Session stores

Persist and reload a host-owned JSON transcript with an atomic replacement.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 35
uv run python -m agent_lab.lessons.lesson_35
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 35](http://127.0.0.1:8080/?lesson=35).

## The concept in code

```python
import json
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions,
    InMemorySessionStore,
    ResultMessage,
    query,
)


def load_transcript(path: Path) -> list[dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save_transcript(path: Path, rows: list[dict[str, str]]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    temporary.replace(
        path
    )  # atomic: readers see the old file or the new one, never half


async def main() -> None:
    path = Path("transcript.json")
    rows = load_transcript(path)
    prompt = "Remember the code word CONTEXT."
    # SDK session state is mirrored through session_store, never through your host file.
    options = ClaudeAgentOptions(session_store=InMemorySessionStore())
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            rows.append(
                {"role": "user", "text": prompt, "session_id": message.session_id}
            )
            rows.append({"role": "assistant", "text": message.result or ""})
    save_transcript(path, rows)
```

The host writes transcript.tmp and calls Path.replace. ClaudeAgentOptions(session_store=...) independently mirrors SDK state. The SQLite adapter persists its entries for a reopened client and isolated CLI configuration; the in-memory adapter demonstrates the process-local variant.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `store` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1369); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 35 --live
```

Suggested prompt:

> Use the exercise tool and explain the transcript store boundaries.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/session_store_lab.py](agent_lab/session_store_lab.py). The host verifies atomic JSON replacement and UUID coverage against the SDK mirror. In-memory and durable SQLite resume, eager/batched flushing, disabled storage, and rejected/delayed store operations have bounded checks. No model tools are enabled.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

The host JSON store is an application transcript store, not a substitute for the SDK's session state.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/35` | Lesson metadata |
| `POST /api/lessons/35/run` | Collected JSON events |
| `POST /api/lessons/35/stream` | Server-Sent Events |
| `/api/lessons/35/ws` | WebSocket events and cancellation |

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
