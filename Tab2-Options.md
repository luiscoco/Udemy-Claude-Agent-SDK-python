# Lesson 2: Options

Validate run options before building ClaudeAgentOptions; distinguish omitted values from defaults.

This lesson is part of **SDK fundamentals**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 2
uv run python -m agent_lab.lessons.lesson_02
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 2](http://127.0.0.1:8080/?lesson=2).

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions
from pydantic import BaseModel, ConfigDict, Field


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_turns: int | None = Field(default=None, ge=1, le=20)
    max_budget_usd: float | None = Field(default=None, gt=0, le=1.0)
    model: str | None = None


def build_options(raw: dict[str, object]) -> ClaudeAgentOptions:
    request = RunRequest.model_validate(raw)
    print("set by the user:", sorted(request.model_fields_set))
    # A field left as None is not sent, so the CLI default applies.
    return ClaudeAgentOptions(
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        model=request.model,
        setting_sources=[],
    )


def main() -> None:
    options = build_options({"max_turns": 3, "max_budget_usd": 0.05})
    print(options.max_turns, options.max_budget_usd, options.model)
```

`RunRequest.model_validate(raw)` rejects bad input, `model_fields_set` shows what the user chose, and only accepted values reach `ClaudeAgentOptions(...)`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `options` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 539); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 2 --live
```

Suggested prompt:

> Describe how turn limits and budget thresholds differ.

The live profile is `options`. Its tools and configuration are in
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
| `GET /api/lessons/2` | Lesson metadata |
| `POST /api/lessons/2/run` | Collected JSON events |
| `POST /api/lessons/2/stream` | Server-Sent Events |
| `/api/lessons/2/ws` | WebSocket events and cancellation |

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
