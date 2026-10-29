# Lesson 57: Parallel workers in Git worktrees

Create isolated Git worktrees and serialize operations on shared repository state.

This lesson is part of **Multi-agent systems**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 57
uv run python -m agent_lab.lessons.lesson_57
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 57](http://127.0.0.1:8080/?lesson=57).

## The concept in code

```python
import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

GIT_LOCK = asyncio.Lock()


async def git(repo: Path, *args: str) -> None:
    async with GIT_LOCK:  # one operation on shared repository state at a time
        process = await asyncio.create_subprocess_exec("git", "-C", str(repo), *args)
        async with asyncio.timeout(15):
            if await process.wait() != 0:
                raise RuntimeError(f"git {' '.join(args)} failed")


async def worker(repo: Path, task_id: str, task: str) -> str | None:
    tree = repo.parent / f"{repo.name}-{task_id}"
    await git(repo, "worktree", "add", "-b", f"agent/{task_id}", str(tree))
    options = ClaudeAgentOptions(
        cwd=tree, allowed_tools=["Read", "Edit", "Grep"], max_turns=8
    )
    async for message in query(prompt=task, options=options):
        if isinstance(message, ResultMessage):
            return message.result
    return None


async def main(repo: Path) -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(worker(repo, "T1", "Add type hints to src/tags.py."))
        group.create_task(worker(repo, "T2", "Add docstrings to src/search.py."))
```

Each worker runs git worktree add on its own branch through the `GIT_LOCK`-guarded git() helper, then points ClaudeAgentOptions(cwd=tree) at that worktree so parallel agents never share a working copy.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `worktrees` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1539); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 57 --live
```

Suggested prompt:

> Use the exercise tool to inspect the worktree paths.

The live profile is `exercise`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

The worktree exercise needs Git and creates a disposable local repository. No remote is contacted or pushed.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/57` | Lesson metadata |
| `POST /api/lessons/57/run` | Collected JSON events |
| `POST /api/lessons/57/stream` | Server-Sent Events |
| `/api/lessons/57/ws` | WebSocket events and cancellation |

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
