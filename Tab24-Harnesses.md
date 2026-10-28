# Lesson 24: Harnesses

Separate model proposals from deterministic host validation and execution.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 24
uv run python -m agent_lab.lessons.lesson_24
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 24](http://127.0.0.1:8080/?lesson=24).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `harness`, line 1236). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("harness")
async def harness(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Treat model output as a proposal: validate it, and execute only what passes."""
    # Fixtures standing in for model replies, from good to unusable.
    proposals = {
        "valid plan": '{"tasks": [{"id": "T1", "files": ["src/tags.py"]}, '
        '{"id": "T2", "files": ["src/search.py"], "depends_on": ["T1"]}]}',
        "two owners for one file": '{"tasks": [{"id": "T1", "files": ["src/tags.py"]}, '
        '{"id": "T2", "files": ["src/tags.py"]}]}',
        "dependency cycle": '{"tasks": [{"id": "T1", "files": ["src/a.py"], "depends_on": ["T2"]}, '
        '{"id": "T2", "files": ["src/b.py"], "depends_on": ["T1"]}]}',
        "file outside src": '{"tasks": [{"id": "T1", "files": [".github/workflows/ci.yml"]}]}',
        "prose instead of JSON": "Sure! First T1, then T2.",
    }
    reviewed = []
    accepted: Plan | None = None
    for label, text in proposals.items():
        try:
            plan = Plan.model_validate_json(text)
        except ValidationError as exc:
            problem = exc.errors()[0]["msg"].removeprefix("Value error, ")
            reviewed.append({"proposal": label, "accepted": False, "problem": problem})
            continue
        reviewed.append({"proposal": label, "accepted": True, "problem": ""})
        accepted = accepted or plan
    started: list[str] = []

    async def worker(task: TaskSpec) -> dict[str, Any]:
        started.append(task.id)
        return {"owned_files": task.files, "verified": True, "source": "scripted host worker"}

    assert accepted is not None
    results = await execute_plan(accepted, worker)
    return {
        "proposals": reviewed,
        "executed": [row["proposal"] for row in reviewed if row["accepted"]],
        "waves": accepted.waves(),
        "workers_started": started,
        "results": results,
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 24 --live
```

Suggested prompt:

> Use the exercise tool to inspect the harness result, then explain its gate.

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
| `GET /api/lessons/24` | Lesson metadata |
| `POST /api/lessons/24/run` | Collected JSON events |
| `POST /api/lessons/24/stream` | Server-Sent Events |
| `/api/lessons/24/ws` | WebSocket events and cancellation |

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
