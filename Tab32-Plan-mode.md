# Lesson 32: Plan mode

Validate a plan separately from executing it; use the SDK plan permission mode.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 32
uv run python -m agent_lab.lessons.lesson_32
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 32](http://127.0.0.1:8080/?lesson=32).

## The concept in code

```python
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
)
from pydantic import BaseModel


class Plan(BaseModel):
    steps: list[str]
    files: list[str]


async def reply_text(client: ClaudeSDKClient) -> str:
    parts: list[str] = []
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            parts += [
                block.text for block in message.content if isinstance(block, TextBlock)
            ]
    return "".join(parts)


async def main() -> None:
    options = ClaudeAgentOptions(permission_mode="plan", allowed_tools=["Read"])
    async with ClaudeSDKClient(options) as client:
        await client.query(
            "Read notes.txt and plan improvements. Reply only JSON {steps, files}."
        )
        plan = Plan.model_validate_json(await reply_text(client))
        if input(f"Approve {plan.steps} touching {plan.files}? [y/N] ").lower() != "y":
            return
        # Leave plan mode only after a person approved the validated plan.
        await client.set_permission_mode("acceptEdits")
        await client.query("Execute the approved plan exactly as written.")
        print(await reply_text(client))
```

ClaudeAgentOptions(`permission_mode`="plan") makes the first turn read-only; Plan.model_validate_json checks the proposal and `set_permission_mode`("acceptEdits") runs only after approval.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `plan_mode` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1321); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 32 --live
```

Suggested prompt:

> Read notes.txt, then plan how to improve it. Do not change any files.

The live profile is `plan`. Its tools and configuration are in
[agent_lab/plan_lab.py](agent_lab/plan_lab.py). The SDK starts in plan mode; the host validates a structured proposal and only an approved valid plan triggers a default-mode confirmation and fixed workers. Approval is a selected lab control.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/32` | Lesson metadata |
| `POST /api/lessons/32/run` | Collected JSON events |
| `POST /api/lessons/32/stream` | Server-Sent Events |
| `/api/lessons/32/ws` | WebSocket events and cancellation |

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
