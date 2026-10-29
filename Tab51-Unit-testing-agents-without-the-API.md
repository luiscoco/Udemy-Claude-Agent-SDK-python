# Lesson 51: Unit testing agents without the API

Use a fake async message source to test host logic without pretending a model ran.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 51
uv run python -m agent_lab.lessons.lesson_51
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 51](http://127.0.0.1:8080/?lesson=51).

## The concept in code

```python
from collections.abc import AsyncIterator

from claude_agent_sdk import AssistantMessage, Message, ResultMessage, TextBlock


async def collect(messages: AsyncIterator[Message]) -> tuple[str, float | None]:
    text: list[str] = []
    cost: float | None = None
    async for message in messages:
        if isinstance(message, AssistantMessage):
            text += [
                block.text for block in message.content if isinstance(block, TextBlock)
            ]
        elif isinstance(message, ResultMessage):
            cost = message.total_cost_usd
    return "".join(text), cost


async def fake_run() -> AsyncIterator[Message]:
    yield AssistantMessage(
        content=[TextBlock(text="Refunds take 5 days.")], model="fixture"
    )
    yield ResultMessage(
        subtype="success",
        duration_ms=0,
        duration_api_ms=0,
        is_error=False,
        num_turns=1,
        session_id="fixture",
        total_cost_usd=0.0,
    )


async def test_collect_reads_text_and_cost() -> None:
    # The fixture stands in for query(): no CLI process starts and no API call is made.
    assert await collect(fake_run()) == ("Refunds take 5 days.", 0.0)
```

collect() accepts any AsyncIterator[Message], so the test feeds it `fake_run()`, a generator of real AssistantMessage, TextBlock and ResultMessage objects, instead of query().

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `message_exercise` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 94); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 51 --live
```

Suggested prompt:

> Use the exercise tool and explain the offline test contract.

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
| `GET /api/lessons/51` | Lesson metadata |
| `POST /api/lessons/51/run` | Collected JSON events |
| `POST /api/lessons/51/stream` | Server-Sent Events |
| `/api/lessons/51/ws` | WebSocket events and cancellation |

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
