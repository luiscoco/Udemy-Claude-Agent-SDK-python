# Agent Evaluation Studio milestone project

Evaluate an SDK tutor on 170 cases in 17 sections, from a first query to production
readiness. You implement the contracts in [studio.py](studio.py); the course app runs
**your** file at <http://127.0.0.1:8080/studio>, so every stage unlocks a feature.

| Stage | Prompt | STAGE value |
|---|---|---|
| M08 | [Browse the roadmap](prompts/m08-browse-the-roadmap.md) | 1 |
| M09 | [Summarize a run honestly](prompts/m09-summarize-a-run.md) | 2 |
| M10 | [Compare baseline and guided instructions](prompts/m10-compare-instructions.md) | 3 |
| M11 | [Add one bounded live run](prompts/m11-add-a-live-run.md) | 4 |
| M12 | [Add external knowledge with MCP](prompts/m12-add-external-knowledge.md) | 5 |
| M13 | [Record reviews and export evidence](prompts/m13-review-and-export.md) | 6 |
| M14 | [Decide a release from regression suites](prompts/m14-release-decision.md) | 7 |

## Run and check

```shell
uv run agent-lab serve                       # open http://127.0.0.1:8080/studio
uv run agent-lab studio check                # checks YOUR studio.py, stage by stage
uv run agent-lab studio check --reference    # checks the reference; never marks your work done
```

Raise `STAGE` after each stage passes; later tests are skipped until you do. On the page,
switch between **Your studio.py** and **Reference**; **Reload my code** picks up edits.

## How it fits together

- `studio.py` (yours) and `reference/studio.py` hold the same functions: pure Python over
  plain dicts, so you can test them without the SDK. `cases.json` holds the 170 cases.
- `agent_lab/evaluation_studio.py` is the server. It converts real SDK messages into the
  dicts your `summarize_run` reads, owns the API key, and keeps the latest 40 runs, reviews
  and suites in `.lab-data/evaluation-studio/state.json`.
- Prepared runs are recorded fixtures with zero model calls. Live runs are optional: they
  need `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true` in `.env`, fresh consent for every run
  and separate consent for an MCP connection. Suites run prepared fixtures only.
- Before each live run, the server resolves every MCP hostname and requires all returned
  IPv4 and IPv6 addresses to be public unicast addresses. Failed or empty DNS lookups and
  lookups taking over five seconds stop the run before the SDK starts. Prepared runs and
  the stage checks do not perform DNS lookups.
  This is a preflight check: the Claude CLI resolves names again and handles redirects,
  so it does not prevent DNS rebinding or redirects to private addresses. Deployments
  requiring connection-time enforcement also need network egress controls.

A plausible answer is not evidence: the run result, the timeline and your review are.
