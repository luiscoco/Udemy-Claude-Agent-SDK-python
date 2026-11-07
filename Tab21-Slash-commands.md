# Lesson 21: Slash commands

Discover an owned project command and verify its slash invocation with a matching Read and response marker.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 21
uv run python -m agent_lab.lessons.lesson_21
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 21](http://127.0.0.1:8080/?lesson=21).

## The concept in code

```python
from pathlib import Path
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

async def main() -> None:
    workspace = Path("workspace").resolve()
    command = workspace / ".claude" / "commands" / "lesson-summary.md"
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("Read notes.txt once. Summarize it in three bullets.\n", encoding="utf-8")
    options = ClaudeAgentOptions(
        cwd=str(workspace),
        setting_sources=["project"],
        tools=["Read"],
        allowed_tools=[],
        max_turns=3,
    )
    async with ClaudeSDKClient(options=options) as client:
        info = await client.get_server_info()
        names = {item.get("name") for item in (info or {}).get("commands", [])}
        assert "lesson-summary" in names
        await client.query("/lesson-summary")
        async for message in client.receive_response():
            print(type(message).__name__)
```

The command is written inside an owned workspace, project settings enable discovery, get_server_info verifies inventory, and the slash prompt invokes the command. The live lab adds exact Read and response correlation.

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
uv run agent-lab lesson 21 --live
```

Suggested prompt:

> /lesson-summary

The live profile is `commands`. Its tools and configuration are in
[agent_lab/slash_commands.py](agent_lab/slash_commands.py). The live run uses one SDK connection to inspect command inventory, invoke the owned slash command, and correlate a Read result with the selected response marker.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/21` | Lesson metadata |
| `POST /api/lessons/21/run` | Collected JSON events |
| `POST /api/lessons/21/stream` | Server-Sent Events |
| `/api/lessons/21/ws` | WebSocket events and cancellation |

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
