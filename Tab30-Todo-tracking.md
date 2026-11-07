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

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

TASKS = ("read", "verify", "publish")
ALLOWED = {("pending", "in_progress"), ("in_progress", "completed")}
ledger = dict.fromkeys(TASKS, "pending")
pending: dict[str, dict[str, str]] = {}


async def before_todo(data, tool_use_id, context):
    items = data.get("tool_input", {}).get("todos", [])
    next_state = {item["content"]: item["status"] for item in items}
    problems = []
    if set(next_state) != set(TASKS) or len(items) != len(TASKS):
        problems.append("use exactly the owned tasks")
    if sum(status == "in_progress" for status in next_state.values()) > 1:
        problems.append("only one task may be in progress")
    for name in TASKS:
        old, new = ledger[name], next_state.get(name)
        if new != old and (old, new) not in ALLOWED:
            problems.append(f"{name}: {old} -> {new}")
    if problems:
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "; ".join(problems),
        }}
    if tool_use_id:
        pending[tool_use_id] = next_state
    return {}


async def after_todo(data, tool_use_id, context):
    if tool_use_id in pending:
        ledger.update(pending.pop(tool_use_id))
    return {}


def build_options():
    return ClaudeAgentOptions(
        tools=["TodoWrite"],
        allowed_tools=["TodoWrite"],
        hooks={
            "PreToolUse": [HookMatcher(matcher="TodoWrite", hooks=[before_todo])],
            "PostToolUse": [HookMatcher(matcher="TodoWrite", hooks=[after_todo])],
        },
        env={"CLAUDE_CODE_ENABLE_TASKS": "0"},
    )
```

The simplified concept code stages valid TodoWrite proposals in PreToolUse and commits them in PostToolUse. The runnable validator also checks exact owned task identities and active forms.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `todos` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1155); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 30 --live
```

Suggested prompt:

> Use the exercise tool to inspect the task ledger.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/todo_lab.py](agent_lab/todo_lab.py). The live run checks real TodoWrite calls with PreToolUse, commits accepted results through PostToolUse, and derives suggestions from the host ledger.

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
