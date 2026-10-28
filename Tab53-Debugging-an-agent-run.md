# Lesson 53: Debugging an agent run

Correlate events by run id and redact secret-like values from diagnostic bundles.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 53
uv run python -m agent_lab.lessons.lesson_53
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 53](http://127.0.0.1:8080/?lesson=53).

## The concept in code

```python
import re
import uuid
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

SECRET_KEY = re.compile(r"token|secret|password|api.?key|authorization", re.IGNORECASE)
SECRET_VALUE = re.compile(r"sk-ant-[\w-]+|Bearer\s+\S+")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if SECRET_KEY.search(k) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return SECRET_VALUE.sub("[REDACTED]", value) if isinstance(value, str) else value


async def main() -> None:
    run_id = uuid.uuid4().hex
    trace: list[dict[str, Any]] = []
    options = ClaudeAgentOptions(
        max_turns=3,
        stderr=lambda line: trace.append({"run_id": run_id, "stderr": line}),
    )
    async for message in query(
        prompt="List the Python files in src/.", options=options
    ):
        event: dict[str, Any] = {"run_id": run_id, "type": type(message).__name__}
        if isinstance(message, ResultMessage):
            event |= {
                "session_id": message.session_id,
                "subtype": message.subtype,
                "errors": message.errors,
            }
        trace.append(event)
    print(redact(trace))  # only the redacted bundle leaves the process
```

Every message and every CLI stderr line (via the stderr callback) is tagged with one run_id, and the bundle passes through redact() before it is printed or shared.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `debugging` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1511); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 53 --live
```

Suggested prompt:

> Use the exercise tool and explain the redacted diagnostic trace.

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
| `GET /api/lessons/53` | Lesson metadata |
| `POST /api/lessons/53/run` | Collected JSON events |
| `POST /api/lessons/53/stream` | Server-Sent Events |
| `/api/lessons/53/ws` | WebSocket events and cancellation |

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
