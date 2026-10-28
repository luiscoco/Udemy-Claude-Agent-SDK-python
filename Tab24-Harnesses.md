# Lesson 24: Harnesses

Separate model proposals from deterministic host validation and execution.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 24
uv run python -m agent_lab.lessons.lesson_24
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 24](http://127.0.0.1:8080/?lesson=24).

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import BaseModel, Field, ValidationError, field_validator


class Task(BaseModel):
    id: str
    files: list[str] = Field(min_length=1)

    @field_validator("files")
    @classmethod
    def inside_src(cls, files: list[str]) -> list[str]:
        if not all(name.startswith("src/") for name in files):
            raise ValueError("every file must be under src/")
        return files


class Plan(BaseModel):
    tasks: list[Task] = Field(min_length=1)


async def propose_plan(goal: str) -> Plan | None:
    schema = Plan.model_json_schema()
    options = ClaudeAgentOptions(
        tools=[], output_format={"type": "json_schema", "schema": schema}
    )
    async for message in query(prompt=goal, options=options):
        if isinstance(message, ResultMessage) and message.structured_output is not None:
            try:
                return Plan.model_validate(message.structured_output)
            except ValidationError:
                return None  # rejected proposals never reach a worker
    return None
```

The model's `structured_output` is only a proposal until `Plan.model_validate(...)` accepts it; a `ValidationError` returns `None`, so nothing is executed.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `harness` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1236); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 24 --live
```

Suggested prompt:

> Use the exercise tool to inspect the harness result, then explain its gate.

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
| `GET /api/lessons/24` | Lesson metadata |
| `POST /api/lessons/24/run` | Collected JSON events |
| `POST /api/lessons/24/stream` | Server-Sent Events |
| `/api/lessons/24/ws` | WebSocket events and cancellation |

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
