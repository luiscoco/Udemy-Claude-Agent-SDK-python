# Lesson 23: Plugins

Build a trusted local plugin manifest with a Python-oriented command and skill.

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

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SdkPluginConfig, query


async def main() -> None:
    plugin = Path("teaching-plugin").resolve()
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / "commands").mkdir(exist_ok=True)
    manifest = {"name": "python-teaching", "version": "1.0.0"}
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (plugin / "commands" / "explain.md").write_text(
        "Explain notes.txt with a short Python example.\n", encoding="utf-8"
    )
    plugins: list[SdkPluginConfig] = [{"type": "local", "path": str(plugin)}]
    options = ClaudeAgentOptions(
        plugins=plugins,
        cwd="workspace",
        tools=["Read"],
        allowed_tools=["Read"],
        max_turns=3,
    )
    # Plugin commands are namespaced as /<plugin-name>:<command>.
    async for message in query(prompt="/python-teaching:explain", options=options):
        if isinstance(message, ResultMessage):
            print(message.result)
```

`.claude-plugin/plugin.json` names the plugin, `plugins=[{"type": "local", "path": ...}]` loads it, and `/python-teaching:explain` calls its namespaced command.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `plugins` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 803); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 23 --live
```

Suggested prompt:

> Explain how local plugins extend an agent.

The live profile is `plugins`. Its tools and configuration are in
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
