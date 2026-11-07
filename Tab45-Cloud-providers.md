# Lesson 45: Cloud providers

Validate mutually exclusive provider environment flags without embedding credentials.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 45
uv run python -m agent_lab.lessons.lesson_45
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 45](http://127.0.0.1:8080/?lesson=45).

## The concept in code

```python
from agent_lab.cloud_wire import HAIKU, canonical_model

wire_model = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
assert canonical_model(wire_model) == HAIKU

# The proxy verifies the lane credential, then records a sanitized receipt.
# A live check joins that receipt to an upstream message ID and SDK session.
```

`canonical_model` accepts only fixed Haiku spellings for forwarding; `evaluate_native` joins authenticated wire, upstream and SDK identities. Provider flags and catalog labels alone cannot pass.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `providers` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1438); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 45 --live
```

Suggested prompt:

> Explain direct API, Bedrock and Vertex hosting choices.

The live profile is `query`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

The exercise validates provider selection locally; real provider calls require your cloud account, model access and credentials.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/45` | Lesson metadata |
| `POST /api/lessons/45/run` | Collected JSON events |
| `POST /api/lessons/45/stream` | Server-Sent Events |
| `/api/lessons/45/ws` | WebSocket events and cancellation |

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
