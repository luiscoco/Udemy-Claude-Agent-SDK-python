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
from claude_agent_sdk import ClaudeAgentOptions


def guarded_fork(source_session: str, retained_entry: str, dropped_turn: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        resume=source_session,
        fork_session=True,
        resume_session_at=retained_entry,
        resume_drops_turn=dropped_turn,
        tools=[], allowed_tools=[], setting_sources=[],
        max_turns=1, max_budget_usd=0.05,
    )


def recovery_fork(source_session: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        resume=source_session, fork_session=True,
        resume_session_at=None, resume_drops_turn=None,
        tools=[], allowed_tools=[], setting_sources=[],
        max_turns=1, max_budget_usd=0.05,
    )

# Parse raw JSONL UUID ancestry before choosing retained_entry and dropped_turn.
# If connect raises, verify the real CLI result frame in ResultError.data; exception text alone is insufficient.
```

resume_session_at identifies the retained boundary and resume_drops_turn names the discarded user turn. A recovery fork clears both fields. The host verifies the actual persisted fork and source hash rather than using assistant recall.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `resume` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 2056); the Python source tab shows it below the concept code. Host contracts
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
[agent_lab/drops_lab.py](agent_lab/drops_lab.py). The host builds four persisted SDK turns with fixed UUIDs, an owned pause tool and a queued command attachment, then parses the active JSONL ancestry. Exact last-turn and unsafe queued-turn forks use resume-session-at and resume-drops-turn; a fresh recovery fork is optional. Prepared refusal results are authored fixtures. The live unsafe CLI result is parsed from the SDK's structured ResultError.data when connect raises before yielding; exception text alone does not count.

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
