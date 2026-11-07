# Lesson 37: Permission prompt tool

Handle tool permission decisions with Python can_use_tool results.

This lesson is part of **Permissions and security**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 37
uv run python -m agent_lab.lessons.lesson_37
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 37](http://127.0.0.1:8080/?lesson=37).

## The concept in code

```python
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import ClaudeAgentOptions

from agent_lab.permission_gate_lab import GATE_TOOL, GateState, gate_config

root = Path.cwd()
gate = GateState(root, "demo-run", "demo-gate", "demo-token", "allow")
# A fixed stdio MCP process asks the host gate for one Write decision.
options = ClaudeAgentOptions(
    tools=["Write"],
    allowed_tools=[],
    permission_prompt_tool_name=GATE_TOOL,
    mcp_servers={"gate": cast(Any, gate_config(gate, "http://127.0.0.1:8765", root / "gate-log.jsonl"))},
    max_turns=4,
    max_budget_usd=0.10,
)
# This is an options example; the full lab starts the bridge and checks effects.
```

GateState.decide validates identity and exact Write input; the stdio MCP tool returns one JSON text block; gate_report correlates process, SDK and disk evidence.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `permission_callback_cases` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 447); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 37 --live
```

Suggested prompt:

> Read notes.txt and describe the permission decision.

The live profile is `hooks`. Its tools and configuration are in
[agent_lab/permission_gate_lab.py](agent_lab/permission_gate_lab.py). A fixed Python stdio MCP process asks a loopback host gate for one owned Write decision. The SDK uses permission_prompt_tool_name and an exact Write hook; process receipt, SDK result and fresh file content must agree. Node is unavailable in this Python workspace.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/37` | Lesson metadata |
| `POST /api/lessons/37/run` | Collected JSON events |
| `POST /api/lessons/37/stream` | Server-Sent Events |
| `/api/lessons/37/ws` | WebSocket events and cancellation |

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
