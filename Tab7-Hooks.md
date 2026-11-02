# Lesson 7: Hooks

Use PreToolUse to make a host policy decision and record an audit event.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 7
uv run python -m agent_lab.lessons.lesson_07
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 7](http://127.0.0.1:8080/?lesson=7).

## The concept in code

```python
from typing import Literal

from claude_agent_sdk import ClaudeAgentOptions, HookContext, HookInput, HookJSONOutput
from claude_agent_sdk import HookMatcher, query

audit_log: list[dict[str, str]] = []


async def pre_tool_use(
    input_data: HookInput, tool_use_id: str | None, context: HookContext
) -> HookJSONOutput:
    if input_data["hook_event_name"] != "PreToolUse":
        return {}
    path = str(input_data["tool_input"].get("file_path", ""))
    decision: Literal["allow", "deny"] = (
        "deny" if ".env" in path or ".." in path else "allow"
    )
    audit_log.append({"tool": input_data["tool_name"], "decision": decision})
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"Host policy: {decision}",
        }
    }


async def main() -> None:
    matcher = HookMatcher(matcher="Read|Glob|Grep", hooks=[pre_tool_use])
    options = ClaudeAgentOptions(
        tools=["Read", "Glob", "Grep"], hooks={"PreToolUse": [matcher]}
    )
    async for message in query(
        prompt="Read notes.txt and summarize it.", options=options
    ):
        print(type(message).__name__, len(audit_log))
```

`pre_tool_use` reads `tool_name` and `tool_input`, returns `hookSpecificOutput` with `permissionDecision`, and `HookMatcher(matcher=..., hooks=[...])` registers it under `"PreToolUse"`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `hooks` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 350); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 7 --live
```

Suggested prompt:

> Read notes.txt and summarize it.

The live profile is `hooks`. Its tools and configuration are in
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
| `GET /api/lessons/7` | Lesson metadata |
| `POST /api/lessons/7/run` | Collected JSON events |
| `POST /api/lessons/7/stream` | Server-Sent Events |
| `/api/lessons/7/ws` | WebSocket events and cancellation |

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
