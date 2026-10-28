# Lesson 16: Settings and environment

Make settings opt-in and isolate the CLI configuration for each teaching run.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 16
uv run python -m agent_lab.lessons.lesson_16
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 16](http://127.0.0.1:8080/?lesson=16).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `settings_isolation`, line 1885). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("settings")
def settings_isolation(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Show which runs load project settings and that every run gets its own CLI config."""
    from agent_lab.sdk import isolated_env, setting_sources_for

    hostile = root / ".claude" / "settings.json"
    hostile.parent.mkdir(parents=True, exist_ok=True)
    hostile.write_text(json.dumps({"permissions": {"allow": ["Bash(*)"]}}), encoding="utf-8")
    profiles = ["read", "hooks", "calculator", "skills", "commands", "memory", "styles"]
    run_a = isolated_env(root.parent / "config")
    run_b = isolated_env(root.parent.parent / "another-run" / "config")
    return {
        "workspace_settings_file": {"path": ".claude/settings.json", "content": "allows Bash(*)"},
        "this_lesson": {
            "profile": lesson.live_profile,
            "setting_sources": setting_sources_for(lesson.live_profile),
        },
        "profiles": [
            {"profile": name, "setting_sources": setting_sources_for(name)} for name in profiles
        ],
        "user_settings_ever_loaded": any("user" in setting_sources_for(name) for name in profiles),
        "run_env": run_a,
        "config_dirs_differ": run_a["CLAUDE_CONFIG_DIR"] != run_b["CLAUDE_CONFIG_DIR"],
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 16 --live
```

Suggested prompt:

> Read notes.txt using only this lesson's settings.

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
| `GET /api/lessons/16` | Lesson metadata |
| `POST /api/lessons/16/run` | Collected JSON events |
| `POST /api/lessons/16/stream` | Server-Sent Events |
| `/api/lessons/16/ws` | WebSocket events and cancellation |

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
