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
from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
)

ALLOWED = {("pending", "in_progress"), ("in_progress", "completed")}
ledger: dict[str, str] = {}


async def validate_todos(
    data: HookInput, tool_use_id: str | None, context: HookContext
) -> HookJSONOutput:
    if data["hook_event_name"] != "PreToolUse":
        return {}
    todos: list[dict[str, str]] = data["tool_input"].get("todos", [])
    problems = [
        f"{t['content']}: {old} -> {t['status']}"
        for t in todos
        if (old := ledger.get(t["content"], "pending")) != t["status"]
        and (old, t["status"]) not in ALLOWED
    ]
    if sum(t["status"] == "in_progress" for t in todos) > 1:
        problems.append("only one task may be in_progress")
    if not problems:
        ledger.update({t["content"]: t["status"] for t in todos})
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "; ".join(problems),
        }
    }


def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        hooks={"PreToolUse": [HookMatcher(matcher="TodoWrite", hooks=[validate_todos])]}
    )
```

A PreToolUse hook scoped to `TodoWrite` checks each status change against `ALLOWED` and the one-in-progress rule, denies with a reason, and updates the host `ledger` only when every change passes.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `todos` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1113); the Python source tab shows it below the concept code. Host contracts
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
