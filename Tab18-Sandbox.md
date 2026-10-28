# Lesson 18: Sandbox

Distinguish a path policy from OS process isolation and inspect SDK sandbox settings.

This lesson is part of **Permissions and security**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 18
uv run python -m agent_lab.lessons.lesson_18
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 18](http://127.0.0.1:8080/?lesson=18).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `sandbox`, line 589). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("sandbox")
async def sandbox(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Show that a path policy guards tool calls, not the processes they start."""
    from claude_agent_sdk.types import SandboxSettings

    outside = root.parent / "outside-secret.txt"
    outside.write_text("host data outside the lesson workspace", encoding="utf-8")
    try:
        allowed, reason = decide(root, "Read", {"file_path": "../outside-secret.txt"})
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            "print(open('../outside-secret.txt').read())",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        async with asyncio.timeout(30):
            stdout, _ = await process.communicate()
    finally:
        outside.unlink(missing_ok=True)
    return {
        "read_tool_through_policy": {"allowed": allowed, "reason": reason},
        "child_process_read_outside": process.returncode == 0 and bool(stdout.strip()),
        "lesson": "The path policy stopped the Read tool, but a process it would have allowed "
        "to run reads the same file. Only OS isolation confines processes.",
        "sdk_sandbox_settings": sorted(SandboxSettings.__annotations__),
        "lab_choice": "Bash is never enabled, so no model-started process exists to confine.",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 18 --live
```

Suggested prompt:

> Explain why a path allowlist alone is not an operating-system sandbox.

The live profile is `query`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

The local path policy is not OS sandboxing. Configure a supported OS sandbox independently before running untrusted shell code.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/18` | Lesson metadata |
| `POST /api/lessons/18/run` | Collected JSON events |
| `POST /api/lessons/18/stream` | Server-Sent Events |
| `/api/lessons/18/ws` | WebSocket events and cancellation |

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
