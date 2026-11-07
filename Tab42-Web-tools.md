# Lesson 42: Web tools

Allow WebSearch and WebFetch explicitly and treat retrieved text as untrusted evidence.

This lesson is part of **Tools and extensions**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 42
uv run python -m agent_lab.lessons.lesson_42
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 42](http://127.0.0.1:8080/?lesson=42).

## The concept in code

```python
from urllib.parse import urlsplit

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

FETCH_URL = "https://nodejs.org/en/about"


def allowed_fetch(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == "nodejs.org" and url == FETCH_URL


async def before_tool(data, tool_id, context):
    args = dict(data["tool_input"])
    if data["tool_name"] == "WebSearch":
        args.pop("blocked_domains", None)
        args["allowed_domains"] = ["nodejs.org"]
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": args}}
    if data["tool_name"] == "WebFetch" and not allowed_fetch(args["url"]):
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}}
    return {}


# PostToolUse can replace known instruction-like spans in fetched output.
# Citations are labelled from observed search/fetch history, not from model claims.
options = ClaudeAgentOptions(tools=["WebSearch", "WebFetch"], setting_sources=[],
    hooks={"PreToolUse": [HookMatcher(hooks=[before_tool])]}, max_turns=7)
```

A host hook rewrites search domains and denies unlisted fetch URLs. Separate post-hook and citation helpers inspect delivered page text and recorded source history.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `web` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1403); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 42 --live
```

Suggested prompt:

> Search for the official Python Claude Agent SDK repository and summarize it.

The live profile is `web`. Its tools and configuration are in
[agent_lab/web_tools_lab.py](agent_lab/web_tools_lab.py). Fixed Node.js WebSearch and WebFetch actions use PreToolUse for a host domain rewrite and exact fetch URL allowlist, then PostToolUse for source history and a labelled heuristic redaction example. Live SDK call/result IDs, hook receipts and terminal costs are correlated by lane; cited URL provenance does not prove claim support.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/42` | Lesson metadata |
| `POST /api/lessons/42/run` | Collected JSON events |
| `POST /api/lessons/42/stream` | Server-Sent Events |
| `/api/lessons/42/ws` | WebSocket events and cancellation |

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
