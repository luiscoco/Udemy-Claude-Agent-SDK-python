# Lesson 8: Subagents

Define a read-only reviewer with AgentDefinition and inspect its tool scope.

This lesson is part of **Multi-agent systems**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 8
uv run python -m agent_lab.lessons.lesson_08
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 8](http://127.0.0.1:8080/?lesson=8).

## The concept in code

```python
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ResultMessage, query

reviewer = AgentDefinition(
    description="Reviews lesson notes without editing them.",
    prompt="Read notes.txt and suggest one improvement. Never modify files.",
    tools=["Read", "Glob", "Grep"],
)


async def main() -> None:
    options = ClaudeAgentOptions(
        agents={"reviewer": reviewer},
        # The main agent needs the Agent tool to delegate at all.
        tools=["Agent", "Read", "Glob", "Grep"],
        allowed_tools=["Agent", "Read", "Glob", "Grep"],
        max_turns=6,
    )
    prompt = "Ask the reviewer subagent to inspect notes.txt."
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            print(message.result)
```

`AgentDefinition(description, prompt, tools=[...])` defines the reviewer, `agents={"reviewer": reviewer}` registers it, and the `Agent` tool in the main catalog lets the main agent delegate.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `subagents` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 513); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 8 --live
```

Suggested prompt:

> Ask the reviewer subagent to inspect notes.txt.

The live profile is `subagents`. Its tools and configuration are in
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
| `GET /api/lessons/8` | Lesson metadata |
| `POST /api/lessons/8/run` | Collected JSON events |
| `POST /api/lessons/8/stream` | Server-Sent Events |
| `/api/lessons/8/ws` | WebSocket events and cancellation |

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
