# Lesson 59: Model routing

Route requests with a deterministic host policy and a per-call budget.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 59
uv run python -m agent_lab.lessons.lesson_59
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 59](http://127.0.0.1:8080/?lesson=59).

## The concept in code

```python
from dataclasses import dataclass

from claude_agent_sdk import ClaudeAgentOptions

SIGNALS = ("refactor", "design", "debug", "architecture", "migrate", "security")


@dataclass(frozen=True)
class Route:
    model: str
    max_turns: int
    max_budget_usd: float
    reason: str


def route(task: str) -> Route:
    matched = [word for word in SIGNALS if word in task.lower()]
    if matched or len(task) > 400:
        reason = f"complex: {', '.join(matched) or 'long input'}"
        return Route("sonnet", max_turns=6, max_budget_usd=0.25, reason=reason)
    return Route("haiku", max_turns=2, max_budget_usd=0.05, reason="simple task")


def options_for(task: str) -> ClaudeAgentOptions:
    chosen = route(task)
    print(f"routing to {chosen.model}: {chosen.reason}")
    return ClaudeAgentOptions(
        model=chosen.model,
        max_turns=chosen.max_turns,
        max_budget_usd=chosen.max_budget_usd,
    )
```

route() applies explicit keyword and length rules and returns a Route whose model, `max_turns` and `max_budget_usd` are passed straight into ClaudeAgentOptions, with the reason logged.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `routing` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1660); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 59 --live
```

Suggested prompt:

> Use the exercise tool to inspect model routing decisions.

The live profile is `exercise`. Its tools and configuration are in
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
| `GET /api/lessons/59` | Lesson metadata |
| `POST /api/lessons/59/run` | Collected JSON events |
| `POST /api/lessons/59/stream` | Server-Sent Events |
| `/api/lessons/59/ws` | WebSocket events and cancellation |

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
