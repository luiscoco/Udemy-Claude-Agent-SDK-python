# Lesson 10: Structured output and interrupt

Validate structured answers with Pydantic and use an interactive client for control.

This lesson is part of **SDK fundamentals**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 10
uv run python -m agent_lab.lessons.lesson_10
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 10](http://127.0.0.1:8080/?lesson=10).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `structured`, line 547). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("structured")
async def structured(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Validate a structured answer, then interrupt a streaming turn with the real client."""
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient

    from agent_lab.scripted_cli import ScriptedCLI

    parsed = Summary.model_validate(
        {"summary": "Host-validated example", "next_steps": ["Run the Python lesson"]}
    )
    try:
        Summary.model_validate({"summary": "", "next_steps": []})
        invalid = "accepted"
    except ValidationError as exc:
        invalid = f"rejected: {exc.error_count()} validation errors"
    cli = ScriptedCLI([[f"step {n} " for n in range(1, 7)]], chunk_delay=0.05)
    received, subtype = 0, None
    async with asyncio.timeout(20):
        async with ClaudeSDKClient(ClaudeAgentOptions(), transport=cli) as client:
            await client.query("Count to six slowly.")
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    received += 1
                    if received == 2:
                        await client.interrupt()
                else:
                    subtype = getattr(message, "subtype", None)
    return {
        "schema": Summary.model_json_schema(),
        "validated": parsed.model_dump(),
        "invalid_answer": invalid,
        "interrupt": {
            "chunks_planned": 6,
            "chunks_received": received,
            "result_subtype": subtype,
            "control_requests": [
                m["request"]["subtype"] for m in cli.received if m["type"] == "control_request"
            ],
        },
        "source": "real ClaudeSDKClient talking to a scripted CLI fixture",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 10 --live
```

Suggested prompt:

> Return a short summary and two next steps about learning Python agents.

The live profile is `structured`. Its tools and configuration are in
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
| `GET /api/lessons/10` | Lesson metadata |
| `POST /api/lessons/10/run` | Collected JSON events |
| `POST /api/lessons/10/stream` | Server-Sent Events |
| `/api/lessons/10/ws` | WebSocket events and cancellation |

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
