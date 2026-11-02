# Lesson 75: Capstone: an autonomous engineering team

Validate task ownership, execute dependency waves and enforce a host release gate.

This lesson is part of **Multi-agent systems**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 75
uv run python -m agent_lab.lessons.lesson_75
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 75](http://127.0.0.1:8080/?lesson=75).

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import BaseModel, Field, model_validator


class Task(BaseModel):
    id: str
    files: list[str] = Field(min_length=1)
    depends_on: list[str] = []


class Plan(BaseModel):
    tasks: list[Task] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def one_owner_per_file(self) -> "Plan":
        owned = [name for task in self.tasks for name in task.files]
        if len(owned) != len(set(owned)) or not all(
            name.startswith("src/") for name in owned
        ):
            raise ValueError("Every src/ file needs exactly one owner.")
        return self


async def propose[T: BaseModel](
    role: str, prompt: str, schema: type[T], budget_usd: float
) -> T:
    proposal_format = {"type": "json_schema", "schema": schema.model_json_schema()}
    options = ClaudeAgentOptions(
        tools=[], max_turns=2, max_budget_usd=budget_usd, output_format=proposal_format
    )
    results = [
        m
        async for m in query(prompt=prompt, options=options)
        if isinstance(m, ResultMessage)
    ]
    if not results or results[-1].is_error or results[-1].structured_output is None:
        raise RuntimeError(f"The {role} returned no valid proposal.")
    return schema.model_validate(results[-1].structured_output)


def release_gate(
    tests_passed: bool, review_approved: bool, spent_usd: float, limit_usd: float
) -> bool:
    # Agents propose; only the host's own checks decide whether anything ships.
    return tests_passed and review_approved and spent_usd <= limit_usd
```

`propose()` runs each role through `query()` with `output_format` from a Pydantic schema, `Plan.one_owner_per_file` validates ownership, and `release_gate()` lets the host decide the release.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `team` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 2456); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 75 --live
```

Suggested prompt:

> Implement the tag helpers with the engineering team and verify the host release gate.

The live profile is `engineering_team`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

Offline mode uses scripted workers. Live mode runs a lead, parallel developers and reviewer through the SDK; the host validates structured source proposals, runs acceptance checks and decides the release gate. This bounded Python fixture does not push a GitHub PR or implement the original full worktree merge and recovery workflow.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/75` | Lesson metadata |
| `POST /api/lessons/75/run` | Collected JSON events |
| `POST /api/lessons/75/stream` | Server-Sent Events |
| `/api/lessons/75/ws` | WebSocket events and cancellation |

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
