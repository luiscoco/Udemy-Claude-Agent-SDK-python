# Lesson 23: Plugins

Load a host-owned local plugin and verify namespaced command discovery and Skill invocation.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 23
uv run python -m agent_lab.lessons.lesson_23
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 23](http://127.0.0.1:8080/?lesson=23).

## The concept in code

```python
import json
from pathlib import Path
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage

async def main() -> None:
    workspace = Path("workspace").resolve()
    plugin = workspace / "teaching-plugin"
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / "commands").mkdir(exist_ok=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "python-teaching", "version": "1.0.0"}), encoding="utf-8"
    )
    (plugin / "commands" / "explain.md").write_text(
        "Explain this Python lesson briefly.\n", encoding="utf-8"
    )
    options = ClaudeAgentOptions(
        cwd=str(workspace),
        plugins=[{"type": "local", "path": str(plugin)}],
        setting_sources=[],
        tools=[],
        max_turns=3,
    )
    async with ClaudeSDKClient(options=options) as client:
        info = await client.get_server_info()
        names = {item.get("name") for item in (info or {}).get("commands", [])}
        assert "python-teaching:explain" in names
        await client.query("/python-teaching:explain")
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                print(message.result)
```

The manifest names the plugin; the explicit local path loads it; SDK inventory verifies the namespaced command before invocation. The live lab also checks the packaged Skill tool call.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `plugins` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 807); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 23 --live
```

Suggested prompt:

> Invoke the selected owned plugin extension.

The live profile is `plugins`. Its tools and configuration are in
[agent_lab/plugin_lab.py](agent_lab/plugin_lab.py). The live run checks namespaced command inventory and response markers, a correlated Skill tool call, and a disabled-plugin discovery control.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/23` | Lesson metadata |
| `POST /api/lessons/23/run` | Collected JSON events |
| `POST /api/lessons/23/stream` | Server-Sent Events |
| `/api/lessons/23/ws` | WebSocket events and cancellation |

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
