# Lesson 64: Browser automation with Playwright MCP

Use an explicit external MCP browser service rather than exposing a host shell.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 64
uv run python -m agent_lab.lessons.lesson_64
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 64](http://127.0.0.1:8080/?lesson=64).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `browser`, line 1878). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("browser")
async def browser(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Inspect the browser MCP service's single tool and the origin rule it enforces."""
    from agent_lab.integrations import browser_mcp

    tools = await browser_mcp.mcp.list_tools()
    origin = browser_mcp.teaching_origin()
    candidates = [
        origin + "/?lesson=1",
        origin.replace("127.0.0.1", "localhost"),
        "http://127.0.0.1:9999/",
        "http://127.0.0.1.evil.example/",
        "file:///C:/Windows/win.ini",
    ]
    return {
        "server": browser_mcp.mcp.name,
        "tools": [{"name": item.name, "input_schema": item.inputSchema} for item in tools],
        "teaching_origin": origin,
        "origin_checks": [
            {"url": url, "allowed": browser_mcp.same_origin(url, origin)} for url in candidates
        ],
        "versus_shell": "The agent can only ask for a page at one origin; it cannot run "
        "commands, read files or reach other hosts. A shell tool would allow all of that.",
        "browser_launched": False,
        "start_service": "uv sync --locked --extra browser && uv run playwright install chromium",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 64 --live
```

Suggested prompt:

> Explain how a browser MCP tool differs from arbitrary shell access.

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

An external browser MCP integration is provided separately; it needs its own browser installation and service startup.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/64` | Lesson metadata |
| `POST /api/lessons/64/run` | Collected JSON events |
| `POST /api/lessons/64/stream` | Server-Sent Events |
| `/api/lessons/64/ws` | WebSocket events and cancellation |

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
