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

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `client_lifecycle`, line 634). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("client_lifecycle")
async def client_lifecycle(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Connect, run two turns in one session, disconnect, and refuse use after close."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, CLIConnectionError

    from agent_lab.scripted_cli import ScriptedCLI

    cli = ScriptedCLI([["Remembered: PYTHON-SESSION."], ["The label was PYTHON-SESSION."]])
    client = ClaudeSDKClient(ClaudeAgentOptions(), transport=cli)
    async with asyncio.timeout(20):
        async with client:
            await client.query("Remember PYTHON-SESSION.")
            first = await scripted_turn(client)
            await client.query("Which label?")
            second = await scripted_turn(client)
    try:
        await client.query("After disconnect")
        after_close = "accepted"
    except CLIConnectionError as exc:
        after_close = f"CLIConnectionError: {exc}"
    return {
        "turns": [first, second],
        "same_session": first["session_id"] == second["session_id"],
        "lifecycle": cli.lifecycle,
        "transport_ready_after_exit": cli.is_ready(),
        "query_after_disconnect": after_close,
        "source": "real ClaudeSDKClient talking to a scripted CLI fixture",
    }
```

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
