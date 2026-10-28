# Lesson 40: Resume and conversation history

Explain Python resume options and avoid treating a host transcript as SDK state.

This lesson is part of **Sessions and context**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 40
uv run python -m agent_lab.lessons.lesson_40
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 40](http://127.0.0.1:8080/?lesson=40).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `resume`, line 2004). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("resume")
async def resume(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Resume needs the SDK's own transcript in the same config dir; host files do not count."""
    from claude_agent_sdk import ClaudeAgentOptions

    config = root / "isolated-config"
    session_id = write_fixture_session(config)
    # A host transcript is application data: the SDK neither lists nor resumes it.
    (root / "host-transcript.json").write_text(
        json.dumps([{"role": "user", "content": "Remember HOST-ONLY."}]), encoding="utf-8"
    )
    same_dir = await probe_sessions(config, session_id)
    other_dir = await probe_sessions(root / "empty-config", session_id)
    variants = {
        "continue this session": ClaudeAgentOptions(resume=session_id),
        "branch into a new session": ClaudeAgentOptions(resume=session_id, fork_session=True),
        "most recent session": ClaudeAgentOptions(continue_conversation=True),
    }
    return {
        "resume_options": [
            {
                "goal": goal,
                "resume": options.resume,
                "fork_session": options.fork_session,
                "continue_conversation": options.continue_conversation,
            }
            for goal, options in variants.items()
        ],
        "sdk_sessions_in_run_config": [row["session_id"] for row in same_dir["sessions"]],
        "host_transcript_listed": any(
            "HOST-ONLY" in (row.get("first_prompt") or "") for row in same_dir["sessions"]
        ),
        "sessions_in_another_config_dir": len(other_dir["sessions"]),
        "rule": "Resume with the same CLAUDE_CONFIG_DIR that recorded the session.",
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 40 --live
```

Suggested prompt:

> Remember the code word CONTEXT.

The live profile is `conversation`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

The interactive lab preserves context within one run. Cross-run SDK resume requires a persistent configuration directory and a saved session id.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/40` | Lesson metadata |
| `POST /api/lessons/40/run` | Collected JSON events |
| `POST /api/lessons/40/stream` | Server-Sent Events |
| `/api/lessons/40/ws` | WebSocket events and cancellation |

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
