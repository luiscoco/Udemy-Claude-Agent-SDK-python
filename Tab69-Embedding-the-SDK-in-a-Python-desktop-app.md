# Lesson 69: Embedding the SDK in a Python desktop app

Reuse the Python lesson service from NiceGUI native mode.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 69
uv run python -m agent_lab.lessons.lesson_69
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 69](http://127.0.0.1:8080/?lesson=69).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `desktop`, line 2194). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("desktop")
def desktop(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """The native window and the browser use the same FastAPI app and lesson service."""
    from importlib.util import find_spec

    from agent_lab.api import create_app
    from agent_lab.config import Settings
    from agent_lab.runtime import RunService

    service = RunService(Settings(enable_live=False, data_dir=root / "desktop-runs"))
    app = create_app(service, with_ui=False)
    paths = {str(getattr(route, "path", "")) for route in app.routes}
    routes = sorted(path for path in paths if path.startswith("/api"))
    return {
        "browser_command": "uv run agent-lab serve",
        "native_command": "uv run agent-lab serve --native",
        "native_window_available": find_spec("webview") is not None,
        "install_native": "uv sync --locked --extra desktop",
        "shared_service": type(app.state.runner).__name__,
        "shared_api_routes": routes,
        "notes": lesson.notes,
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 69 --live
```

Suggested prompt:

> Explain why the Python desktop UI calls the same lesson service.

The live profile is `query`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

This lesson teaches NiceGUI native mode with the same Python service used by the browser UI.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/69` | Lesson metadata |
| `POST /api/lessons/69/run` | Collected JSON events |
| `POST /api/lessons/69/stream` | Server-Sent Events |
| `/api/lessons/69/ws` | WebSocket events and cancellation |

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
