# Lesson 32: Plan mode

The SDK starts with `permission_mode="plan"` and no model tools. It returns a structured task proposal. The host validates exact task IDs, file ownership, dependencies and paths. A valid proposal with the **selected host approval control** triggers `set_permission_mode("default")`, a confirmation turn on the same session, and two deterministic host workers. A valid plan held for review and a duplicate-owner plan stay in plan mode and start no workers. The automated approval selection is not a person's review during the run.

The original `plan_mode` exercise teaches the sequence through a real `ClaudeSDKClient` connected to `ScriptedCLI`. Its timeline is a fixture. The enhanced experiment adds real provider-backed SDK observations in live mode and labelled SDK fixtures in offline mode. The automatic check requires matching initialized and terminal sessions, the observed plan/default permission modes, a structured call/result for each turn, the expected host verdict and exact worker hashes. Recorded missing or mismatched evidence needs review.

## Live acceptance

On 3 November 2026, all three bounded provider-backed variants passed:

| Case | Mode and host outcome | Stream reported USD |
|---|---|---:|
| Valid approved | Plan then default; two workers | 0.014248 |
| Valid review-only | Plan; no workers | 0.004673 |
| Duplicate rejected | Plan; no workers | 0.003916 |

Final run stream-reported cost: **$0.022837**. Report: `.lab-data/lesson-live-smoke/lesson-32-20261103T131201923828Z/report.json`. Two earlier live runs preceded the final exact-worker check. The first probe finished but failed the acceptance check because it counted only one internal `StructuredOutput` call across two turns; it reported $0.012218 at `.lab-data/lesson-live-smoke/lesson-32-20261103T130025038240Z/report.json`. The preceding passing run reported $0.020865 at `.lab-data/lesson-live-smoke/lesson-32-20261103T130702247755Z/report.json`. Combined stream-reported cost across all three runs: **$0.055920**.

The live stream demonstrated both SDK permission modes and the same session. These fixed host workers do not establish a general approval or model-editing workflow. The SDK's [Python client method](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py) defines `set_permission_mode` for connected clients.
