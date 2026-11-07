# Lesson 38: Prompt suggestions

Generate host-owned next-action suggestions from a validated task state.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 38
uv run python -m agent_lab.lessons.lesson_38
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 38](http://127.0.0.1:8080/?lesson=38).

## The concept in code

```python
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage


async def run_chat(work: Path) -> None:
    options = ClaudeAgentOptions(
        cwd=str(work), tools=[], allowed_tools=[], mcp_servers={},
        setting_sources=[], strict_mcp_config=True,
        extra_args={"prompt-suggestions": None, "no-session-persistence": None},
        max_turns=6, max_budget_usd=0.10,
    )
    async with ClaudeSDKClient(options=options) as client:
        for prompt in ("Suggest a CLI improvement.", "Suggest a next step."):
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, ResultMessage):
                    print(message.session_id, message.subtype)

# The installed Python SDK parser skips raw prompt_suggestion envelopes.
# The lesson's SuggestionTap records those envelopes at the transport boundary.
# A suggestion is displayed separately and enters the chat only via send().
```

extra_args requests the CLI suggestion flag; the transport tap records raw prompt_suggestion envelopes after each result, while the host queue alone owns submitted inputs.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `todos` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1155); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 38 --live
```

Suggested prompt:

> Use the exercise tool and explain the suggested next action.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/suggestions_lab.py](agent_lab/suggestions_lab.py). A transport tap records raw CLI prompt_suggestion envelopes after SDK results while a separate validated host queue owns submitted inputs. The installed Python SDK parser skips this event type; suggestions may be absent even after successful turns. No tools are enabled.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/38` | Lesson metadata |
| `POST /api/lessons/38/run` | Collected JSON events |
| `POST /api/lessons/38/stream` | Server-Sent Events |
| `/api/lessons/38/ws` | WebSocket events and cancellation |

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
