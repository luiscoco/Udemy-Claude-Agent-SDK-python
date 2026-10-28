# Lesson 31: AskUserQuestion

Validate the tool's question shape and route a response through the permission callback.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 31
uv run python -m agent_lab.lessons.lesson_31
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 31](http://127.0.0.1:8080/?lesson=31).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `questions`, line 1156). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("questions")
async def questions(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Validate AskUserQuestion input, then route the user's answer through can_use_tool."""
    from agent_lab.hooks import permission_callback
    from agent_lab.sdk import Questions

    def question(**changes: Any) -> dict[str, Any]:
        item = {
            "question": "Which teaching style?",
            "header": "Style",
            "options": [
                {"label": "Concise", "description": "One short example"},
                {"label": "Detailed", "description": "Explain each step"},
            ],
            "multiSelect": False,
        }
        return {"questions": [item | changes]}

    candidates = {
        "valid question": question(),
        "only one option": question(options=[{"label": "Concise", "description": "Short"}]),
        "header too long": question(header="A header that is far too long to fit"),
        "unknown field": question(priority="high"),
    }
    shape_checks = []
    for label, body in candidates.items():
        try:
            Questions.model_validate(body)
            shape_checks.append({"case": label, "valid": True, "problem": ""})
        except ValidationError as exc:
            error = exc.errors()[0]
            where = ".".join(str(part) for part in error["loc"])
            shape_checks.append(
                {"case": label, "valid": False, "problem": f"{where}: {error['msg']}"}
            )
    shown: list[str] = []

    async def ask(arguments: dict[str, Any]) -> dict[str, Any]:
        shown.extend(item["question"] for item in arguments["questions"])
        return {"Which teaching style?": "Concise"}  # stands in for the user's click

    callback = permission_callback(
        lambda name, arguments: (name == "AskUserQuestion", "Only AskUserQuestion is enabled."),
        ask,
    )
    answered = await callback("AskUserQuestion", candidates["valid question"], None)
    other = await callback("Bash", {"command": "ls"}, None)
    return {
        "shape_checks": shape_checks,
        "shown_to_user": shown,
        "routed": {
            "result_type": type(answered).__name__,
            "answers": answered.updated_input["answers"],
        },
        "other_tool": {"result_type": type(other).__name__, "message": other.message},
        "source": "real can_use_tool callback; the answer stands in for the user",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 31 --live
```

Suggested prompt:

> Use AskUserQuestion to ask which response style I prefer.

The live profile is `questions`. Its tools and configuration are in
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
| `GET /api/lessons/31` | Lesson metadata |
| `POST /api/lessons/31/run` | Collected JSON events |
| `POST /api/lessons/31/stream` | Server-Sent Events |
| `/api/lessons/31/ws` | WebSocket events and cancellation |

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
