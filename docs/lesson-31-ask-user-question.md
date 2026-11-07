# Lesson 31: AskUserQuestion

The model calls `AskUserQuestion` with one fixed teaching-style question. The host validates the complete question shape, then returns the selected **simulated host answer** through `PermissionResultAllow(updated_input={..., "answers": ...})`. The selected answer comes from the lesson control, not a real user click. No other tool is available.

The enhanced experiment records the SDK tool call and result, the host callback, the initialized session and final result. Its automatic check passes only when those observations agree. An assistant sentence alone does not establish that the question was asked. Offline runs label SDK events as fixtures and execute the actual host callback. Recorded missing or mismatched evidence needs review.

The original `questions` exercise also demonstrates Pydantic shape failures: one option, an oversized header and an unknown field. Its answer is an explicitly scripted fixture.

## Live acceptance

On 3 November 2026, two bounded provider-backed runs passed. Each produced one `AskUserQuestion` SDK call/result pair, an accepted host callback with the selected answer, a matching initialized and terminal session, and a closed client.

| Selection | Result | Stream reported USD |
|---|---|---:|
| Concise | Passed | 0.01089385 |
| Detailed | Passed | 0.00535515 |

Combined stream reported cost: **$0.01624900**. Evidence: `.lab-data/lesson-live-smoke/lesson-31-20261103T123556860095Z/report.json`. The result verifies this fixed question and the two automated answer variants. It does not establish how a person would select an answer in a deployed UI.
