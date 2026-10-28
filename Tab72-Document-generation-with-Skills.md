# Lesson 72: Document generation with Skills

Generate a Word document with python-docx from a validated incident specification.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 72
uv run python -m agent_lab.lessons.lesson_72
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 72](http://127.0.0.1:8080/?lesson=72).

## The concept in code

```python
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ToolPermissionContext
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

BUILD = "python .claude/skills/atmira-docx/scripts/build_docx.py incident.spec.json out/incident.docx"


async def gate(
    name: str, args: dict[str, Any], ctx: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    if name in {"Skill", "Read"} or (name == "Bash" and args.get("command") == BUILD):
        return PermissionResultAllow()
    if (
        name == "Write"
        and Path(str(args.get("file_path", ""))).name == "incident.spec.json"
    ):
        return PermissionResultAllow()
    return PermissionResultDeny(
        message="Only the skill's spec file and exact build command are allowed."
    )


async def main(work: Path) -> None:
    options = ClaudeAgentOptions(
        cwd=str(
            work
        ),  # holds .claude/skills/atmira-docx/ (SKILL.md, reference/, scripts/)
        skills=["atmira-docx"],
        tools=["Skill", "Read", "Write", "Bash"],
        can_use_tool=gate,
        max_turns=12,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            "Turn input/incident.md into a post-incident review Word document."
        )
        async for message in client.receive_response():
            print(type(message).__name__)
```

`skills=["atmira-docx"]` loads the project skill from `cwd`, and `gate` allows only `Skill`, `Read`, a `Write` to the spec file and the exact `BUILD` command from `SKILL.md`.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `document` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 2284); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 72 --live
```

Suggested prompt:

> Use the exercise tool and explain the generated incident document.

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

The offline exercise generates a real .docx. Review the output in Word before sharing; this exercise does not perform visual document QA.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/72` | Lesson metadata |
| `POST /api/lessons/72/run` | Collected JSON events |
| `POST /api/lessons/72/stream` | Server-Sent Events |
| `/api/lessons/72/ws` | WebSocket events and cancellation |

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
