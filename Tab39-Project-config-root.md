# Lesson 39: Project configuration root

Resolve trusted project paths and opt into settings only in that project.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 39
uv run python -m agent_lab.lessons.lesson_39
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 39](http://127.0.0.1:8080/?lesson=39).

## The concept in code

```python
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage


async def compare(cwd: Path, trusted: Path, config: Path) -> None:
    options = ClaudeAgentOptions(
        cwd=str(cwd),
        setting_sources=["project", "local"],
        extra_args={"project-config-root": str(trusted)},
        tools=[], allowed_tools=[], mcp_servers={},
        strict_mcp_config=True,
        env={"CLAUDE_CONFIG_DIR": str(config)},
        max_turns=3, max_budget_usd=0.10,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Explain the project configuration root briefly.")
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                print(message.session_id, message.subtype)

# Check actual init cwd, hook log and command inventory separately.
# A dry SDK argv capture proves serialization only; it does not load settings.
```

cwd stays at the selected checkout while extra_args serializes an explicit project-config-root. Project and local sources must be enabled; the host verifies configuration origin from init and owned hook/command observations.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `config_root` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 263); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 39 --live
```

Suggested prompt:

> Read notes.txt in this isolated project.

The live profile is `read`. Its tools and configuration are in
[agent_lab/config_root_lab.py](agent_lab/config_root_lab.py). Each run creates owned trusted, branch and docs Git worktrees. A dry SDK argument capture checks project-config-root serialization; live SDK init, hook/command origins and fixture hashes establish selected configuration. A separate exact Bash probe compares trusted tool unavailability with branch permission, and credential-free startup probes capture invalid-root CLI errors.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/39` | Lesson metadata |
| `POST /api/lessons/39/run` | Collected JSON events |
| `POST /api/lessons/39/stream` | Server-Sent Events |
| `/api/lessons/39/ws` | WebSocket events and cancellation |

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
