# Lesson 66: Real-time frontends over WebSocket

Use a typed WebSocket protocol and cancel the run when the connection closes.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 66
uv run python -m agent_lab.lessons.lesson_66
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 66](http://127.0.0.1:8080/?lesson=66).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `websocket`, line 1452). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("websocket")
async def websocket(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Serve the real WebSocket endpoint on loopback and drive it as a browser would."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    from agent_lab.api import create_app
    from agent_lab.config import Settings
    from agent_lab.runtime import RunService

    inner = RunService(Settings(enable_live=False, data_dir=root / "ws-runs"))
    app = create_app(inner, with_ui=False)
    async with EmbeddedServer(app).running() as base:
        endpoint = base.replace("http", "ws") + "/api/lessons/5/ws"
        async with asyncio.timeout(30):
            async with connect(endpoint) as socket:
                await socket.send(json.dumps({"mode": "offline"}))
                kinds = []
                async for raw in socket:
                    event = json.loads(raw)
                    kinds.append(event["kind"])
                    if event["kind"] == "done":
                        final_status = event["data"]["status"]
                        break
            async with connect(endpoint) as socket:
                await socket.send(json.dumps({"mode": "offline", "cwd": "outside"}))
                try:
                    await socket.recv()
                    invalid_close = None
                except ConnectionClosed as exc:
                    invalid_close = exc.rcvd.code if exc.rcvd else None
            async with connect(base.replace("http", "ws") + "/api/lessons/57/ws") as socket:
                await socket.send(json.dumps({"mode": "offline"}))
                await socket.recv()  # started, then the browser goes away mid-run
            for _ in range(250):
                if not inner.active:
                    break
                await asyncio.sleep(0.02)
    await inner.close()
    return {
        "endpoint": "/api/lessons/{lesson_id}/ws",
        "server_events": kinds,
        "final_status": final_status,
        "invalid_request_close_code": invalid_close,
        "owned_runs_after_disconnect": len(inner.active),
        "disconnect": "Closing the socket cancels and awaits the owned run.",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 66 --live
```

Suggested prompt:

> Explain why a disconnected browser should cancel its agent run.

The live profile is `query`. Its tools and configuration are in
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
| `GET /api/lessons/66` | Lesson metadata |
| `POST /api/lessons/66/run` | Collected JSON events |
| `POST /api/lessons/66/stream` | Server-Sent Events |
| `/api/lessons/66/ws` | WebSocket events and cancellation |

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
