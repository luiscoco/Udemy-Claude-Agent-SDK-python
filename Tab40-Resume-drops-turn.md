# Lesson 40: Resume and conversation history

Explain Python resume options and avoid treating a host transcript as SDK state.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 40
uv run python -m agent_lab.lessons.lesson_40
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 40](http://127.0.0.1:8080/?lesson=40).

## The concept in code

```python
import os

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, list_sessions, query


async def ask(prompt: str, options: ClaudeAgentOptions) -> str:
    session_id = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            session_id = message.session_id
    return session_id


async def main() -> None:
    # The CLI and list_sessions() must both see the same config dir.
    os.environ["CLAUDE_CONFIG_DIR"] = os.path.abspath("claude-config")
    first = await ask("Remember the code word CONTEXT.", ClaudeAgentOptions())
    variants = {
        "resume": ClaudeAgentOptions(resume=first),
        "fork": ClaudeAgentOptions(resume=first, fork_session=True),
        "continue": ClaudeAgentOptions(continue_conversation=True),
    }
    for name, options in variants.items():
        print(name, await ask("What is the code word?", options))
    for info in list_sessions():
        print(info.session_id, info.summary)
```

ask() captures ResultMessage.session_id, then ClaudeAgentOptions(resume=first), resume plus `fork_session`=True, and `continue_conversation`=True reopen it from one `CLAUDE_CONFIG_DIR`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `resume` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 2052); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 40 --live
```

Suggested prompt:

> Remember the code word CONTEXT.

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

The interactive lab preserves context within one run. Cross-run SDK resume requires a persistent configuration directory and a saved session id.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/40` | Lesson metadata |
| `POST /api/lessons/40/run` | Collected JSON events |
| `POST /api/lessons/40/stream` | Server-Sent Events |
| `/api/lessons/40/ws` | WebSocket events and cancellation |

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
