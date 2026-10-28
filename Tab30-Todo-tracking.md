# Lesson 30: Todo tracking

Validate task state transitions in a host-owned ledger.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 30
uv run python -m agent_lab.lessons.lesson_30
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 30](http://127.0.0.1:8080/?lesson=30).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `todos`, line 993). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("todos", "suggestions")
def todos(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Validate todo transitions and derive the next suggestion from the resulting state."""
    allowed = {"pending": {"in_progress"}, "in_progress": {"completed", "pending"}}
    tasks = {"read": "pending", "verify": "pending", "release": "pending"}
    requested = [
        ("read", "in_progress"),
        ("read", "completed"),
        ("release", "completed"),  # skips in_progress
        ("verify", "in_progress"),
        ("release", "in_progress"),  # a second task in progress
        ("read", "pending"),  # reopens completed work
    ]
    transitions = []
    for task, target in requested:
        current = tasks[task]
        if target not in allowed.get(current, set()):
            reason = f"{current} cannot move to {target}"
        elif target == "in_progress" and "in_progress" in tasks.values():
            reason = "another task is already in progress"
        else:
            reason = ""
            tasks[task] = target
        transitions.append(
            {"task": task, "from": current, "to": target, "accepted": not reason, "reason": reason}
        )
    active = next((task for task, state in tasks.items() if state == "in_progress"), None)
    waiting = next((task for task, state in tasks.items() if state == "pending"), None)
    suggestion = (
        f"Finish {active} before starting another task."
        if active
        else f"Start {waiting}."
        if waiting
        else "All tasks are complete."
    )
    return {
        "transitions": transitions,
        "rejected": sum(not row["accepted"] for row in transitions),
        "tasks": [{"id": task, "status": state} for task, state in tasks.items()],
        "suggestion": suggestion,
        "source": "derived from validated host state",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 30 --live
```

Suggested prompt:

> Use the exercise tool to inspect the task ledger.

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
| `GET /api/lessons/30` | Lesson metadata |
| `POST /api/lessons/30/run` | Collected JSON events |
| `POST /api/lessons/30/stream` | Server-Sent Events |
| `/api/lessons/30/ws` | WebSocket events and cancellation |

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
