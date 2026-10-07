# Lesson 75: Capstone: an autonomous engineering team

Validate task ownership, execute dependency waves and enforce a host release gate.

This lesson is part of **Multi-agent systems**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 75
uv run python -m agent_lab.lessons.lesson_75
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 75](http://127.0.0.1:8080/?lesson=75).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `team`, line 908). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("team")
async def team(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    plan = Plan(
        tasks=[
            TaskSpec(id="T1", files=["src/tags.py"]),
            TaskSpec(id="T2", files=["src/search.py"], depends_on=["T1"]),
            TaskSpec(id="T3", files=["src/report.py"], depends_on=["T1"]),
        ]
    )
    sources = {
        "T1": "def normalize_tag(value: str) -> str:\n    return value.strip().lower()\n",
        "T2": "from tags import normalize_tag\ndef find_by_tag(notes, tag):\n    return [n for n in notes if normalize_tag(tag) in [normalize_tag(t) for t in n['tags']]]\n",
        "T3": "from tags import normalize_tag\ndef tag_counts(notes):\n    counts = {}\n    for note in notes:\n        for tag in set(map(normalize_tag, note['tags'])):\n            counts[tag] = counts.get(tag, 0) + 1\n    return counts\n",
    }
    board = Board({"T1", "T2", "T3", "lead"})
    journal = Journal(root / "team.jsonl")

    async def developer(task: TaskSpec):
        path = inside(root, task.files[0])
        path.parent.mkdir(exist_ok=True)
        code = sources[task.id]
        compile(code, str(path), "exec")
        path.write_text(code, encoding="utf-8")
        board.send(task.id, "lead", f"Compiled {task.files[0]}")
        journal.append({"event": "completed", "step": task.id, "file": task.files[0]})
        return {"file": task.files[0], "compiled": True}

    results = await execute_plan(plan, developer)
    probe = "from tags import normalize_tag\nfrom search import find_by_tag\nfrom report import tag_counts\nnotes=[{'tags':[' Python ','python','AI']}]\nassert normalize_tag(' PYTHON ') == 'python'\nassert len(find_by_tag(notes, 'python')) == 1\nassert tag_counts(notes) == {'python':1, 'ai':1}\nprint('3 acceptance checks passed')\n"
    (root / "src" / "acceptance.py").write_text(probe, encoding="utf-8")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        "import sys; sys.path.insert(0, '.'); exec(open('acceptance.py').read())",
        cwd=root / "src",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(15):
            stdout, _ = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return {
        "plan": plan.model_dump(),
        "waves": plan.waves(),
        "workers": "scripted Python fixtures",
        "results": results,
        "messages": board.messages,
        "journal": journal.replay(),
        "release_gate": process.returncode == 0,
        "acceptance": stdout.decode().strip(),
        "published": False,
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 75 --live
```

Suggested prompt:

> Implement the tag helpers with the engineering team and verify the host release gate.

The live profile is `engineering_team`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

Offline mode uses scripted workers. Live mode runs a lead, parallel developers and reviewer through the SDK; the host validates structured source proposals, runs acceptance checks and decides the release gate. This bounded Python fixture does not push a GitHub PR or implement the original full worktree merge and recovery workflow.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/75` | Lesson metadata |
| `POST /api/lessons/75/run` | Collected JSON events |
| `POST /api/lessons/75/stream` | Server-Sent Events |
| `/api/lessons/75/ws` | WebSocket events and cancellation |

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
