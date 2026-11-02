# SDK experiments and assessments: lessons 2–10

This block applies the Lesson 1 pattern to nine more lessons: lesson-specific controls, request validation before a run starts, bounded evidence checks, positive and negative scenarios, seven explained questions and three exact source excerpts with line references and questions. Existing question positions are preserved, including all three original calculator questions. Saved answers, challenge attempts, guide positions and the four manual review checkboxes retain their existing format.

## Try the lessons

Open a lesson, choose **Run the exercise**, keep **Offline Python exercise** and start with the default **Lesson experiment** controls and **Passing example**. Then compare **Missing required evidence** and **Mismatched identity**. A completed local replay is not the same thing as a successful SDK outcome. The two negative cases should show **Needs review**.

The selected experiment is the primary result. The existing standard Python example is retained in a collapsed, separate reference section for compatibility. Offline prompts are validated and recorded; they do not generate a model answer. Local reads, writes, arithmetic and hook callbacks really execute against owned fixtures. Correlation identities are explicitly labelled as recorded fixtures. Session and stop experiments use the official Python client with a scripted transport, without starting Claude Code or calling a model.

| Lesson | Controls and observations | Bounded automatic check |
| --- | --- | --- |
| 2. Options | Omitted/custom model, omitted/custom/preset system instruction, partial-message flag, optional omission of SDK turn and budget thresholds; actual SDK options are displayed, including after failures. | The actual echo matches the selected inputs, initialization was observed and the stream succeeded. This does not grade limit enforcement or answer quality. |
| 3. Built-in tools | Read, Glob, Grep or the fixed `python --version` operation; a separate host-permission checkbox; actual local result and before/after file hash. | A configured and announced tool call has one successful result with the same call ID, and the stream succeeds. File effects and prose are separate observations. |
| 4. Permissions | Deny, Allow, Redirect or Ask me; owned `draft.txt`/`notes.txt` targets and `approved.txt` redirect. The dialog includes **Cancel run**. | Supported denied Write/Edit targets match run and call identity, and their hashes or absence agree at denial and completion. Missing snapshots cannot be mistaken for observed absence. This does not observe every intermediate filesystem event. |
| 5. Custom tools | Editable offline calculator arguments, invalid-argument and ambiguous-handler scenarios; host validation, handler events and call/result identities. Live arguments come from the agent's actual call. | A handler uniquely matches name and arguments, then a successful result by call ID, with successful parent completion. Invalid arguments execute no selected handler; ambiguous matches need review. |
| 6. Sessions | Same-client continuation, a new client with the previous successful ID, or a fresh client. Visible previous/follow-up identities and outgoing resume value. | Matching successful session identity; explicit resume additionally sends that ID and observes it in the next initialization. Fresh sessions and answer recall are separate comparisons. |
| 7. Hooks | Teaching PreToolUse and PostToolUse toggles; observe, block or rewrite a Read to `alternate.txt`. An independent host path guard stays registered. | An enabled post-use hook matches a successful call/result by ID and name, with successful completion. Guard decisions and rewritten contents require separate inspection. |
| 8. Subagents | Reviewer tool scope and model, actual AgentDefinition, foreground configuration and parent/child message grouping. Offline review uses a local function rather than a model worker. | An Agent/Task delegation has a successful result by the same call ID and a successful parent outcome. Report quality is manual. |
| 9. System prompts | Omitted, custom, preset, dynamic-boundary or owned CLAUDE.md/project variants, while keeping the user question fixed. | The actual system representation and project-setting selection match, and the stream succeeds. Adherence and cache savings are not inferred from configuration. |
| 10. Structured output | Editable offline Summary JSON, schema failures and a separate interrupt/continue versus abort comparison. | The host accepts `structured_output` under the course schema and the stream succeeds. Factual accuracy and the stop comparison are not certified by this check. |

## Shared entry points

The browser, existing `/api/lessons/{id}/run`, stream/WebSocket routes and CLI use the same lesson-aware validator. Experiment values are supplied under `lesson_options`; unknown fields, unsupported choices, wrong numeric types and non-finite calculator inputs are rejected before task/workspace creation. Recorded negative scenarios are rejected in live mode.

The CLI accepts the lesson's offered scenario, for example:

```shell
uv run agent-lab lesson 5 --scenario invalid-arguments
uv run agent-lab lesson 10 --scenario stop-control
uv run agent-lab lesson 6 --lesson-options-file session-options.json --follow-up "What label did I mention?"
```

For the last example, `session-options.json` contains `{"strategy":"resume"}`. An explicit options file avoids shell-dependent JSON quoting. Other lessons retain their existing default prompts and limits.

In **Python source**, expand **How the offline lab checks this concept** to inspect the actual configuration function, the selected host experiment and the shared evaluator. Every excerpt is read from the current source and shows its exact path and line range. Questions, guides and source inspection make no model call. Save an explanation and quiz answers in **Learn**, reload, or return through **My Learning** to resume your work. Automatic checks never complete manual review.

## Verification and reference scope

Tests cover all nine positive cases and missing-evidence/identity failures, typed input rejection before effects, permission writes/redirects and cancellation while waiting, configured hooks and immutable path guards, session strategies, schema rejection and stop comparison, and actual SDK option/callback assembly through injected streams. Browser checks visit every lesson on desktop and phone, save/reload work, inspect three source excerpts and exercise the permission dialog. The existing Learning Guide tests continue to check real red outlines and clipping.

The teaching contracts were read at the pinned [Student Rebuild commit](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/tree/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts). This is an adapted Python block, not a claim of complete platform parity. The custom-tool example uses this course's calculator rather than task-file tools; structured output uses the course Summary schema. Shell access is limited to the displayed fixed command. Session comparisons are inside one owned run; durable cross-browser/cross-run session ownership remains separate work. The stop comparison is a scripted-transport experiment; live Cancel aborts the run, and a persistent live interrupt/send/end interface remains pending. Python's supported system-prompt representations are used rather than unsupported content-block options. Reference route aliases, shared navigation/tab order, authored media and recorded narration remain tracked in the [parity inventory](reference-parity.md). No paid model call is needed for this release's automated verification.
