# Lesson 32: Plan mode

Validate a plan separately from executing it; use the SDK plan permission mode.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 32
uv run python -m agent_lab.lessons.lesson_32
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 32](http://127.0.0.1:8080/?lesson=32).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `plan_mode`, line 1278). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("plan")
async def plan_mode(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Plan in plan mode, validate the plan, and only execute after approval."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    from agent_lab.scripted_cli import ScriptedCLI

    proposal = (
        '{"tasks": [{"id": "T1", "files": ["src/tags.py"]}, '
        '{"id": "T2", "files": ["src/search.py"], "depends_on": ["T1"]}, '
        '{"id": "T3", "files": ["src/report.py"], "depends_on": ["T1"]}]}'
    )
    cli = ScriptedCLI([[proposal]])
    started: list[str] = []
    timeline: list[dict[str, Any]] = []

    async def worker(task: TaskSpec) -> dict[str, Any]:
        started.append(task.id)
        return {"owned_files": task.files, "verified": True}

    async with asyncio.timeout(20):
        async with ClaudeSDKClient(ClaudeAgentOptions(), transport=cli) as client:
            await client.set_permission_mode("plan")
            timeline.append({"step": "enter plan mode", "cli_mode": cli.permission_mode})
            await client.query("Plan the tag normalization change. Do not edit files.")
            reply = await scripted_turn(client)
            plan = Plan.model_validate_json(reply["text"])
            timeline.append(
                {
                    "step": "plan validated",
                    "waves": plan.waves(),
                    "workers_started": len(started),
                }
            )
            timeline.append({"step": "human approves the plan", "approved": True})
            await client.set_permission_mode("default")
            timeline.append({"step": "leave plan mode", "cli_mode": cli.permission_mode})
    results = await execute_plan(plan, worker)
    timeline.append({"step": "execute", "workers_started": len(started)})
    return {
        "timeline": timeline,
        "workers_before_approval": timeline[1]["workers_started"],
        "results": results,
        "live_option": 'ClaudeAgentOptions(permission_mode="plan")',
        "source": "real ClaudeSDKClient talking to a scripted CLI fixture",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 32 --live
```

Suggested prompt:

> Read notes.txt, then plan how to improve it. Do not change any files.

The live profile is `plan`. Its tools and configuration are in
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
| `GET /api/lessons/32` | Lesson metadata |
| `POST /api/lessons/32/run` | Collected JSON events |
| `POST /api/lessons/32/stream` | Server-Sent Events |
| `/api/lessons/32/ws` | WebSocket events and cancellation |

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
