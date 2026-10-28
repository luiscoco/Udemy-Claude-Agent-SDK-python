# Lesson 14: Thinking, effort and models

Inspect installed SDK thinking and effort fields rather than copying another language's options.

This lesson is part of **SDK fundamentals**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 14
uv run python -m agent_lab.lessons.lesson_14
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 14](http://127.0.0.1:8080/?lesson=14).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `thinking`, line 124). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("thinking")
def thinking(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Build every thinking configuration the installed SDK accepts, and reject foreign names."""
    import typing

    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk.types import (
        ThinkingConfigAdaptive,
        ThinkingConfigDisabled,
        ThinkingConfigEnabled,
    )

    from agent_lab.sdk import THINKING_PROFILE

    hints = typing.get_type_hints(ClaudeAgentOptions)
    effort_values = list(typing.get_args(typing.get_args(hints["effort"])[0]))
    configs: dict[str, Any] = {
        "adaptive": ThinkingConfigAdaptive(type="adaptive"),
        "fixed budget": ThinkingConfigEnabled(type="enabled", budget_tokens=4000),
        "off": ThinkingConfigDisabled(type="disabled"),
    }
    built = [
        {
            "choice": label,
            "thinking": ClaudeAgentOptions(thinking=config, effort="medium").thinking,
            "keys": sorted(config),
        }
        for label, config in configs.items()
    ]
    foreign = []
    for name in ("maxThinkingTokens", "thinkingBudget", "reasoningEffort"):
        foreign_option: dict[str, Any] = {name: 4000}  # deliberately not a Python option
        try:
            ClaudeAgentOptions(**foreign_option)
            foreign.append({"option": name, "accepted": True})
        except TypeError:
            foreign.append({"option": name, "accepted": False})
    return {
        "installed_version": importlib.metadata.version("claude-agent-sdk"),
        "thinking_type": str(hints["thinking"]),
        "effort_values": effort_values,
        "configs": built,
        "foreign_option_names": foreign,
        "live_profile": THINKING_PROFILE,
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 14 --live
```

Suggested prompt:

> Explain when more reasoning effort is useful.

The live profile is `thinking`. Its tools and configuration are in
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
| `GET /api/lessons/14` | Lesson metadata |
| `POST /api/lessons/14/run` | Collected JSON events |
| `POST /api/lessons/14/stream` | Server-Sent Events |
| `/api/lessons/14/ws` | WebSocket events and cancellation |

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
