# Claude Agent SDK Learning Platform Python edition

Learn the official Python Claude Agent SDK through 75 numbered exercises and a
browser lab authored in Python. The stack is **Python, FastAPI, Uvicorn, NiceGUI,
Pydantic, asyncio, the official MCP Python SDK, pytest, HTTPX, uv, Ruff and mypy**.

## Install and start

Use Python 3.12 or newer. This checkout was verified with Python 3.14.
Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```shell
uv sync --locked
uv run agent-lab serve
```

Open **http://127.0.0.1:8080**. The home page shows three learning paths
(Beginner, Application Developer, Advanced Harness), the eight course sections
with their quizzes, your progress and the visual guides. Each lesson has six tabs:

| Tab | What you do there |
|---|---|
| **Learn** | Prepare the lesson, read the concept and Python tutorial, complete the workbook (review checklist, private notes, challenge with small and detailed hints, reference explanation, saved attempts) and answer the knowledge check. |
| **Lab walkthrough** | Follow five steps, see what evidence to inspect, the expected result and recovery tips. |
| **Visual guide** | Study the related course infographic with zoom, fit and scroll-to-pan. |
| **Run the exercise** | Run offline or live; the **Automatic check** compares the local evidence with the lesson criterion. |
| **Python source** | Read the host exercise used by the UI, CLI and API. |
| **AI Tutor** | Get a free prepared answer grounded in the lesson, or explicitly authorize one live answer (one turn, no tools, 0.05 USD budget threshold) and save it. |

Workbook entries, quiz answers, check results, saved tutor answers and appearance
(Light/Dark/System theme, text size) are stored per browser in `.nicegui/` on
this machine. They are never sent to Claude and do not sync between browsers.
The automatic check covers local evidence only; your self-review stays separate.
The **Response and results** panel displays formatted Claude answers, local
exercise results, structured data and downloads. Offline fixtures are labelled
separately from live answers. Raw SDK events remain in a collapsed **Diagnostics**
section for lessons that inspect messages, hooks or usage.
FastAPI's API reference is at http://127.0.0.1:8080/docs.

