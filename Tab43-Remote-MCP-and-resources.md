# Lesson 43: Remote MCP and resources

Connect a Python MCP client over streamable HTTP and distinguish resources from tools.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 43
uv run python -m agent_lab.lessons.lesson_43
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 43](http://127.0.0.1:8080/?lesson=43).

## The concept in code

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import AnyUrl
import httpx


async def inspect_owned_server(base: str, token: str) -> None:
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
        async with streamable_http_client(base + "/mcp", http_client=http) as (read, write, session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                status = await session.call_tool("get_status", {"marker": "owned-marker"})
                runbook = await session.read_resource(AnyUrl("docs://runbook"))
                print(session_id(), tools, resources, status, runbook)


def agent_options(base: str, token: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        tools=["ReadMcpResourceTool"],
        allowed_tools=["mcp__lesson_remote__get_status", "ReadMcpResourceTool"],
        mcp_servers={"lesson_remote": {
            "type": "http", "url": base + "/mcp",
            "headers": {"Authorization": "Bearer " + token},
        }},
        strict_mcp_config=True,
        max_turns=5,
        max_budget_usd=0.10,
    )
```

The host discovers metadata, requests a short-lived credential, then uses a real MCP ClientSession. ClaudeSDKClient receives the same owned endpoint and a bounded tool catalog; matching call IDs and server receipts establish the live path.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `remote_mcp` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 970); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 43 --live
```

Suggested prompt:

> Explain MCP resources versus tools.

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

The standalone remote MCP client requires a separately running trusted MCP endpoint. The browser exercise inspects transport types locally.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/43` | Lesson metadata |
| `POST /api/lessons/43/run` | Collected JSON events |
| `POST /api/lessons/43/stream` | Server-Sent Events |
| `/api/lessons/43/ws` | WebSocket events and cancellation |

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
