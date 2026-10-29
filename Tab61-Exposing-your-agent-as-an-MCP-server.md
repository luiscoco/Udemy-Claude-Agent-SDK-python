# Lesson 61: Exposing an agent as an MCP server

Expose a typed Python MCP tool whose async handler invokes the official Agent SDK.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 61
uv run python -m agent_lab.lessons.lesson_61
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 61](http://127.0.0.1:8080/?lesson=61).

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from mcp.server.fastmcp import FastMCP

server = FastMCP("python-agent")


@server.tool()
async def explain_python_agent(prompt: str) -> dict[str, object]:
    """Ask a bounded, tool-free teaching agent one question."""
    # The outer MCP client only chooses the prompt; the inner run's limits are fixed here.
    options = ClaudeAgentOptions(
        tools=[],
        setting_sources=[],
        max_turns=1,
        max_budget_usd=0.05,
        permission_mode="dontAsk",
    )
    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result = message
    if result is None or result.is_error:
        raise RuntimeError("The inner agent run did not finish.")
    return {"answer": result.result, "cost_usd": result.total_cost_usd}
```

`@server.tool()` makes `explain_python_agent` a typed MCP tool, and its handler builds fixed `ClaudeAgentOptions` (no tools, `max_turns=1`, `max_budget_usd=0.05`) before calling `query()`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `agent_mcp` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 954); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 61 --live
```

Suggested prompt:

> Explain the boundary between the outer MCP client and the inner agent.

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

The standalone agent MCP server invokes the SDK only when explicitly started with live access enabled.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/61` | Lesson metadata |
| `POST /api/lessons/61/run` | Collected JSON events |
| `POST /api/lessons/61/stream` | Server-Sent Events |
| `/api/lessons/61/ws` | WebSocket events and cancellation |

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