Without uv, create `.venv` with `python -m venv .venv` and use the following.
The pip fallback requires pip 25.1+ for `--group`; uv is the reproducible setup.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e . --group dev
.\.venv\Scripts\python.exe -m agent_lab serve
```

macOS or Linux:

```shell
.venv/bin/python -m pip install -e . --group dev
.venv/bin/python -m agent_lab serve
```

## Run lessons independently

```shell
uv run agent-lab list
uv run agent-lab lesson 1
uv run python -m agent_lab.lessons.lesson_05
uv run agent-lab lesson 75
```

Offline exercises execute local host code without calling Claude. Recorded
messages, usage and scripted workers are explicitly identified as fixtures.
The worktree lesson requires Git. Evidence remains in `.lab-data/<run-id>/work/`.
The browser offers downloads for the document-generation exercise.

## Enable live SDK calls

Windows: `Copy-Item .env.example .env`. macOS/Linux: `cp .env.example .env`.
Edit the copied file:

```dotenv
ANTHROPIC_API_KEY=your-key-here
LAB_ENABLE_LIVE=true
LAB_MODEL=claude-haiku-4-5
```

Restart the server. Live mode uses `claude-agent-sdk`, not the general Messages
API client. The SDK manages the Claude Code runtime. Each run has its own working
directory and CLI configuration; this lab does not reuse a personal Claude Code
login or load settings from your repository.

Check the runtime before enabling paid calls:

```shell
uv run agent-lab doctor
```

Some platform/source distributions omit the bundled Claude executable. This
Windows SDK package does. In that case, install native Claude Code using the
[official installation instructions](https://code.claude.com/docs/en/setup),
verify `claude --version`, and set `LAB_CLI_PATH` to the executable if it is not
on PATH or in the native user install directory (`~/.local/bin`). The app and
`agent-lab doctor` use the same executable lookup. Offline exercises do not
require that executable.

```shell
uv run agent-lab lesson 5 --live --prompt "Add 19 and 23 using the calculator"
```

Live calls may incur charges. The SDK budget is a threshold, not an exact billing
cap. The default server listens locally; add authentication and authorization
before exposing these teaching endpoints to other users.

## Architecture

| File or directory | Responsibility |
|---|---|
| `agent_lab/curriculum.py` | Stable lesson ids, objectives and adaptations |
| `agent_lab/lessons/` | Standalone entry points for all 75 lessons |
| `agent_lab/exercises.py` | Actual offline host exercises |
| `agent_lab/services.py` | Schemas, graph, approvals, ledger, retrieval and SQLite |
| `agent_lab/sdk.py` | Official SDK tools, hooks and interactive client |
| `agent_lab/runtime.py` | Task ownership, deadlines and cancellation |
| `agent_lab/api.py` | JSON, SSE and WebSocket routes |
| `agent_lab/ui.py` | NiceGUI navigation and exercise controls |
| `agent_lab/ui_learning.py` | Lesson tabs, workbook, quizzes, visual guides, tutor, home and appearance |
| `agent_lab/learning.py` | Validated lesson guides, course paths and quizzes, automatic evidence checks |
| `agent_lab/tutor.py` | Prepared tutor answers and the bounded, consented live tutor call |
| `agent_lab/content/` | `lessons.json` (per-lesson Python guides and quizzes) and `course.json` (paths, section quizzes, visual guides) |
| `agent_lab/integrations/` | Explicitly started MCP and notification adapters |
| `Tab*.md` | Python lesson tutorials |
| `curriculum.json` | Machine-readable lesson, document and source index |
| `tests/` | Offline regression and integration tests |

The UI, CLI and API call one service. SDK connections open, consume and close in
one producer task. Cancellation awaits it. Tool arguments never grant access
to another customer or an arbitrary host file.

## Optional integrations

```shell
uv run python -m agent_lab.integrations.notes_mcp
uv run python -m agent_lab.integrations.agent_mcp
uv run python -m agent_lab.integrations.remote_mcp https://your-trusted-server/mcp
```

The first two are stdio MCP servers. The agent server requires live access to
be explicitly enabled. The remote inspector needs a separately running server.

For the Python Playwright MCP integration:

```shell
uv sync --locked --extra browser
uv run playwright install chromium
uv run python -m agent_lab.integrations.browser_mcp
```

It allows requests only to `LAB_BROWSER_ORIGIN`. Channel notification adapters
need explicitly supplied credentials and an HTTPX client; offline runs never
call them and application startup never sends a message.

For a native window: `uv sync --locked --extra desktop`, then
`uv run agent-lab serve --native`. Install the platform's pywebview dependencies
as needed. Browser mode is the standard course setup.

## Verify and rebuild

```shell
uv run ruff check agent_lab tests scripts
uv run mypy agent_lab
uv run pytest
uv run python scripts/build_curriculum.py
```

The documentation build uses the curriculum contract, document filenames in
`curriculum.json`, and exercise source. It does not require the recovery archive.
Tests require no API credentials. Paid model calls remain opt-in.

## Migration coverage and recovery

This edition reimplements the 75 learning objectives using a shared Python app
and streamlined exercises. **It is not yet feature-for-feature equivalent to all
controls, live experiments and production workflows of the original edition.**
The autonomous engineering capstone uses scripted workers offline and real SDK
agents in live mode, with source proposals validated by the host. Its full Git
worktree merge/recovery and PR publication workflow is still pending. Cloud-provider
experiments, SDK-native checkpointing/session-store experiments, channel approval
delivery and model-driven PR publication need further implementation and live
verification. Adaptations appear in lesson notes and the browser UI.

Lesson 41 teaches the public Python interactive client. Lesson 69 teaches Python
desktop embedding. The legacy runtime, Node dependencies, scripts, CI templates
and generated lab folders have been removed from the active project.
The original code and documents are preserved in
`.migration/original-typescript.zip` with a SHA-256 manifest; secrets are excluded.
Keep the snapshot until migration parity has been reviewed. It is recovery data
and is not used by the app, tests or documentation builder.

### Learning features ported from the Student Rebuild

The lesson workspace, workbook, quizzes, learning paths, AI Tutor, automatic checks,
appearance controls and the four visual guides (`public/visual-guides/`) follow
[Udemy-Claude-Agent-SDK-Student-Rebuild](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild).
Lesson guides and quizzes were rewritten for the Python exercises in this
repository; every automatic check is tested against the actual offline evidence.
The Rebuild's per-lesson infographics, narrated audio and TypeScript code tours
are not included because they describe its TypeScript implementation.

## References

- [Official Python Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
- [Python API reference](https://code.claude.com/docs/en/agent-sdk/python)
- [NiceGUI](https://nicegui.io/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
