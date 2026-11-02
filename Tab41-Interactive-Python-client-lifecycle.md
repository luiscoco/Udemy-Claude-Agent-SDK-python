# Lesson 41: Interactive Python client lifecycle

Manage interactive sessions with ClaudeSDKClient query and receive_response.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 41
uv run python -m agent_lab.lessons.lesson_41
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 41](http://127.0.0.1:8080/?lesson=41).

## The concept in code

```python
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk import CLIConnectionError, TextBlock


async def turn(client: ClaudeSDKClient, prompt: str) -> None:
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            print("".join(b.text for b in message.content if isinstance(b, TextBlock)))


async def main() -> None:
    client = ClaudeSDKClient(ClaudeAgentOptions(max_turns=1))
    async with client:  # connect() on enter, disconnect() on exit
        await turn(client, "Introduce yourself as a Python teaching assistant.")
        await turn(client, "Repeat your role in five words.")
    try:
        await client.query("Are you still there?")
    except CLIConnectionError as error:
        print("client is closed:", error)
```

async with client connects and disconnects, each turn() pairs client.query with `receive_response`, and the final query raises CLIConnectionError.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `client_lifecycle` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 761); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 41 --live
```

Suggested prompt:

> Introduce yourself as a Python teaching assistant.

The live profile is `conversation`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

This lesson uses Python's public interactive client lifecycle.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/41` | Lesson metadata |
| `POST /api/lessons/41/run` | Collected JSON events |
| `POST /api/lessons/41/stream` | Server-Sent Events |
| `/api/lessons/41/ws` | WebSocket events and cancellation |

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
