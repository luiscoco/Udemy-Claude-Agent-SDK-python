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
| **Learn** | Prepare the lesson, read the concept, follow its **code tour** (each step highlights lines of the concept code; **Read aloud** uses your browser's voice) and the Python tutorial, complete the workbook (review checklist, private notes, challenge with small and detailed hints, reference explanation, saved attempts) and answer the knowledge check. |
| **Lab walkthrough** | Follow five steps, see what evidence to inspect, the expected result and recovery tips. |
| **Visual guide** | Study the related course infographic with zoom, fit and scroll-to-pan. |
| **Run the exercise** | Run offline or live; the **Automatic check** compares the local evidence with the lesson criterion. |
| **Python source** | Read the host exercise used by the UI, CLI and API. |
| **AI Tutor** | Get a free prepared answer grounded in the lesson, or explicitly authorize one live answer (one turn, no tools, 0.05 USD budget threshold) and save it. |

Every lesson has **Open Learning Guide**: an explicitly started, seven-section
written tour with red target highlighting, saved-position Resume, tab-change pause,
minimize/close, Finish tour and route-aware Next lesson. Each guide uses that lesson's
preparation, Python example, offline exercise, expected evidence and challenge. It
never clicks Run or changes your manual checklist. Recorded Python narration remains
pending. See [Learning Guide maintenance](docs/learning-guides.md) and the
[reference parity comparison](docs/reference-parity.md).

Workbook entries, quiz answers, check results, saved tutor answers, guide position and appearance
(Light/Dark/System theme, text size) are stored per browser in `.nicegui/` on
this machine. They are never sent to Claude and do not sync between browsers.

Open **My Learning** from the home page or a lesson's navigation to resume your
saved guide, see checklist progress by learning path, and find notes, practice quiz
results and challenge attempts. The dashboard reads your existing records; exercise
checks and quiz scores remain separate from manual review. See the
[My Learning guide](docs/my-learning.md).

Use **Export progress** on the home page or in My Learning to save them as a JSON file, and
**Import progress** in another browser to restore them. Imports are validated
and replace that browser's progress only after you confirm.
Automatic checks cover exercise evidence; your self-review stays separate.
Lesson 1 checks terminal stream success and includes three recorded outcome scenarios,
seven explained questions and bounded request validation. See the [Lesson 1 guide](docs/lesson-1-query.md).
Lessons 2–10 also include seven explained questions, lesson-specific experiment controls,
correlated evidence checks and three exact source excerpts. See the [SDK experiments guide](docs/foundations-2-10.md).
Lesson 11 adds project/plugin skill discovery, invocation and host-preload comparisons,
supporting resources and correlated Skill evidence. See the [Skills lab guide](docs/lesson-11-skills.md).
Lesson 12 adds one open input queue, manual messages, acknowledged runtime controls,
token-scoped session APIs and closure checks. See the [Streaming input guide](docs/lesson-12-streaming.md).
Lesson 13 adds real inventory MCP transports, lifecycle workshops, scoped APIs and
correlated agent evidence. See the [MCP servers guide](docs/lesson-13-mcp.md).
Lesson 14 compares requested model/thinking/effort with observed Stop evidence,
keeps missing metrics unknown and offers a separate prompt-free metadata probe.
See the [Thinking, effort and models guide](docs/lesson-14-thinking.md).
Lesson 15 adds final usage checks, message grouping, limit scenarios and a separate
session cost meter. See the [Cost and usage guide](docs/lesson-15-usage.md).
Lesson 16 adds owned project/local settings controls, an actual child environment probe and correlated Read/terminal checks. CLI settings precedence remains separate. See the [Settings and environment guide](docs/lesson-16-settings.md).
Lesson 17 adds a guarded one-file native rewind workflow, real Python client control fixtures, checkpoint UUID checks and hash-verified restoration. See the [Checkpointing and rewind guide](docs/lesson-17-checkpointing.md).
Lesson 18 compares correlated Read policy outcomes with an actual process counterexample and a separately verified native Linux/WSL sandbox probe. See the [Sandbox guide](docs/lesson-18-sandbox.md).
Lesson 19 adds an owned session catalog with paged inspection, rename/tag, local fork and deletion through the public SDK APIs in an isolated child. See the [Session management guide](docs/lesson-19-sessions.md).
Lesson 20 adds correlated hook decisions, Read rewrites, success/failure audits, prompt/Stop observers and contained callback faults. See the [Hooks in depth guide](docs/lesson-20-hooks.md).
Lesson 21 adds owned Slash command templates, SDK inventory discovery, correlated invocation evidence and a no-project control. See the [Slash commands guide](docs/lesson-21-slash-commands.md).
Lesson 22 compares owned CLAUDE.md marker rules across project settings and system prompt modes, with automatic memory disabled in a private CLI config. See the [CLAUDE.md and memory guide](docs/lesson-22-project-memory.md).
Lesson 23 adds a host-owned local plugin with namespaced command discovery, a correlated Skill invocation and a disabled-plugin control. See the [Plugins guide](docs/lesson-23-plugins.md).
Lesson 24 adds a structured proposal gate with exact host validation, approval controls and deterministic two-file worker effects. See the [Harnesses guide](docs/lesson-24-harnesses.md).
Lesson 25 adds an actual bounded MCP tool result, a host progress summary control and a registered `PreCompact` observer. See the [Compaction and context guide](docs/lesson-25-compaction-context.md).
Lesson 26 adds observed SDK model and permission-mode controls, a streamed-turn interrupt, and post-disconnect rejection checks. See the [Query control methods guide](docs/lesson-26-query-control-methods.md).
Lesson 27 carries a host-owned background watcher across a real SDK turn and verifies cancellation or release plus awaited cleanup. See the [Background tasks guide](docs/lesson-27-background-tasks.md).
Lesson 28 adds bounded host retries over a real SDK MCP tool, with transient recovery, permanent rejection and an idempotent in-memory write ledger. See the [Errors, retries and recovery guide](docs/lesson-28-errors-retries-recovery.md).
Lesson 29 sends a validated workspace-owned PNG as a typed SDK image block and checks red and blue live responses. See the [Images and file input guide](docs/lesson-29-images-file-input.md).
Lesson 30 gates real TodoWrite calls with pre and post hooks, commits only accepted transitions and derives suggestions from the host ledger. See the [Todo tracking guide](docs/lesson-30-todo-tracking.md).
Lesson 31 validates a fixed AskUserQuestion call, routes a labelled simulated host answer through `can_use_tool`, and correlates the real SDK tool result with the callback. Both answer variants passed provider-backed acceptance. See the [AskUserQuestion guide](docs/lesson-31-ask-user-question.md).
Lesson 32 starts the SDK in plan mode, validates a structured proposal, and switches to default mode only for a selected approved plan before fixed host workers run. Three provider-backed variants passed. See the [Plan mode guide](docs/lesson-32-plan-mode.md).
Lesson 33 bridges a provider-backed SDK tool to an owned Python MCP server, checks simulated accept, decline and cancel responses against actual server outcomes, and records the installed SDK's native elicitation-hook limitation. See the [MCP elicitation guide](docs/lesson-33-mcp-elicitation.md).
Lesson 34 compares owned Teaching and Brief output styles with project settings enabled and disabled, checking the SDK-reported style, response marker and unchanged files. All three provider-backed variants passed. See the [Output styles guide](docs/lesson-34-output-styles.md).

Lesson 35 compares a host JSON transcript with the SDK's separate session mirror. It includes UUID coverage, a durable SQLite adapter, fresh-client resume, flush and fault controls, and scoped inspection routes. Eight provider-backed cases passed. See the [Session stores guide](docs/lesson-35-session-stores.md).

Lesson 36 launches a fixed local host child, taps JSONL stdout without changing forwarded bytes, keeps stderr separate and reaps interrupted children. A separate real SDK turn must also succeed. Five provider-backed cases passed their expected outcomes. The installed Python SDK has no public custom-spawner option. See the [Process spawning guide](docs/lesson-36-process-spawning.md).

Lesson 37 runs a fixed Python stdio MCP permission gate for an owned Write, checks its loopback host decision, SDK tool result and fresh file content, and exposes scoped inspection routes. Six provider-backed outcomes passed. See the [Permission gate guide](docs/lesson-37-permission-gate.md).

Lesson 38 observes raw CLI prompt suggestions after SDK turns and keeps them separate from the host input queue. It includes token-owned interactive chat routes, offline evidence scenarios and bounded live probes. See the [Prompt suggestions guide](docs/lesson-38-prompt-suggestions.md).

Lesson 39 compares working directory with an independently selected project configuration root across owned Git worktrees. Its probes record SDK init, hook and command origins, exact Bash takeover evidence, and credential-free CLI startup failures. See the [Project configuration root guide](docs/lesson-39-project-config-root.md).

Lesson 40 parses persisted SDK transcript ancestry, keeps queued attachments in their logical turn, and compares exact last-turn and unsafe queued-turn resume forks. The real unsafe CLI result is recovered from the SDK's structured `ResultError.data` after connection fails; exception text alone is not counted. The full provider-backed comparison passed. See the [Resume drops turn guide](docs/lesson-40-resume-drops-turn.md).

Lesson 41 runs three turns on one Python `ClaudeSDKClient`, refuses a query after disconnect and resumes an owned session in a fresh client. The historical JavaScript V2 API is outside this explicit Python adaptation. See the [Python client lifecycle guide](docs/lesson-41-python-client-lifecycle.md).

Lesson 42 uses fixed Node.js WebSearch/WebFetch actions with host URL policy, call/result correlation, a labelled hostile-output overlay, and per-lane citation provenance. Its provider-backed scenarios met their selected checks, including a missing-page Needs review outcome. See the [Web tools guide](docs/lesson-42-web-tools.md).
Lesson 43 runs an owned remote MCP fixture with machine credential discovery, HTTP and SSE clients, tool receipts, and digest-checked resources. Provider-backed tool, resource and same-client credential rotation calls are bounded; rotation uses a version-guarded private SDK control. Three source-aligned Yash clips are recorded. See the [remote MCP guide](docs/lesson-43-remote-mcp.md) and [narration review](docs/lesson-43-narration.md).

Lesson 44 uses an owned OTLP HTTP JSON collector for six local and live telemetry actions. The live checks require received metrics, logs and traces joined to the SDK session and tool call; privacy, trace parenting, denied-tool, temporality and collector-auth comparisons are included. Three source-aligned Yash clips are recorded. See the [telemetry guide](docs/lesson-44-telemetry.md) and [narration review](docs/lesson-44-narration.md).

Lesson 45 compares five native cloud provider routes through an owned loopback proxy and fixed host-key upstream. Five live actions cover catalog inspection, equivalent prompts, authentication, model forms and denied Sonnet with fresh Haiku recovery. The portal includes distinct diagrams and three source-aligned Yash clips. See the [cloud provider guide](docs/lesson-45-cloud-providers.md) and [live acceptance](docs/live-acceptance.md).

Lesson 46 measures prompt-cache behavior over two native SDK turns with independently matched wire and SDK counters. Five live acceptance cases cover cache anatomy, one-hour TTL, changed prefix, capped model switch and allowed model switch. Additional bounded live probes cover the other TTL and prefix selectors plus cancellation. The portal shows a per-turn table, distinct diagrams and three source-aligned Yash clips. See the [cache guide](docs/lesson-46-cache.md), [narration evidence](docs/lesson-46-narration.md) and [live acceptance](docs/live-acceptance.md).

Lesson 47 compares native Agent delegation with host-controlled pipeline, fan-out and evaluator queries. The host joins worker starts, completions, owned file reads and independent numeric verdicts; a fair limiter bounds fan-out concurrency. Five API live actions and a one-worker variant passed. The portal includes a worker table, distinct diagrams and three source-aligned Yash clips. See the [orchestration guide](docs/lesson-47-orchestration.md), [narration evidence](docs/lesson-47-narration.md) and [live acceptance](docs/live-acceptance.md).

Lesson 48 compares contrast and guarded security lanes over owned synthetic files, a child environment and a loopback collector. Four local and four provider-backed live API actions pass, along with a shared runner action and active cancellation check. The portal includes a decision table, two diagrams and three verified Yash source clips. See the [security guide](docs/lesson-48-security.md), [narration evidence](docs/lesson-48-narration.md) and [live acceptance](docs/live-acceptance.md).

Lesson 49 runs exact owned child processes for headless CLI/SDK and CI decisions, maps explicit host exit codes, and supervises a one-slot local worker through readiness, backpressure, drain and close. Four local actions, the provider-backed Headless and CI matrix, a shared runner and cancellation checks pass. The portal includes fixed files, process receipts, two diagrams and three source-aligned Yash clips. See the [headless guide](docs/lesson-49-headless.md), [narration evidence](docs/lesson-49-narration.md) and [live acceptance](docs/live-acceptance.md).

Lesson 50 connects a synthetic scoped support conversation, persisted orders/tickets/refunds/audit, one-shot exact refund approval and structured CRM close. The local API and browser lifecycle pass; a bounded provider-backed orders, ticket, denied refund, approved refund and restricted-fork close matrix has passed. The page includes seven explained questions, two diagrams and three source-aligned Yash clips. See the [desk guide](docs/lesson-50-desk.md), [narration evidence](docs/lesson-50-narration.md) and [live acceptance](docs/live-acceptance.md).

Lesson 51 runs sixteen deterministic host assertions and six synthetic stream replays against real host contracts with zero model calls and zero billed cost. A one-case denial mutation, strict streaming API, network-guarded CLI and mobile lab panel make the test boundary visible. The page includes seven questions, two diagrams and three source-bound Yash clips. This lesson is offline only; see the [host suite guide](docs/lesson-51-offline.md) and [narration evidence](docs/lesson-51-narration.md).

Lesson 52 adds a three-case support evaluation lab with synthetic baseline comparisons, 40-decision heuristic calibration, uncertainty metrics, retained reports, guarded baseline promotion and optional paid Agent SDK trials with a separate model judge. Run `uv run python scripts/eval.py` for the free baseline or `uv run python scripts/eval.py --live --budget 1 --trials 1 --demo baseline` for a capped paid probe. A reviewed provider-backed nine-trial run passed all criteria and became the scoped live/model baseline. See the [evaluation guide](docs/lesson-52-evals.md) and [narration evidence](docs/lesson-52-narration.md).
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

Build the three milestone projects in order (understand, evaluate, publish); the
[milestone guide](docs/milestone-projects.md) has the procedure and compares their paths.

## Milestone project: Study Coach

Build a study coach in seven stages: validated questions, live conversations that resume
the SDK session on the server, structured study plans and safe recovery of saved turns.
You implement [mini_projects/study_coach/coach.py](mini_projects/study_coach/coach.py);
the course app runs your file at http://127.0.0.1:8080/coach, so each finished stage
unlocks a feature. Check your work with `uv run agent-lab coach check`. Start with the
[project README](mini_projects/study_coach/README.md).

## Milestone project: Agent Evaluation Studio

Evaluate an SDK tutor on 170 cases in 17 sections: honest run summaries, instruction
variants, bounded live runs with MCP and a specialist reviewer, reviews, evidence export
and a release decision from regression suites. You implement
[mini_projects/evaluation_studio/studio.py](mini_projects/evaluation_studio/studio.py); the
app runs it at http://127.0.0.1:8080/studio. Check with `uv run agent-lab studio check` and
start with the [project README](mini_projects/evaluation_studio/README.md).

## Milestone project: Agent Publishing Studio

Turn one saved SDK answer into Word, PDF, SVG and PNG files in eight stages: validated and
consented live answers, uploaded sources with visible extracted text, strict document and
infographic plans that keep code intact, deterministic builders, the optional documentation
MCP and a PNG style reference. You implement
[mini_projects/publishing_studio/publisher.py](mini_projects/publishing_studio/publisher.py);
the app runs it at http://127.0.0.1:8080/publish. Check with `uv run agent-lab publish check`
and start with the [project README](mini_projects/publishing_studio/README.md).

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

Real provider-backed scenario acceptance is required before advancing when the lesson contract includes a live path. Lesson 51 expressly has no live path. Lessons 16-20 have passed their current live scenario sets (lesson 18 includes a separate native WSL process probe); see [live acceptance evidence](docs/live-acceptance.md). Run `uv run python scripts/lesson_live_smoke.py 17 --live` for the bounded lesson scenarios.

After an SDK upgrade, run the optional provider smoke checks explicitly:

```shell
uv run python scripts/live_smoke.py                      # diagnostics only; no model calls
uv run python scripts/live_smoke.py --live               # lesson 1 and the three milestone services
uv run python scripts/live_smoke.py --live --only elicitation  # lesson 33 with a synthetic demo answer
```

The checks use isolated data folders and reference implementations, stop on the first
failure, and save a JSON report under `.lab-data/live-smoke/`. The four application
checks use per-call budget thresholds totaling $0.35; the elicitation check uses $0.15.
These thresholds are not hard billing caps. The script does not retry failed checks.
Lesson 33's browser workspace offers labelled simulated accept, decline and cancel
choices for the owned Python MCP callback. This older smoke script supplies a fixed
synthetic acceptance to its separate local demonstration server.

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
| `agent_lab/scripted_cli.py` | Scripted stand-in for the Claude Code process: the real `ClaudeSDKClient` runs offline against it (lessons 10, 26, 41) |
| `agent_lab/hooks.py` | PreToolUse policy, PostToolUse audit and `can_use_tool` callbacks shared by live runs and the offline hook lessons (7, 20, 37) |
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

GitHub Actions (`.github/workflows/ci.yml`) runs these checks on Ubuntu and
Windows with Python 3.12 and 3.13, including the browser tests, and fails if the
generated lessons are out of date. CI never makes a paid model call.

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
experiments, Resumed and multi-file checkpoint/session-store experiments, channel approval
delivery and model-driven PR publication need further implementation and live
verification. Adaptations appear in lesson notes and the browser UI.

Lesson 41 teaches the public Python interactive client. Lesson 69 teaches Python
desktop embedding. The legacy runtime, Node dependencies, scripts, CI templates
and generated lab folders have been removed from the active project.
The recovery ZIP described in earlier migration notes is absent from this checkout.
The [reference parity report](docs/reference-parity.md) pins the available TypeScript
repositories and records all 75 lesson contracts, shared feature gaps and verification
limits. The app, tests and documentation builder do not require a recovery archive.

### Learning features ported from the Student Rebuild

The lesson workspace, workbook, quizzes, learning paths, AI Tutor, automatic checks,
appearance controls and the four visual guides (`public/visual-guides/`) follow
[Udemy-Claude-Agent-SDK-Student-Rebuild](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild).
Lesson guides and quizzes were rewritten for the Python exercises in this
repository; every automatic check is tested against the actual offline evidence.
The Rebuild's TypeScript code tours are replaced by Python code tours
(`agent_lab/content/code_tours.json`): 3 to 5 reviewed steps per lesson, bound to the
SHA-256 of the concept code, so a test fails and the tour is hidden when the code changes
without a review. Its recorded narration (a paid TTS service) is not included; Read aloud
uses the browser's built-in speech instead.

## References

- [Official Python Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
- [Python API reference](https://code.claude.com/docs/en/agent-sdk/python)
- [NiceGUI](https://nicegui.io/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
