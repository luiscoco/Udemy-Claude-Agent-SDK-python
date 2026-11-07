# Lesson 39: Project configuration root

`cwd` selects the checkout where the SDK works. The CLI's `--project-config-root` flag can select another checkout for project configuration. Project and local setting sources must still be enabled. The lesson verifies each path independently with SDK initialization, discovered commands and a SessionStart hook log; the model's answer is discussion material, not proof of configuration origin.

## Owned fixture

Each run creates a fresh Git repository with trusted, branch and docs worktrees under lesson storage. Trusted and branch carry distinct `.claude/settings.json`, `.claude/settings.local.json`, command, skill and CLAUDE.md markers. Docs has no `.claude` directory. Git commands use local identity and ignore global/system configuration. The hook records only run and session IDs, event, marker, project directory, cwd, setting markers and PID into an owned JSONL file. The host hashes fixture files before and after the probe.

The browser selects only fixed `cwd`, configuration-root and source choices. No browser field accepts a raw path, command, environment variable or URL. The normal live origin probe enables no tools, uses isolated CLI configuration, an empty MCP server set, at most three turns, a $0.10 SDK threshold and a 60-second route deadline.

## Actions

- `POST /api/c39/dry` accepts `{}` and captures the installed SDK's actual CLI argv for omitted, absolute trusted and relative roots using an inert process. It neither starts the CLI nor loads configuration.
- `POST /api/c39/where` runs one selected prepared or consented live origin probe.
- `POST /api/c39/takeover` compares branch cwd with trusted or omitted root. The branch may allow Bash, but the host PreToolUse guard accepts only one generated nonce command; a fallback callback denies permission requests. The report distinguishes trusted tool unavailability from an attempted execution denial.
- `POST /api/c39/try` runs valid origin probes or a credential-free startup probe for fixed relative, missing or file roots. Startup sets an unreachable loopback provider base and reports the actual CLI exit and stderr.
- `GET /api/c39/code` returns three current source excerpts.

Prepared mode creates real local fixtures and labels authored SDK init/result observations. Live mode must show one successful SDK terminal with matching session ID, exact init cwd, selected hook and command origin, unchanged fixture hashes and normal closure. The takeover case also checks exact tool call/result correlation, fallback activity and a fresh nonce proof file. A missing, foreign, failed, interrupted or altered observation stays **Needs review**.

The docs worktree has no `.claude` directory, but an omitted-root live probe may still discover commands through Git or ancestor configuration. Its command inventory must be inspected; absence of a docs-local directory alone does not certify an empty configuration. The observed docs/omitted control stayed **Needs review** because it listed project commands despite no hook log.

The trusted root can remove Bash from init tools. When that happens, no Bash call was attempted; the check certifies tool unavailability, with no proof file or host permission traffic. The omitted-root branch case requires an actual exact Bash call, successful tool result and matching proof file. CLAUDE.md marker text is not treated as evidence of model memory influence.
