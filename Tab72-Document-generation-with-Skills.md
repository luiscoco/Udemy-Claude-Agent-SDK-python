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

## What to inspect

Read the exercise, predict its evidence, then run it. Inspect input validation,
state ownership and the condition that allows the next step. A model's description
of an action is not evidence that the action happened.

The exercise is in [agent_lab/exercises.py](agent_lab/exercises.py)
(function `document`, line 2276). Host contracts are in
[agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

```python
@exercise("document")
async def document(root: Path, request: RunRequest, lesson: Lesson) -> dict[str, Any]:
    """Follow the atmira-docx Skill's workflow: write a spec, build, fix SPEC ERRORs, rebuild."""
    import shutil

    from docx import Document

    from agent_lab.config import ROOT

    skill = root / ".claude" / "skills" / "atmira-docx"
    shutil.copytree(ROOT / "docgen-skills" / "atmira-docx", skill)
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    front = dict(
        line.split(": ", 1) for line in text.split("---")[1].strip().splitlines() if ": " in line
    )
    # The spec is what the model writes in a live run; here a fixture stands in for it.
    # The first draft breaks the incident rules: no severity callout and sections out of order.
    draft = {**INCIDENT_SPEC, "blocks": INCIDENT_SPEC["blocks"][1:]}
    attempts = []
    for number, spec in enumerate([draft, INCIDENT_SPEC], 1):
        (root / "incident.spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            ".claude/skills/atmira-docx/scripts/build_docx.py",
            "incident.spec.json",
            "out/incident-report.docx",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async with asyncio.timeout(60):
            output, _ = await process.communicate()
        attempts.append(
            {
                "attempt": number,
                "exit_code": process.returncode,
                "output": output.decode().strip().replace(str(root), ".")[-300:],
            }
        )
        if process.returncode == 0:
            break
    built = root / "out" / "incident-report.docx"
    result: dict[str, Any] | None = (
        {"path": "out/incident-report.docx"} if built.is_file() else None
    )
    if result is not None:
        shutil.copyfile(built, root / "incident-report.docx")  # served by the download link
        word = Document(str(built))
        result |= {
            "bytes": built.stat().st_size,
            "headings": [
                p.text for p in word.paragraphs if p.style and p.style.name == "Heading 1"
            ],
            "tables": len(word.tables),
        }
    # A failed build is still evidence: the SPEC ERROR lines are what the student must read.
    return {
        "skill": {"name": front.get("name"), "description": front.get("description")},
        "discovery": "Only the name and description are loaded up front; the body, reference "
        "files and script are read when the skill is used.",
        "workflow_command": "python .claude/skills/atmira-docx/scripts/build_docx.py "
        "incident.spec.json out/incident-report.docx",
        "attempts": attempts,
        "document": result,
        "spec_author": "fixture standing in for the model",
    }
```

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
