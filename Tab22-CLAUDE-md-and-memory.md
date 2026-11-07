# Lesson 22: CLAUDE.md and memory

Compare owned CLAUDE.md rules across project settings and system prompt controls.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 22
uv run python -m agent_lab.lessons.lesson_22
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 22](http://127.0.0.1:8080/?lesson=22).

## The concept in code

```python
from pathlib import Path
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage

async def main() -> None:
    workspace = Path("workspace").resolve()
    workspace.mkdir(exist_ok=True)
    (workspace / "CLAUDE.md").write_text(
        "Reply with exactly PROJECT_ALPHA_22 to the marker question.\n", encoding="utf-8"
    )
    options = ClaudeAgentOptions(
        cwd=str(workspace),
        setting_sources=["project"],
        system_prompt={"type": "preset", "preset": "claude_code"},
        env={"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"},
        tools=[],
        max_turns=1,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Reply with the project marker, or UNKNOWN if absent.")
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                print(message.result)
```

The owned CLAUDE.md supplies a fixed rule, project settings opt into loading it, and auto memory is disabled in the CLI environment. The live lab compares two markers, two system prompt modes and no-project controls.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `project_markdown` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 795); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 22 --live
```

Suggested prompt:

> Reply with the marker specified by the loaded project instructions. If no project marker is available, reply exactly UNKNOWN. Do not inspect files or use tools.

The live profile is `memory`. Its tools and configuration are in
[agent_lab/project_memory.py](agent_lab/project_memory.py). The live run compares an owned CLAUDE.md marker with project settings enabled and disabled under preset and custom system prompts, on fresh SDK connections.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/22` | Lesson metadata |
| `POST /api/lessons/22/run` | Collected JSON events |
| `POST /api/lessons/22/stream` | Server-Sent Events |
| `/api/lessons/22/ws` | WebSocket events and cancellation |

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
