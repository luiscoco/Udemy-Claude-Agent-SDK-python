# Lesson 55: Upgrading the SDK safely

Check installed public interfaces and pin Python dependencies reproducibly.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 55
uv run python -m agent_lab.lessons.lesson_55
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 55](http://127.0.0.1:8080/?lesson=55).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `upgrade`, line 1843). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("upgrade")
def upgrade(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Compare the declared pin, the lockfile and the installed SDK, then gate on interfaces."""
    import tomllib

    import claude_agent_sdk as sdk

    from agent_lab.config import ROOT

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pin = next(
        item for item in project["project"]["dependencies"] if item.startswith("claude-agent-sdk")
    )
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(item["version"] for item in lock["package"] if item["name"] == "claude-agent-sdk")
    installed = importlib.metadata.version("claude-agent-sdk")
    required = [
        "query",
        "tool",
        "create_sdk_mcp_server",
        "ClaudeAgentOptions",
        "ClaudeSDKClient",
        "HookMatcher",
        "PermissionResultAllow",
        "PermissionResultDeny",
        "Transport",
        "list_sessions",
    ]
    methods = ["connect", "query", "receive_response", "interrupt", "set_model", "disconnect"]
    missing = [name for name in required if not hasattr(sdk, name)]
    missing += [
        f"ClaudeSDKClient.{name}" for name in methods if not hasattr(sdk.ClaudeSDKClient, name)
    ]
    # A candidate release that dropped one method the app uses must be blocked.
    candidate_missing = ["ClaudeSDKClient.interrupt"]
    return {
        "declared_pin": pin,
        "locked_version": locked,
        "installed_version": installed,
        "pin_lock_install_match": pin.endswith(f"=={locked}") and locked == installed,
        "required_interfaces": len(required) + len(methods),
        "missing_interfaces": missing,
        "current_gate": "pass" if not missing else "blocked",
        "simulated_candidate": {"missing": candidate_missing, "gate": "blocked"},
        "reproducible_install": "uv sync --locked",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 55 --live
```

Suggested prompt:

> Use the exercise tool and explain the SDK compatibility report.

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
| `GET /api/lessons/55` | Lesson metadata |
| `POST /api/lessons/55/run` | Collected JSON events |
| `POST /api/lessons/55/stream` | Server-Sent Events |
| `/api/lessons/55/ws` | WebSocket events and cancellation |

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
