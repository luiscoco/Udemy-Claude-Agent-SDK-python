# Lesson 50: Full-stack support capstone

Bind a support tool to a host-selected customer and require approval before refunding.

This lesson is part of **Production and deployment**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 50
uv run python -m agent_lab.lessons.lesson_50
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 50](http://127.0.0.1:8080/?lesson=50).

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `support`, line 1304). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("support")
def support(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Bind tools to the signed-in customer and require an exact approval before a refund."""
    customer = "alice"  # chosen by the host session, never by tool arguments
    orders = Orders(root / "orders.sqlite")
    try:
        visible = orders.list(customer)
    finally:
        orders.close()
    proposal = Refund(order_id="A-001", amount_cents=4200, reason="Damaged on arrival")
    steps: list[dict[str, Any]] = []
    approval = Approval(proposal)
    try:
        approval.consume(proposal)
    except ValueError as exc:
        steps.append({"step": "refund before approval", "outcome": str(exc)})
    try:
        approval.decide("guessed-token", True)
    except PermissionError as exc:
        steps.append({"step": "approve with a wrong credential", "outcome": str(exc)})
    approval.decide(approval.token, True)
    steps.append({"step": "staff approves", "outcome": approval.state})
    larger = proposal.model_copy(update={"amount_cents": 9000})
    try:
        approval.consume(larger)
    except ValueError as exc:
        steps.append({"step": "refund a different amount", "outcome": str(exc)})
    approval.consume(proposal)
    steps.append({"step": "refund the approved action", "outcome": approval.state})
    return {
        "customer": customer,
        "visible_orders": visible,
        "proposal": proposal.model_dump(),
        "approval_steps": steps,
        "refunds_executed": 1,
        "final_state": approval.state,
    }
```

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 50 --live
```

Suggested prompt:

> Use the support tools to inspect my orders; propose a refund without executing it.

The live profile is `support`. Its tools and configuration are in
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
| `GET /api/lessons/50` | Lesson metadata |
| `POST /api/lessons/50/run` | Collected JSON events |
| `POST /api/lessons/50/stream` | Server-Sent Events |
| `/api/lessons/50/ws` | WebSocket events and cancellation |

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
