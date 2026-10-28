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

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `options`, line 450). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("options")
def options(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Validate requests first, then build ClaudeAgentOptions only from accepted values."""
    from claude_agent_sdk import ClaudeAgentOptions

    from agent_lab.config import Settings

    valid = {"omitted values": {}, "explicit values": {"max_turns": 2, "max_budget_usd": 0.05}}
    invalid = {
        "zero turns": {"max_turns": 0},
        "budget is not a number": {"max_budget_usd": float("nan")},
        "budget above the lab limit": {"max_budget_usd": 5},
        "unknown option": {"cwd": "C:/"},
    }
    accepted = []
    for label, body in valid.items():
        parsed = RunRequest.model_validate(body)
        accepted.append(
            {
                "case": label,
                "set_by_student": sorted(parsed.model_fields_set) or ["(none)"],
                "max_turns": parsed.max_turns,
                "max_budget_usd": parsed.max_budget_usd,
            }
        )
    rejected = []
    for label, bad in invalid.items():
        try:
            RunRequest.model_validate(bad)
        except ValidationError as exc:
            error = exc.errors()[0]
            rejected.append({"case": label, "field": str(error["loc"][0]), "problem": error["msg"]})
    chosen = RunRequest.model_validate(valid["explicit values"])
    built = ClaudeAgentOptions(
        model=Settings().model,
        max_turns=chosen.max_turns,
        max_budget_usd=chosen.max_budget_usd,
        tools=[],
        setting_sources=[],
    )
    fields = ("model", "max_turns", "max_budget_usd", "tools", "setting_sources")
    return {
        "accepted": accepted,
        "rejected": rejected,
        "built_options": {name: getattr(built, name) for name in fields},
        "sdk_defaults": {name: getattr(ClaudeAgentOptions(), name) for name in fields},
        "note": "None in sdk_defaults means the option is not sent and the CLI decides. "
        "The lab always sends explicit limits.",
    }
```

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
