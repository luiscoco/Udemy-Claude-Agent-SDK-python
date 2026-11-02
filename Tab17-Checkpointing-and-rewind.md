# Lesson 17: Checkpointing and rewind

Snapshot a workspace file and restore it; inspect the SDK's rewind interface separately.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 17
uv run python -m agent_lab.lessons.lesson_17
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 17](http://127.0.0.1:8080/?lesson=17).

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, UserMessage


async def main() -> None:
    options = ClaudeAgentOptions(
        enable_file_checkpointing=True,
        extra_args={"replay-user-messages": None},  # stream UserMessage.uuid values
        tools=["Read", "Edit"],
        allowed_tools=["Read", "Edit"],
        cwd="workspace",
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Rewrite notes.txt as a bulleted list.")
        checkpoint: str | None = None
        async for message in client.receive_response():
            if isinstance(message, UserMessage) and message.uuid and checkpoint is None:
                checkpoint = message.uuid
        if checkpoint is not None:
            # Files return to the checkpoint; the conversation history is unchanged.
            await client.rewind_files(checkpoint)
```

`enable_file_checkpointing=True` tracks file edits, the first `UserMessage.uuid` marks the checkpoint, and `client.rewind_files(checkpoint)` restores the files.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `checkpoint` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1033); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 17 --live
```

Suggested prompt:

> Explain the difference between rewinding files and resetting a conversation.

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

Offline rewind is a host file snapshot. Live SDK checkpointing needs a write-enabled session; this lab does not grant writes to the model.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/17` | Lesson metadata |
| `POST /api/lessons/17/run` | Collected JSON events |
| `POST /api/lessons/17/stream` | Server-Sent Events |
| `/api/lessons/17/ws` | WebSocket events and cancellation |

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
