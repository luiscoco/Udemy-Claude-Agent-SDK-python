# Lesson 20: Hooks in depth

Evaluate pre-tool policies, post-tool audit records and denial reasons.

This lesson is part of **Configuration and hooks**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 20
uv run python -m agent_lab.lessons.lesson_20
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 20](http://127.0.0.1:8080/?lesson=20).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `hook_pipeline`, line 258). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("hook_pipeline")
async def hook_pipeline(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Dispatch matched hooks around a host tool loop, as the CLI does for each tool call."""
    from claude_agent_sdk import HookContext, HookInput, HookJSONOutput, HookMatcher

    timeline: list[dict[str, Any]] = []

    async def audit(kind: str, data: dict[str, Any]) -> None:
        step = {"hook": "PreToolUse hook", "audit": "PostToolUse audit"}[kind]
        timeline.append({"step": step, **data})

    config = lesson_hooks(lambda name, arguments: decide(root, name, arguments), audit)

    async def write_alert(
        arguments: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        timeline.append({"step": "write alert hook", "tool": arguments.get("tool_name")})
        return {}

    # A matcher-scoped hook: it would only ever see Write or Edit results.
    config["PostToolUse"].append(HookMatcher(matcher="Write|Edit", hooks=[write_alert]))
    for number, (label, tool, arguments) in enumerate(TOOL_CALLS, 1):
        tool_use_id = f"toolu_{number}"
        timeline.append({"step": "tool requested", "case": label, "tool": tool})
        allowed = True
        for matcher in config["PreToolUse"]:
            if matches(matcher.matcher, tool):
                for callback in matcher.hooks:
                    output = await call_hook(
                        callback, hook_input("PreToolUse", tool, arguments), tool_use_id
                    )
                    allowed &= output["hookSpecificOutput"]["permissionDecision"] == "allow"
        if not allowed:
            timeline.append({"step": "tool blocked", "tool": tool})
            continue
        # Only allowed reads reach this point; the host performs the read itself.
        result = inside(root, arguments["file_path"]).read_text(encoding="utf-8")
        timeline.append({"step": "tool executed", "tool": tool, "characters": len(result)})
        for matcher in config["PostToolUse"]:
            if matches(matcher.matcher, tool):
                for callback in matcher.hooks:
                    await call_hook(
                        callback,
                        hook_input("PostToolUse", tool, arguments, tool_response=result),
                        tool_use_id,
                    )
    executed = [row for row in timeline if row["step"] == "tool executed"]
    audited = [row for row in timeline if row["step"] == "PostToolUse audit"]
    return {
        "matchers": {
            event: [matcher.matcher or "*" for matcher in matchers]
            for event, matchers in config.items()
        },
        "timeline": timeline,
        "executed": len(executed),
        "audited": len(audited),
        "every_execution_audited": len(executed) == len(audited),
        "write_alerts": sum(row["step"] == "write alert hook" for row in timeline),
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 20 --live
```

Suggested prompt:

> Read notes.txt, then explain the tool result.

The live profile is `hooks`. Its tools and configuration are in
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
| `GET /api/lessons/20` | Lesson metadata |
| `POST /api/lessons/20/run` | Collected JSON events |
| `POST /api/lessons/20/stream` | Server-Sent Events |
| `/api/lessons/20/ws` | WebSocket events and cancellation |

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
