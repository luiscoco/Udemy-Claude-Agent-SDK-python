# Lesson 33: MCP elicitation

Inspect Python SDK elicitation support and validate accept, decline and cancel responses.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 33
uv run python -m agent_lab.lessons.lesson_33
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 33](http://127.0.0.1:8080/?lesson=33).

## The concept in code

```python
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext


async def on_elicit(
    context: RequestContext[ClientSession, Any], params: types.ElicitRequestParams
) -> types.ElicitResult:
    if not isinstance(params, types.ElicitRequestFormParams):
        return types.ElicitResult(action="decline")
    choice = input(f"{params.message} [y]es / [n]o / [c]ancel: ").strip().lower()
    if choice == "c":
        return types.ElicitResult(action="cancel")
    if choice != "y":
        return types.ElicitResult(action="decline")
    return types.ElicitResult(action="accept", content={"confirm": True})


async def main() -> None:
    # The installed Agent SDK has no on_elicitation option, so the MCP client answers.
    server = StdioServerParameters(command="python", args=["drafts_server.py"])
    async with stdio_client(server) as (read, write):
        async with ClientSession(
            read, write, elicitation_callback=on_elicit
        ) as session:
            await session.initialize()
            result = await session.call_tool("delete_draft", {"name": "q3-plan"})
            print(result.content)
```

`on_elicit`, passed as ClientSession(..., `elicitation_callback`=`on_elicit`), turns the server's ElicitRequestParams into an ElicitResult with action accept, decline or cancel.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `elicitation` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 2050); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 33 --live
```

Suggested prompt:

> Explain how an MCP server asks its client for missing information.

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

This lesson inspects elicitation support in the pinned Python SDK and validates responses locally.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/33` | Lesson metadata |
| `POST /api/lessons/33/run` | Collected JSON events |
| `POST /api/lessons/33/stream` | Server-Sent Events |
| `/api/lessons/33/ws` | WebSocket events and cancellation |

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
