# Lesson 25: Compaction and context

Bound tool result size and preserve a compact host summary of completed work.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 25
uv run python -m agent_lab.lessons.lesson_25
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 25](http://127.0.0.1:8080/?lesson=25).

## The concept in code

```python
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, HookContext, HookInput, HookJSONOutput
from claude_agent_sdk import HookMatcher, create_sdk_mcp_server, tool

LIMIT = 600


@tool("read_log", "Read workspace/build.log, bounded to 600 characters.", {})
async def read_log(args: dict[str, Any]) -> dict[str, Any]:
    raw = Path("workspace/build.log").read_text(encoding="utf-8")
    text = (
        raw
        if len(raw) <= LIMIT
        else raw[:LIMIT] + f"\n[truncated {len(raw) - LIMIT} chars]"
    )
    return {"content": [{"type": "text", "text": text}]}


async def before_compact(
    data: HookInput, tool_use_id: str | None, context: HookContext
) -> HookJSONOutput:
    if data["hook_event_name"] == "PreCompact":
        print(
            "SDK compaction starting:", data["trigger"]
        )  # save the host summary first
    return {}


def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        mcp_servers={"logs": create_sdk_mcp_server(name="logs", tools=[read_log])},
        allowed_tools=["mcp__logs__read_log"],
        hooks={"PreCompact": [HookMatcher(hooks=[before_compact])]},
    )
```

The `read_log` tool bounds its result to `LIMIT` characters with an explicit truncation marker, and the `PreCompact` hook marks when the SDK's own compaction starts.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `compaction` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1043); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 25 --live
```

Suggested prompt:

> Explain what context compaction preserves and what it may lose.

The live profile is `query`. Its tools and configuration are in
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
| `GET /api/lessons/25` | Lesson metadata |
| `POST /api/lessons/25/run` | Collected JSON events |
| `POST /api/lessons/25/stream` | Server-Sent Events |
| `/api/lessons/25/ws` | WebSocket events and cancellation |

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
