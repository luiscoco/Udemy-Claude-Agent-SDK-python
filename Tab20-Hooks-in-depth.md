# Lesson 20: Hooks in depth

Correlate hook decisions, input rewrites, success/failure audits and prompt/Stop lifecycle observations.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 20
uv run python -m agent_lab.lessons.lesson_20
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 20](http://127.0.0.1:8080/?lesson=20).

## The concept in code

```python
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions, HookContext, HookInput, HookJSONOutput, HookMatcher,
)


def build_options(workspace: Path) -> ClaudeAgentOptions:
    root = workspace.resolve()

    async def guard(
        data: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        if data["hook_event_name"] != "PreToolUse":
            return {}
        allowed = False
        if data["tool_name"] == "Read":
            try:
                target = (root / str(data["tool_input"].get("file_path", ""))).resolve()
                allowed = target.is_relative_to(root) and target == root / "notes.txt"
            except (ValueError, OSError):
                pass
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if allowed else "deny",
            "permissionDecisionReason": "Only the owned notes.txt Read is permitted.",
        }}

    async def audit(
        data: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        if data["hook_event_name"] == "PostToolUse":
            # Log identity and size, not the response body.
            print(data["tool_name"], tool_use_id, len(str(data["tool_response"])))
        return {}

    return ClaudeAgentOptions(
        cwd=str(root), tools=["Read"], allowed_tools=[], setting_sources=[],
        strict_mcp_config=True,
        hooks={
            "PreToolUse": [HookMatcher(matcher="Read", hooks=[guard], timeout=10)],
            "PostToolUse": [HookMatcher(hooks=[audit], timeout=10)],
        },
        max_turns=4, max_budget_usd=0.10,
    )
```

The resolved path and tool name determine the pre-hook decision; no string-prefix path check is used. The successful post-hook records identity and size only. The full lab additionally correlates rewrite/failure effects, prompt/Stop observations and an independent host boundary.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `hook_pipeline` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 386); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 20 --live
```

Suggested prompt:

> Read notes.txt, then explain the tool result.

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
| `GET /api/lessons/20` | Lesson metadata |
| `POST /api/lessons/20/run` | Collected JSON events |
| `POST /api/lessons/20/stream` | Server-Sent Events |
| `/api/lessons/20/ws` | WebSocket events and cancellation |

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
