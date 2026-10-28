# Lesson 19: Session management

Inspect list_sessions and get_session_messages without exposing host transcripts.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 19
uv run python -m agent_lab.lessons.lesson_19
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 19](http://127.0.0.1:8080/?lesson=19).

## The concept in code

```python
import os
from pathlib import Path

from claude_agent_sdk import get_session_info, get_session_messages, list_sessions


def inspect_run_sessions(config_dir: Path, workspace: Path) -> None:
    # Call this in a child process: the session functions read CLAUDE_CONFIG_DIR.
    os.environ["CLAUDE_CONFIG_DIR"] = str(config_dir)
    project = str(workspace)
    for session in list_sessions(directory=project, limit=5):
        info = get_session_info(session.session_id, directory=project)
        print(session.session_id, session.summary, info.created_at if info else None)
        for message in get_session_messages(
            session.session_id, directory=project, limit=3
        ):
            print("  ", message.type, message.uuid)
```

`os.environ["CLAUDE_CONFIG_DIR"]` scopes where transcripts are read, then `list_sessions`, `get_session_info` and `get_session_messages` read only that run's sessions.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `session_management` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1995); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 19 --live
```

Suggested prompt:

> Remember the project name Python Lab.

The live profile is `conversation`. Its tools and configuration are in
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
| `GET /api/lessons/19` | Lesson metadata |
| `POST /api/lessons/19/run` | Collected JSON events |
| `POST /api/lessons/19/stream` | Server-Sent Events |
| `/api/lessons/19/ws` | WebSocket events and cancellation |

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
