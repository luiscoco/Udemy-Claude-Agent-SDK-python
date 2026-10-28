# Lesson 26: Query control methods

Inspect ClaudeSDKClient control methods and preserve ownership of its async context.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 26
uv run python -m agent_lab.lessons.lesson_26
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 26](http://127.0.0.1:8080/?lesson=26).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `control`, line 590). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("control")
async def control(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Call ClaudeSDKClient control methods and observe their effect on the next turn."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    from agent_lab.scripted_cli import ScriptedCLI

    cli = ScriptedCLI([["Before the switch."], ["After the switch."]])
    owner = asyncio.current_task()
    async with asyncio.timeout(20):
        async with ClaudeSDKClient(ClaudeAgentOptions(), transport=cli) as client:
            info = await client.get_server_info()
            await client.query("First turn")
            before = await scripted_turn(client)
            await client.set_model("claude-sonnet-5-5")
            await client.set_permission_mode("plan")
            await client.query("Second turn")
            after = await scripted_turn(client)
            try:
                await client.get_mcp_status()
                unsupported = "accepted"
            except Exception as exc:
                unsupported = str(exc)
            same_owner = asyncio.current_task() is owner
    return {
        "server_info_keys": sorted(info or {}),
        "before": {"models": before["models"], "text": before["text"]},
        "after": {"models": after["models"], "text": after["text"]},
        "cli_permission_mode": cli.permission_mode,
        "control_requests": [
            m["request"]["subtype"] for m in cli.received if m["type"] == "control_request"
        ],
        "unsupported_request": unsupported,
        "context_owned_by_one_task": same_owner,
        "source": "real ClaudeSDKClient talking to a scripted CLI fixture",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 26 --live
```

Suggested prompt:

> Explain the difference between interrupting a turn and disconnecting a client.

The live profile is `conversation`. Its tools and configuration are in
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
| `GET /api/lessons/26` | Lesson metadata |
| `POST /api/lessons/26/run` | Collected JSON events |
| `POST /api/lessons/26/stream` | Server-Sent Events |
| `/api/lessons/26/ws` | WebSocket events and cancellation |

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
