# Lesson 48: Security hardening

Combine input validation, path boundaries, tool restrictions and secret redaction.

This lesson is part of **Permissions and security**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 48
uv run python -m agent_lab.lessons.lesson_48
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 48](http://127.0.0.1:8080/?lesson=48).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `permission_cases`, line 168). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("permissions", "security", "redteam")
def permission_cases(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    cases = [
        ("normal read", "Read", {"file_path": "notes.txt"}, True),
        ("path traversal", "Read", {"file_path": "../outside.txt"}, False),
        ("secret read", "Read", {"file_path": ".env"}, False),
        ("shell injection", "Bash", {"command": "echo preapproved"}, False),
        ("unapproved write", "Write", {"file_path": "notes.txt"}, False),
    ]
    rows: list[dict[str, Any]] = []
    for label, tool, arguments, expected in cases:
        allowed, reason = decide(root, tool, arguments)
        rows.append(
            {
                "case": label,
                "tool": tool,
                "allowed": allowed,
                "expected": expected,
                "passed": allowed == expected,
                "reason": reason,
            }
        )
    return {
        "decisions": rows,
        "pass_rate": sum(row["passed"] for row in rows) / len(rows),
        "redacted": redact({"api_key": "fixture-only", "text": "Bearer fake-fixture-token"}),
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 48 --live
```

Suggested prompt:

> Use the exercise tool to inspect the policy decisions.

The live profile is `exercise`. Its tools and configuration are in
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
| `GET /api/lessons/48` | Lesson metadata |
| `POST /api/lessons/48/run` | Collected JSON events |
| `POST /api/lessons/48/stream` | Server-Sent Events |
| `/api/lessons/48/ws` | WebSocket events and cancellation |

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
