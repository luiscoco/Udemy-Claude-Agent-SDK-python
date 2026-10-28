# Lesson 67: Multi-tenant SaaS architecture

Capture tenant identity in host state and reject cross-tenant access.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 67
uv run python -m agent_lab.lessons.lesson_67
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 67](http://127.0.0.1:8080/?lesson=67).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `tenancy`, line 1800). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("tenancy")
def tenancy(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Every query runs with the tenant from host state; tool arguments cannot change it."""
    orders = Orders(root / "orders.sqlite")
    try:
        sessions = {"session-alice": "alice", "session-bob": "bob"}

        def list_orders(session_id: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
            # A model-supplied tenant is ignored: the tool schema has no tenant field.
            return orders.list(sessions[session_id], arguments.get("status", "all"))

        checks: list[dict[str, Any]] = [
            {
                "check": "alice sees her orders",
                "result": [r["id"] for r in list_orders("session-alice", {})],
            },
            {
                "check": "bob sees his orders",
                "result": [r["id"] for r in list_orders("session-bob", {})],
            },
            {
                "check": "alice passes tenant=bob",
                "result": [r["id"] for r in list_orders("session-alice", {"tenant": "bob"})],
            },
            {"check": "injection in tenant", "result": orders.list("alice' OR 1=1 --")},
            {
                "check": "bob cancels alice's order",
                "result": orders.cancel("bob", "A-001", 1, approved=True),
            },
            {
                "check": "alice cancels with a stale version",
                "result": orders.cancel("alice", "A-001", 7, approved=True),
            },
            {
                "check": "alice cancels her current order",
                "result": orders.cancel("alice", "A-001", 1, approved=True),
            },
        ]
    finally:
        orders.close()
    return {
        "tenant_source": "host session table",
        "checks": checks,
        "cross_tenant_rows": 0
        if checks[2]["result"] == ["A-001"] and not checks[3]["result"]
        else 1,
        "cross_tenant_update": checks[4]["result"],
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 67 --live
```

Suggested prompt:

> Use the exercise tool to inspect tenant isolation.

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
| `GET /api/lessons/67` | Lesson metadata |
| `POST /api/lessons/67/run` | Collected JSON events |
| `POST /api/lessons/67/stream` | Server-Sent Events |
| `/api/lessons/67/ws` | WebSocket events and cancellation |

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
