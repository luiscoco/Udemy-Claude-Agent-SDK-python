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
        live_description = (
            "[agent_lab/web_tools_lab.py](agent_lab/web_tools_lab.py). Fixed Node.js WebSearch and WebFetch actions use PreToolUse for a host domain rewrite and exact fetch URL allowlist, then PostToolUse for source history and a labelled heuristic redaction example. Live SDK call/result IDs, hook receipts and terminal costs are correlated by lane; cited URL provenance does not prove claim support."
            if number == 42 else
            "[agent_lab/client_lifecycle_lab.py](agent_lab/client_lifecycle_lab.py). Three fixed prompts run sequentially through one connected Python ClaudeSDKClient. A completed owned manifest records the session ID; a fresh client resumes that same ID and must return a successful terminal. Prepared mode uses ScriptedCLI and is labelled as a fixture. The historical JavaScript V2 API is not a Python SDK export."
            if number == 41 else
            "[agent_lab/drops_lab.py](agent_lab/drops_lab.py). The host builds four persisted SDK turns with fixed UUIDs, an owned pause tool and a queued command attachment, then parses the active JSONL ancestry. Exact last-turn and unsafe queued-turn forks use resume-session-at and resume-drops-turn; a fresh recovery fork is optional. Prepared refusal results are authored fixtures. The live unsafe CLI result is parsed from the SDK's structured ResultError.data when connect raises before yielding; exception text alone does not count."
            if number == 40 else
            "[agent_lab/config_root_lab.py](agent_lab/config_root_lab.py). Each run creates owned trusted, branch and docs Git worktrees. A dry SDK argument capture checks project-config-root serialization; live SDK init, hook/command origins and fixture hashes establish selected configuration. A separate exact Bash probe compares trusted tool unavailability with branch permission, and credential-free startup probes capture invalid-root CLI errors."
            if number == 39 else
            "[agent_lab/suggestions_lab.py](agent_lab/suggestions_lab.py). A transport tap records raw CLI prompt_suggestion envelopes after SDK results while a separate validated host queue owns submitted inputs. The installed Python SDK parser skips this event type; suggestions may be absent even after successful turns. No tools are enabled."
            if number == 38 else
            "[agent_lab/permission_gate_lab.py](agent_lab/permission_gate_lab.py). A fixed Python stdio MCP process asks a loopback host gate for one owned Write decision. The SDK uses permission_prompt_tool_name and an exact Write hook; process receipt, SDK result and fresh file content must agree. Node is unavailable in this Python workspace."
            if number == 37 else
            "[agent_lab/process_spawning_lab.py](agent_lab/process_spawning_lab.py). The host launches a fixed Python child with explicit argv, local cwd, separate pipes, a JSONL byte tap and bounded cleanup. A separate SDK CLI turn must return a matching successful terminal. The installed Python SDK has no public custom-spawner option; this host child does not carry SDK protocol."
            if number == 36 else
            "[agent_lab/session_store_lab.py](agent_lab/session_store_lab.py). The host verifies atomic JSON replacement and UUID coverage against the SDK mirror. In-memory and durable SQLite resume, eager/batched flushing, disabled storage, and rejected/delayed store operations have bounded checks. No model tools are enabled."
            if number == 35 else
            "[agent_lab/styles_lab.py](agent_lab/styles_lab.py). The host writes an owned output-style file and settings.json, then compares fixed marker behavior with project settings enabled or disabled on the real SDK. No model tools are enabled."
            if number == 34 else
            "[agent_lab/elicitation_lab.py](agent_lab/elicitation_lab.py). A provider-backed SDK tool invokes the owned Python MCP server through a client with a labelled simulated form callback. The host correlates the SDK call/result and checks the actual server outcome."
            if number == 33 else
            "[agent_lab/plan_lab.py](agent_lab/plan_lab.py). The SDK starts in plan mode; the host validates a structured proposal and only an approved valid plan triggers a default-mode confirmation and fixed workers. Approval is a selected lab control."
            if number == 32 else
            "[agent_lab/question_lab.py](agent_lab/question_lab.py). The live run validates one exact AskUserQuestion call and returns a labelled simulated answer through can_use_tool, then correlates the SDK result."
            if number == 31 else
            "[agent_lab/slash_commands.py](agent_lab/slash_commands.py). The live run uses one "
            "SDK connection to inspect command inventory, invoke the owned slash command, "
            "and correlate a Read result with the selected response marker."
            if number == 21 else
            "[agent_lab/project_memory.py](agent_lab/project_memory.py). The live run "
            "compares an owned CLAUDE.md marker with project settings enabled and disabled "
            "under preset and custom system prompts, on fresh SDK connections."
            if number == 22 else
            "[agent_lab/plugin_lab.py](agent_lab/plugin_lab.py). The live run checks "
            "namespaced command inventory and response markers, a correlated Skill "
            "tool call, and a disabled-plugin discovery control."
            if number == 23 else
            "[agent_lab/harness_lab.py](agent_lab/harness_lab.py). The live run "
            "receives a structured plan, applies exact host validation and approval, "
            "then records deterministic worker effects or a specific rejection."
            if number == 24 else
            "[agent_lab/compaction_lab.py](agent_lab/compaction_lab.py). The live run "
            "correlates a bounded SDK MCP tool result with its host callback and "
            "records any actual PreCompact hook events without forcing compaction."
            if number == 25 else
            "[agent_lab/control_lab.py](agent_lab/control_lab.py). The live run "
            "observes control acknowledgements and two turns on one SDK session, "
            "or interrupts a streamed turn, then checks post-disconnect rejection."
            if number == 26 else
            "[agent_lab/background_lab.py](agent_lab/background_lab.py). The live run "
            "owns a host watcher across one real SDK turn, then cancels or "
            "releases and awaits it before disconnecting."
            if number == 27 else
            "[agent_lab/retry_lab.py](agent_lab/retry_lab.py). The live run "
            "correlates real SDK MCP refund calls while the host applies fixed "
            "transient/permanent retry decisions to an in-memory ledger."
            if number == 28 else
            "[agent_lab/image_input_lab.py](agent_lab/image_input_lab.py). The live run "
            "validates an owned PNG, sends a typed base64 image plus text through "
            "the SDK, and compares red/blue responses with the file hashes."
            if number == 29 else
            "[agent_lab/todo_lab.py](agent_lab/todo_lab.py). The live run "
            "checks real TodoWrite calls with PreToolUse, commits accepted "
            "results through PostToolUse, and derives suggestions from the host ledger."
            if number == 30 else
            "[agent_lab/sdk.py](agent_lab/sdk.py). Evidence profiles expose a read-only MCP\n"
            "tool; the model explains already computed evidence. They do not autonomously\n"
            "perform the offline exercise. Conversation profiles send two turns on one\n"
            "`ClaudeSDKClient`. Question profiles require an answer in the browser UI."
        )
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
{live_description}

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
