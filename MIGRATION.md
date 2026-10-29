# Python migration status

The Python edition is runnable. The legacy app source, Node dependencies, bridge,
generated lab folders and Node CI templates have been removed from the active
project. Feature parity work remains. The pinned TypeScript comparison and the
75-lesson inventory are in [reference parity](docs/reference-parity.md).

## Implemented

- Python package, uv lockfile and local virtual environment.
- FastAPI JSON/SSE/WebSocket API and a NiceGUI UI with all 75 lesson ids.
- 75 standalone Python entry points and rewritten lesson Markdown.
- Native Python SDK query, interactive sessions, tools, hooks, permissions,
  structured output, input streaming, subagents, Skills and project settings.
- Local host exercises for all learning objectives, labelled independently
  from live model execution.
- Python MCP stdio servers, actual MCP elicitation, remote client, browser
  server and explicit notification adapters.
- SQLite tenant boundaries, approvals, bounded task graphs, host journals,
  retrieval, analysis, document generation and headless review examples.
- Live engineering fixture: a lead plans, developers propose source in
  dependency waves, the host validates and tests it, and a reviewer evaluates
  it. API calls are explicitly enabled and remain unverified against a real
  paid model in this environment.
- Python companion fixtures, document Skill command and plugin manifests.
- Offline tests, SDK configuration tests, MCP tests, lint/type checks and
  desktop/mobile browser checks.
- Completed learner implementations of the Study Coach (7/7), Evaluation Studio
  (7/7) and Publishing Studio (8/8), with separate reference implementations.
- Reviewed Python source tours for all 75 lessons; browser Read aloud remains
  separate from the reference's prerecorded TypeScript narration.
- Seven-section written Learning Guides for all 75 lessons: explicit Start/Resume,
  real targets, tab-change pause, minimize/close, saved position and route-aware
  navigation. Each guide uses its own lesson content; recorded narration is pending.
- On 29 October 2026, bounded live checks passed for lesson 1, Study Coach,
  Evaluation Studio, Publishing Studio and lesson 33's elicitation callback on
  SDK 0.2.174. These selected checks do not establish all-lesson live parity.

- A dedicated My Learning workspace and Setup page: manual path progress, saved notes,
  practice quiz feedback, challenge-attempt history, search/filtering and explicit
  guide-section resume. Existing progress keys and manual completion rules are preserved.

## Remaining before declaring the whole migration complete

1. Port the original per-lesson controls and comparison scenarios. The current
   UI uses a common exercise form; it does not replicate all original panels.
2. Replace simplified offline demonstrations with the original workshops'
   full business behavior where needed, especially approvals, durable jobs,
   multi-tenant sessions, eval calibration and scheduling.
3. Add full SDK-native checkpoint/rewind, session-store/resume experiments,
   hook lifecycle comparisons, process-spawning comparisons, cloud-provider
   proxy experiments and token/cache measurement scenarios.
4. Integrate remote MCP OAuth, browser automation and channel delivery into
   their browser lessons rather than offering standalone adapters alone.
5. Complete the original PR-fix and engineering-team worktree/merge/recovery
   pipeline. The live teaching fixture validates bounded source proposals;
   it does not yet reproduce the original general repository workflow.
6. Expand live verification beyond the selected smoke checks to the remaining
   lesson-specific scenarios, connected integrations and cloud providers. The
   installed 0.2.174 SDK's bundled Windows executable was used by the selected
   checks; executable detection alone does not verify an API response.
7. Verify browser/native startup on supported operating systems and build
   the container in an environment with Docker.
8. Complete recorded Python narration, remaining shared navigation/troubleshooting
   destinations and reference question/excerpt coverage. Supply separate student
   starter templates alongside the now-completed milestone apps.

## Legacy cleanup

The active project uses the Python stack exclusively. Companion commands point
to Python fixtures, CI templates run Python checks, and lesson documentation is
rebuilt from `curriculum.json` without opening the recovery archive. Lessons 41
and 69 have filenames matching their Python topics. Third-party browser assets
inside installed Python dependencies are still required by NiceGUI.

## Recovery

Earlier notes described `.migration/original-typescript.zip` and an accompanying
manifest. Neither file is present in this checkout, so their contents and hashes
were not reverified in the current audit. The pinned Student Rebuild and original
Learning Platform v2 repositories in [reference parity](docs/reference-parity.md)
are the available comparison sources. Keep any separately held recovery archive
until its provenance and migration coverage have been reviewed.

The machine-readable Python curriculum is `curriculum.json`. Lesson-specific
adaptations are maintained in `agent_lab/curriculum.py` and rendered into the
browser and each `Tab*.md` tutorial.
