# Lesson 39: Project configuration root

Resolve trusted project paths and opt into settings only in that project.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 39
uv run python -m agent_lab.lessons.lesson_39
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 39](http://127.0.0.1:8080/?lesson=39).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `config_root`, line 220). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("config_root")
def config_root(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Resolve project paths safely and load project settings only for allowlisted projects."""
    from claude_agent_sdk import ClaudeAgentOptions

    projects = root / "projects"
    for name, allow in (("course-app", "Read"), ("downloaded-repo", "Bash(*)")):
        settings = projects / name / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"permissions": {"allow": [allow]}}), encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for requested in (
        "course-app",
        "downloaded-repo",
        "course-app/../downloaded-repo",
        "../outside",
        "course-app/.claude",
    ):
        try:
            path = inside(projects, requested)
        except ValueError as exc:
            rows.append({"requested": requested, "resolved": None, "error": str(exc)})
            continue
        trusted = path.name in TRUSTED_PROJECTS and path.is_dir()
        options = ClaudeAgentOptions(cwd=str(path), setting_sources=["project"] if trusted else [])
        rows.append(
            {
                "requested": requested,
                "resolved": path.relative_to(projects).as_posix(),
                "trusted": trusted,
                "setting_sources": options.setting_sources,
            }
        )
    return {
        "trusted_projects": sorted(TRUSTED_PROJECTS),
        "resolutions": rows,
        "untrusted_settings_loaded": any(
            row.get("setting_sources") and row["resolved"] != "course-app" for row in rows
        ),
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 39 --live
```

Suggested prompt:

> Read notes.txt in this isolated project.

The live profile is `read`. Its tools and configuration are in
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
| `GET /api/lessons/39` | Lesson metadata |
| `POST /api/lessons/39/run` | Collected JSON events |
| `POST /api/lessons/39/stream` | Server-Sent Events |
| `/api/lessons/39/ws` | WebSocket events and cancellation |

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
