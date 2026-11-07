# Lesson 24: Harnesses

Validate structured SDK proposals against exact host rules before deterministic execution.

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
from pathlib import Path
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    files: list[str] = Field(min_length=1)

class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tasks: list[Task] = Field(min_length=1)

def host_accepts(plan: Plan, root: Path) -> bool:
    expected = {"T1": "src/tags.py", "T2": "src/search.py"}
    if len(plan.tasks) != 2 or {task.id for task in plan.tasks} != set(expected):
        return False
    return all(task.files == [expected[task.id]] and
               (root / expected[task.id]).resolve().is_relative_to(root.resolve())
               for task in plan.tasks)

async def propose(root: Path) -> Plan | None:
    options = ClaudeAgentOptions(
        cwd=str(root), tools=[], setting_sources=[],
        output_format={"type": "json_schema", "schema": Plan.model_json_schema()},
        max_turns=4,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Propose T1 for src/tags.py and T2 for src/search.py.")
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                try:
                    plan = Plan.model_validate(message.structured_output, strict=True)
                except ValidationError:
                    return None
                return plan if host_accepts(plan, root) else None
    return None
```

The SDK structured output is parsed again by the host. Exact task IDs and canonical owned paths are checked before a separate approval gate can start fixed workers.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `harness` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1279); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 24 --live
```

Suggested prompt:

> Propose the selected fixed task plan for host validation.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/harness_lab.py](agent_lab/harness_lab.py). The live run receives a structured plan, applies exact host validation and approval, then records deterministic worker effects or a specific rejection.

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
