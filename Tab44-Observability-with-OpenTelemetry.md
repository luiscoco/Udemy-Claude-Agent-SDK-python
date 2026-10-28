# Lesson 44: Observability with OpenTelemetry

Record a real host span with attributes and export telemetry only when configured.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 44
uv run python -m agent_lab.lessons.lesson_44
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 44](http://127.0.0.1:8080/?lesson=44).

## The concept in code

```python
import os

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query


def telemetry_env() -> dict[str, str]:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return {}  # no backend configured, so nothing is exported
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
        "OTEL_RESOURCE_ATTRIBUTES": "lesson.id=44,run.mode=live",
    }


async def main() -> None:
    options = ClaudeAgentOptions(env=telemetry_env(), max_turns=1)
    async for message in query(prompt="Explain the trace attributes.", options=options):
        if isinstance(message, ResultMessage):
            print(message.session_id, message.duration_ms, message.total_cost_usd)
```

telemetry_env returns OTLP exporter settings only when OTEL_EXPORTER_OTLP_ENDPOINT is configured, and ClaudeAgentOptions(env=...) hands them to the CLI.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `telemetry` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1373); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 44 --live
```

Suggested prompt:

> Use the exercise tool and explain the trace attributes.

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
| `GET /api/lessons/44` | Lesson metadata |
| `POST /api/lessons/44/run` | Collected JSON events |
| `POST /api/lessons/44/stream` | Server-Sent Events |
| `/api/lessons/44/ws` | WebSocket events and cancellation |

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
