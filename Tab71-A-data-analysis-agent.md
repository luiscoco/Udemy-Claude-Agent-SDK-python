# Lesson 71: A data analysis agent

Compute totals in Python and attach a computation ledger to the model's explanation.

This lesson is part of **Agent workflows**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 71
uv run python -m agent_lab.lessons.lesson_71
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 71](http://127.0.0.1:8080/?lesson=71).

## The concept in code

```python
import csv
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, tool


def totals_with_ledger(path: str) -> dict[str, Any]:
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    ledger: list[str] = []
    with open(path, newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            totals[row["region"]] += Decimal(row["amount"])
            ledger.append(
                f"{row['region']} += {row['amount']} -> {totals[row['region']]}"
            )
    return {
        "totals": {region: str(value) for region, value in totals.items()},
        "ledger": ledger,
    }


def build_options(csv_path: str) -> ClaudeAgentOptions:
    @tool(
        "analyze_sales",
        "Return Python-computed sales totals by region and their ledger.",
        {},
    )
    async def analyze_sales(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": [
                {"type": "text", "text": json.dumps(totals_with_ledger(csv_path))}
            ]
        }

    return ClaudeAgentOptions(
        tools=[],
        mcp_servers={
            "lesson": create_sdk_mcp_server(name="lesson", tools=[analyze_sales])
        },
        allowed_tools=["mcp__lesson__analyze_sales"],
        system_prompt="Explain the totals from analyze_sales. Never recompute or alter a number.",
    )
```

`totals_with_ledger()` sums `amount` by `region` with `csv.DictReader` and `Decimal`, and the `analyze_sales` tool returns those totals plus the ledger for the model to explain.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `analysis` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 2218); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 71 --live
```

Suggested prompt:

> Use the analyze_sales tool and explain the verified totals.

The live profile is `analysis`. Its tools and configuration are in
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
| `GET /api/lessons/71` | Lesson metadata |
| `POST /api/lessons/71/run` | Collected JSON events |
| `POST /api/lessons/71/stream` | Server-Sent Events |
| `/api/lessons/71/ws` | WebSocket events and cancellation |

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
