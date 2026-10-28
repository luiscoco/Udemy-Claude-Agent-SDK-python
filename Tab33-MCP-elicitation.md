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

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `elicitation`, line 1774). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("elicitation")
async def elicitation(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """An MCP tool asks the user for structured input; each response type changes the outcome."""
    import claude_agent_sdk as sdk
    from mcp import types
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session
    from pydantic import BaseModel

    class Confirmation(BaseModel):
        confirm: bool
        reason: str = ""

    def build() -> FastMCP:
        server = FastMCP("drafts")

        @server.tool()
        async def delete_draft(name: str, ctx: Context) -> str:
            """Delete a draft after the user confirms."""
            answer = await ctx.elicit(f"Delete the draft {name}?", schema=Confirmation)
            if answer.action == "accept":
                return f"Deleted {name}." if answer.data.confirm else "Kept: not confirmed."
            return f"Not deleted: the user chose {answer.action}."

        return server

    responses: dict[str, types.ElicitResult] = {
        "accept": types.ElicitResult(action="accept", content={"confirm": True}),
        "decline": types.ElicitResult(action="decline"),
        "cancel": types.ElicitResult(action="cancel"),
        "accept with invalid data": types.ElicitResult(
            action="accept", content={"confirm": "maybe"}
        ),
    }
    outcomes = []
    for label, response in responses.items():
        prompts: list[str] = []

        async def answer(
            context: Any,
            params: Any,
            response: types.ElicitResult = response,
            prompts: list[str] = prompts,
        ) -> types.ElicitResult:
            prompts.append(params.message)
            return response

        async with asyncio.timeout(20):
            async with create_connected_server_and_client_session(
                build(), elicitation_callback=answer
            ) as session:
                result = await session.call_tool("delete_draft", {"name": "q3-plan"})
        outcomes.append(
            {
                "response": label,
                "asked": prompts[0] if prompts else "",
                "is_error": result.isError,
                "tool_result": tool_text(result)[:160],
            }
        )
    return {
        "outcomes": outcomes,
        "python_sdk_on_elicitation": "on_elicitation"
        in {field.name for field in dataclasses.fields(sdk.ClaudeAgentOptions)},
        "note": "MCP elicitation runs between an MCP client and server. This installed Python "
        "Agent SDK does not expose an on_elicitation option, so the lab uses the MCP client.",
    }
```

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
