"""Build Python lesson entry points and Markdown from the curriculum contract."""

import inspect
import json

from agent_lab.config import ROOT
from agent_lab.curriculum import LESSONS
from agent_lab.exercises import EXERCISES
from agent_lab.learning import guide


def main() -> None:
    rows = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
    documents = {row["id"]: row["document"] for row in rows}
    if len(rows) != len(LESSONS) or set(documents) != set(LESSONS):
        raise ValueError("The document index must contain each lesson exactly once.")
    for number, filename in documents.items():
        if not filename.startswith(f"Tab{number}-") or not filename.endswith(".md") or any(
            separator in filename for separator in ("/", "\\")
        ):
            raise ValueError(f"Invalid lesson document filename: {filename}")
    package = ROOT / "agent_lab" / "lessons"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(
        '"""Standalone entry points for all 75 Python lessons."""\n', encoding="utf-8"
    )
    index = []
    for number, lesson in LESSONS.items():
        module_name = f"lesson_{number:02}"
        source = (
            f'"""Lesson {number}: {lesson.title}.\n\n{lesson.objective}\n"""\n'
            "import asyncio\n\nfrom agent_lab.cli import run_lesson\n\n"
            'if __name__ == "__main__":\n'
            f"    raise SystemExit(asyncio.run(run_lesson({number})))\n"
        )
        (package / f"{module_name}.py").write_text(source, encoding="utf-8")
        filename = documents[number]
        function = EXERCISES[lesson.exercise]
        line = inspect.getsourcelines(function)[1]
        concept = guide(number)
        notes =f"\n## Python edition adaptation\n\n{lesson.notes}\n" if lesson.notes else ""
        markdown = f"""# Lesson {number}: {lesson.title}

{lesson.objective}

This lesson is part of **{lesson.topic}**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson {number}
uv run python -m agent_lab.lessons.{module_name}
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson {number}](http://127.0.0.1:8080/?lesson={number}).

## The concept in code

```python
{concept.concept_code.rstrip()}
```

{concept.code_focus}

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `{function.__name__}` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line {line}); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson {number} --live
```

Suggested prompt:

> {lesson.prompt}

The live profile is `{lesson.live_profile}`. Its tools and configuration are in
[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP
tool; the model explains already computed evidence. They do not autonomously
perform the offline exercise. Conversation profiles send two turns on one
`ClaudeSDKClient`. Question profiles require an answer in the browser UI.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.
{notes}
## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/{number}` | Lesson metadata |
| `POST /api/lessons/{number}/run` | Collected JSON events |
| `POST /api/lessons/{number}/stream` | Server-Sent Events |
| `/api/lessons/{number}/ws` | WebSocket events and cancellation |

Pydantic validates the request before the run starts:

```json
{{"mode": "offline", "prompt": "", "max_turns": 4, "max_budget_usd": 0.10}}
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
"""
        (ROOT / filename).write_text(markdown, encoding="utf-8")
        index.append(
            {
                "id": number,
                "title": lesson.title,
                "document": filename,
                "module": f"agent_lab.lessons.{module_name}",
                "exercise_function": function.__name__,
                "live_profile": lesson.live_profile,
                "adaptation": lesson.notes,
            }
        )
    (ROOT / "curriculum.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Built {len(index)} Python lesson modules and Markdown lessons.")


if __name__ == "__main__":
    main()
