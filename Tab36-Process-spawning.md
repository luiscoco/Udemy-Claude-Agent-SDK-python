# Lesson 36: Process spawning

Launch Python with an argument list, capture output and bound process lifetime.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 36
uv run python -m agent_lab.lessons.lesson_36
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 36](http://127.0.0.1:8080/?lesson=36).

## The concept in code

```python
import asyncio
from pathlib import Path

from agent_lab.process_spawning_lab import FrameTap, probe_child

async def inspect(root: Path) -> None:
    child = await probe_child(root, 'success', 'machine-a')
    print(child['frames'], child['bytes_forwarded_unchanged'])

# The live lab also runs a separate real SDK CLI turn.
# This installed Python SDK has no public custom-spawner option.
asyncio.run(inspect(Path.cwd()))
```

FrameTap buffers split JSONL bytes; probe_child launches fixed argv and reaps interrupted children; spawn_report requires separate host and SDK success.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `spawn` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1383); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 36 --live
```

Suggested prompt:

> Use the exercise tool and explain shell-free spawning.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/process_spawning_lab.py](agent_lab/process_spawning_lab.py). The host launches a fixed Python child with explicit argv, local cwd, separate pipes, a JSONL byte tap and bounded cleanup. A separate SDK CLI turn must return a matching successful terminal. The installed Python SDK has no public custom-spawner option; this host child does not carry SDK protocol.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/36` | Lesson metadata |
| `POST /api/lessons/36/run` | Collected JSON events |
| `POST /api/lessons/36/stream` | Server-Sent Events |
| `/api/lessons/36/ws` | WebSocket events and cancellation |

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
