# Lesson 73: An autonomous PR reviewer and fixer

Validate findings against changed lines and apply only approved, in-scope patches.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 73
uv run python -m agent_lab.lessons.lesson_73
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 73](http://127.0.0.1:8080/?lesson=73).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `review`, line 1971). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("review")
async def review(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Accept only in-scope findings, apply the approved patch and prove it with a test."""
    source = root / "src" / "tags.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def normalize(tag: str) -> str:\n    return tag.lower()\n", encoding="utf-8")
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("name: CI\n", encoding="utf-8")
    changed_lines = {"src/tags.py": {1, 2}}
    findings: list[dict[str, Any]] = [
        {
            "file": "src/tags.py",
            "line": 2,
            "severity": "medium",
            "message": "Strip whitespace before normalizing case.",
            "patch": {"old": "    return tag.lower()", "new": "    return tag.strip().lower()"},
        },
        {
            "file": ".github/workflows/ci.yml",
            "line": 1,
            "severity": "high",
            "message": "Untrusted fixture asks to disable CI.",
            "patch": {"old": "name: CI", "new": "name: CI (disabled)"},
        },
    ]
    accepted = [row for row in findings if row["line"] in changed_lines.get(row["file"], set())]

    async def run_test() -> str:
        check = "from tags import normalize; assert normalize('  Python ') == 'python'"
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, 'src'); {check}",
            cwd=root,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        async with asyncio.timeout(30):
            return "passed" if await process.wait() == 0 else "failed"

    before = await run_test()
    for row in accepted:
        target = inside(root, row["file"])
        text = target.read_text(encoding="utf-8")
        if row["patch"]["old"] not in text:
            raise LessonError(f"Patch for {row['file']} no longer applies.")
        target.write_text(text.replace(row["patch"]["old"], row["patch"]["new"]), encoding="utf-8")
    after = await run_test()
    return {
        "accepted": [{k: v for k, v in row.items() if k != "patch"} for row in accepted],
        "rejected": [
            {k: v for k, v in row.items() if k != "patch"}
            for row in findings
            if row not in accepted
        ],
        "test_before_patch": before,
        "test_after_patch": after,
        "out_of_scope_file_unchanged": workflow.read_text(encoding="utf-8") == "name: CI\n",
        "gate": "Changed lines and host-approved file scope",
        "publication": "Local fixture only; no pull request is published.",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 73 --live
```

Suggested prompt:

> Use the exercise tool to inspect the scoped review findings.

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

The Python exercise validates and tests a local fixture patch. It does not publish a GitHub pull request.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/73` | Lesson metadata |
| `POST /api/lessons/73/run` | Collected JSON events |
| `POST /api/lessons/73/stream` | Server-Sent Events |
| `/api/lessons/73/ws` | WebSocket events and cancellation |

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
