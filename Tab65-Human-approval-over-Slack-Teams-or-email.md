# Lesson 65: Human approval across channels

Bind an expiring, single-use approval credential to an immutable action.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 65
uv run python -m agent_lab.lessons.lesson_65
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 65](http://127.0.0.1:8080/?lesson=65).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `approval`, line 1411). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("approval")
def approval(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    action = Refund(
        order_id="A-001", amount_cents=4200, reason="Fixture return approved by the host"
    )
    pending = Approval(action)
    pending.decide(pending.token, True)
    pending.consume(action)
    try:
        pending.consume(action)
    except ValueError:
        reuse_denied = True
    return {
        "action": action.model_dump(),
        "fingerprint": pending.fingerprint,
        "state": pending.state,
        "reuse_denied": reuse_denied,
        "delivery": "local fixture, no external notification",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 65 --live
```

Suggested prompt:

> Use the exercise tool to inspect a local approval decision.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

Default delivery is a local approval exercise. Channel adapters require explicit configuration and are never called by an offline run.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/65` | Lesson metadata |
| `POST /api/lessons/65/run` | Collected JSON events |
| `POST /api/lessons/65/stream` | Server-Sent Events |
| `/api/lessons/65/ws` | WebSocket events and cancellation |

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
