# Python migration status

The Python edition is runnable. The legacy app source, Node dependencies, bridge,
generated lab folders and Node CI templates have been removed from the active
project. Feature parity work remains; keep the recovery snapshot for reference.

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
6. Verify paid live calls with API or cloud credentials. The Windows SDK source
   package has no bundled executable; native Claude Code 2.1.292 is now installed
   and detected on this machine. Executable detection does not verify credentials
   or a paid model response.
7. Verify browser/native startup on supported operating systems and build
   the container in an environment with Docker.

## Legacy cleanup

The active project uses the Python stack exclusively. Companion commands point
to Python fixtures, CI templates run Python checks, and lesson documentation is
rebuilt from `curriculum.json` without opening the recovery archive. Lessons 41
and 69 have filenames matching their Python topics. Third-party browser assets
inside installed Python dependencies are still required by NiceGUI.

## Recovery

`.migration/original-typescript.zip` preserves the original app and Markdown,
with `.migration/original-manifest.json` recording SHA-256 hashes. The archive
was read back and verified before original documents were rewritten. Secrets,
dependency directories and caches were excluded.

The machine-readable Python curriculum is `curriculum.json`. Lesson-specific
adaptations are maintained in `agent_lab/curriculum.py` and rendered into the
browser and each `Tab*.md` tutorial.
