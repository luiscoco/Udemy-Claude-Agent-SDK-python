# Live lesson acceptance

The user requires real provider-backed scenarios before advancing to the next lesson. This rule is recorded in [AGENTS.md](../AGENTS.md). Offline fixtures and injected live clients remain useful regression checks, but do not satisfy this requirement.

## 3 November 2026

Verified with Python SDK 0.2.174, Claude Code 2.1.310 and claude-haiku-4-5. These are actual provider calls through the application's run service and host policy, in isolated disposable workspaces. The CLI needed network-enabled execution; the restricted attempt initialized but timed out without a final usage report.

| Lesson | Live scenario | Acceptance | Reported USD |
|---|---|---|---|
| 16 | isolated | Passed | 0.008028 |
| 16 | project | Passed | 0.008866 |
| 16 | project-local | Passed | 0.008544 |
| 16 | inherited-demo | Passed | 0.007972 |
| 17 | rewind | Passed | 0.011220 |
| 17 | inspect | Passed | 0.012195 |
| 17 | checkpointing-disabled | Passed | 0.011727 |
| 17 | replay-disabled | Passed | 0.012044 |

Lesson 17's first network-enabled attempt exposed a prompt defect: the model omitted the required final newline, so the exact-content guard denied its writes. That attempt stopped at the turn limit and reported $0.018800. The prompt now supplies a JSON-encoded string and requires Read before Write. The guard still requires exact content. Regression tests and a fresh full live scenario set passed after the fix.

The eight passing cases reported $0.080596 in total; including the earlier provider failure, reported costs total $0.099396. The restricted attempt had no final cost report and is not assigned a fabricated zero.

For lesson 17, native rewind acknowledged the captured original user-message UUID and restored the changed file's original hash. Inspect-only and disabled-feature variants completed successfully while intentionally failing the restoration automatic check; acceptance verifies no rewind was submitted and the edited state remained. File history and external side effects are outside this criterion.

For lesson 16, the selected sources, actual child environment probe, real Read result, matching successful parent session and closure passed. These scenarios do not inspect the CLI's resolved project/local environment or establish every precedence rule. Resumed/multiple checkpoints, more files and full reference certification also remain separate.

Run the supported scenario sets explicitly:

```shell
uv run python scripts/lesson_live_smoke.py 17 --live
uv run python scripts/lesson_live_smoke.py 16 --live
```

Without --live the runner lists cases and makes no provider call. Each scenario uses four turns, a 120-second host deadline and a $0.10 SDK threshold; thresholds are not hard billing caps. The runner stops on the first failed acceptance and saves a report under `.lab-data/lesson-live-smoke/`. It does not retry failed cases automatically.

Raw passing reports:

- Lesson 16: `.lab-data/lesson-live-smoke/lesson-16-20261103T060048530940Z/report.json`
- Lesson 17: `.lab-data/lesson-live-smoke/lesson-17-20261103T055853447513Z/report.json`


## Lesson 18: 3 November 2026

Three actual provider-backed application scenarios passed: inside Read ($0.008337), outside denial ($0.007997) and protected-file denial ($0.007781). Each includes an actual host child-process counterexample, matching Read/decision/result identities, parent success and closure. Report: `.lab-data/lesson-live-smoke/lesson-18-20261103T062440134731Z/report.json`.

The separate actual Linux/WSL native SDK sandbox probe also passed ($0.01256825): the local server was reachable outside the sandbox, the command wrote its workspace file, sibling-file writes were denied and direct loopback access was blocked. SDK call/result IDs, host guard and parent success matched, outside bytes stayed unchanged and the client closed. Report: `.lab-data/native-sandbox-live/20261103T062141937149Z/report.json`.

Lesson 18's reported total is $0.03668325. Native Windows is not supported and fails validation before a paid call; that platform gate is not described as observed OS enforcement. Ubuntu's existing bubblewrap/socat and a workspace-local Linux SDK 0.2.174 installation supplied the native runtime. macOS and wider network policy acceptance remain separate. No system package installation or unsandboxed retry was used.


## Lesson 19: 3 November 2026

All four actual provider-backed session catalog cases passed with a fresh tools-disabled session per case. Each client closed before the public SDK catalog operations ran in a child with a private config/project and matching original prompt digest.

| Live case | Observed effect | Reported USD |
|---|---|---|
| inspect-page | Persisted session, correct session/message pagination and unchanged transcript | 0.001100 |
| rename-tag | New title/tag, changed metadata bytes, preserved visible messages and UUIDs | 0.000914 |
| fork | New session and message UUIDs, preserved content and unchanged original bytes | 0.001247 |
| delete-owned | Only the newly created owned transcript absent from file, metadata and catalog | 0.001329 |

Reported total: $0.004590. Report: `.lab-data/lesson-live-smoke/lesson-19-20261103T065136666900Z/report.json`. The actual recorded observations were re-evaluated successfully after the evaluator was tightened to reject incomplete digests, missing retained metadata and inconsistent operation effects; no extra provider call was needed for that re-evaluation.

These cases verify native local SDK file operations on actual CLI transcripts. They do not certify resumed fork conversations, external session stores, multi-tenant authorization or full reference parity. SDK catalog calls themselves do not call a model. Deleting the disposable transcript does not wipe the run's evidence or workspace.


## Lesson 20: 3 November 2026

Seven actual provider-backed hook cases passed with one fixed owned Read per case. Native callback observations, tool call/result IDs, parent identity, file markers and hashes, and client closure matched the configured behavior.

| Live case | Observed outcome | Reported USD |
|---|---|---|
| allow-audit | Original fixture marker and successful audit | 0.007431 |
| deny | Pre-hook denial, error result and no successful audit | 0.007118 |
| rewrite | Actual alternate input target and alternate marker in post-hook and result | 0.007127 |
| tool-error | Permitted missing-file Read and PostToolUseFailure | 0.007507 |
| callback-error | Caught synthetic callback fault returned denial | 0.007416 |
| nonmatching-matcher | Teaching hook absent; independent guard and normal success audit observed | 0.007043 |
| success-audit-disabled | Configured control observed; full learning check intentionally needs review | 0.006728 |

Reported total: $0.050370. Report: `.lab-data/lesson-live-smoke/lesson-20-20261103T073426208662Z/report.json`. All seven recorded native observations also passed re-evaluation after callback identity, audit digest, fixture-marker and lifecycle-order requirements were tightened. That re-evaluation made no additional provider call.

UserPromptSubmit and observe-only Stop matched the parent session. Matching pre-hook relative ordering was not assumed. These cases do not certify arbitrary callback exceptions/timeouts, every hook kind, subagent interleaving or OS process isolation. The contained callback error is a deliberately caught teaching fault, not an unhandled SDK failure. The live runner requires observation_passed even for the intentionally incomplete-audit case, so a missing workflow cannot pass merely because its full check is false.


## Lesson 21: 3 November 2026

Three provider-backed slash command cases passed. Both enabled templates appeared in the actual SDK command inventory and produced a matching `Read` of the owned note and their selected response marker. The no-project control had no `lesson-summary` inventory entry and correctly needed review for invocation. All cases had matching initialized/final session IDs, unchanged fixture hashes and closed clients.

| Live case | Observed effect | Reported USD |
|---|---|---|
| summary | Discovered project command, matching note Read and Summary marker | 0.010775 |
| quiz | Discovered same command with Quiz marker and matching note Read | 0.011010 |
| project-disabled | Command absent from SDK inventory; invocation criterion false | 0.012923 |

Final reported total: $0.034707. Report: `.lab-data/lesson-live-smoke/lesson-21-20261103T083027019483Z/report.json`. These were repeated after tightening the marker evaluator to count assistant and terminal text only. The initial three-case run also passed and reported $0.034573; its report is `.lab-data/lesson-live-smoke/lesson-21-20261103T082338709010Z/report.json`. Combined reported cost for both runs: $0.069280. The records hold SDK inventory, stream identities and marker labels, without arbitrary command or private file contents.


## Lesson 22: 3 November 2026

Six provider-backed comparisons passed on fresh SDK connections with no model tools. The owned `CLAUDE.md` hash stayed unchanged, initialized and final session IDs matched, automatic memory was disabled in each private CLI config, and no `MEMORY.md` appeared there. The response followed the selected project rule under both tested system prompt modes; disabling project settings yielded `UNKNOWN` under both.

| Live case | Observed answer | Reported USD |
|---|---|---|
| project-alpha | `PROJECT_ALPHA_22` | 0.006580 |
| project-beta | `PROJECT_BETA_22` | 0.006310 |
| no-project | `UNKNOWN` | 0.006479 |
| custom-prompt | `PROJECT_ALPHA_22` | 0.001481 |
| custom-beta | `PROJECT_BETA_22` | 0.001529 |
| no-project-custom | `UNKNOWN` | 0.001485 |

Final run total: $0.023864. Report: `.lab-data/lesson-live-smoke/lesson-22-20261103T085116659245Z/report.json`. The first four-case attempt reported $0.021081 and correctly failed its outdated custom-prompt expectation; its report is `.lab-data/lesson-live-smoke/lesson-22-20261103T084911391854Z/report.json`. Combined reported cost: $0.044945. This supports a bounded behavioral conclusion, not full resolved-prompt visibility or a global absence of memory files.


## Lesson 23: 3 November 2026

Four provider-backed plugin scenarios passed on fresh SDK connections. Both namespaced commands appeared in actual SDK inventory and produced their selected markers. The Skill run had exactly one `Skill` call for `python-teaching:python-example`, one matching successful tool result and its marker. With plugin loading disabled, the command was absent from SDK inventory while the owned files remained unchanged. Initialized/final sessions matched and clients closed in all cases.

| Live case | Observed effect | Reported USD |
|---|---|---|
| explain-command | Namespaced command discovered and Explain marker returned | 0.006183 |
| quiz-command | Namespaced command discovered and Quiz marker returned | 0.006585 |
| skill | Named Skill call/result paired and Skill marker returned | 0.009137 |
| plugin-disabled | Namespaced command absent from SDK inventory | 0.006699 |

Reported total: $0.028603. Report: `.lab-data/lesson-live-smoke/lesson-23-20261103T091053192079Z/report.json`. This verifies only the fixed, reviewed local plugin and the pinned SDK/CLI behavior; it does not authorize arbitrary third-party plugins or certify marketplace and reload paths.


## Lesson 24: 3 November 2026

Five provider-backed structured proposal cases passed. The SDK emitted one `StructuredOutput` call with a matching successful result for each proposal. The host accepted and executed only the approved exact two-task plan, producing the expected hashes for `src/tags.py` and `src/search.py`. The review-only plan was accepted without workers. Duplicate ownership, dependency cycle and outside-scope proposals received specific host rejections and started no workers. Initialized/final sessions matched and clients closed.

| Live case | Host verdict and effect | Reported USD |
|---|---|---|
| valid-execute | Accepted; T1/T2 fixed files written and hashed | 0.003925 |
| valid-review-only | Accepted; no worker started | 0.003881 |
| duplicate-rejected | Duplicate owner; no worker started | 0.003852 |
| cycle-rejected | Dependency cycle; no worker started | 0.003717 |
| outside-rejected | Outside owned scope; no worker started | 0.004052 |

Final run total: $0.019427. Report: `.lab-data/lesson-live-smoke/lesson-24-20261103T094208918743Z/report.json`. The first five-case run passed before the StructuredOutput identity-pair criterion was tightened and reported $0.017880; its report is `.lab-data/lesson-live-smoke/lesson-24-20261103T094006414775Z/report.json`. Combined reported cost: $0.037307. These runs verify a fixed teaching plan and deterministic host worker; they do not authorize arbitrary model-generated code or prove a general-purpose harness safe.

## Lesson 25: 3 November 2026

Three provider-backed SDK MCP tool cases passed. Each run had one correlated tool call/result and callback. The 5,168-character source yielded 653 characters at the 600-character bound and 253 at the 200-character bound, including the exact removal marker. The omitted-summary control observed a successful bounded tool run and correctly requested review for lost host progress state. No `PreCompact` event was observed in these short sessions.

| Live case | Observed result | Reported USD |
|---|---|---|
| default-bound | 600-character prefix, marker, retained summary; passed | 0.009913 |
| tight-bound | 200-character prefix, marker, retained summary; passed | 0.009383 |
| summary-omitted | Bounded tool observed; missing summary needs review | 0.009283 |

Total reported cost: $0.028578. Report: `.lab-data/lesson-live-smoke/lesson-25-20261103T100442810016Z/report.json`. This verifies bounded delivery and the host summary control, not actual automatic compaction.

## Lesson 26: 3 November 2026

Three provider-backed control-method cases passed. Both switch cases completed two turns on one initialized session, acknowledged `set_model` and `set_permission_mode`, and rejected a query after disconnect. The Sonnet case observed `claude-haiku-4-5-20251001` on the first turn and `claude-sonnet-5-5` on the second. The interrupt case issued `interrupt()` after an actual streamed text delta and received `error_during_execution` on the same session; the generic subtype does not identify the cause by itself.

| Final live case | Observed result | Reported USD |
|---|---|---|
| current-plan | Same model, plan mode acknowledged, two successful turns | 0.010440 |
| sonnet-default | Sonnet observed on second turn, default mode acknowledged | 0.012081 |
| interrupt | Text delta, interrupt acknowledged, error terminal, post-close rejection | 0.000000 |

Final run reported total: $0.022521. Report: `.lab-data/lesson-live-smoke/lesson-26-20261103T103011672042Z/report.json`. The earlier three-case run passed before the text-delta trigger was tightened and reported $0.031666; its report is `.lab-data/lesson-live-smoke/lesson-26-20261103T102833742154Z/report.json`. Combined stream-reported cost: $0.054187. The interrupted turn's zero stream cost does not prove zero provider-side billing.

## Lesson 27: 3 November 2026

Two provider-backed host-task cases passed. In each, the watcher started before a real SDK query, remained pending during it, and completed its `finally` cleanup after the host awaited it and before client disconnect. The SDK result matched the initialized session.

| Live case | Host watcher outcome | Reported USD |
|---|---|---|
| cancel-await | Cancelled, awaited, cleaned up | 0.005910 |
| release-await | Released, awaited, cleaned up | 0.005933 |

Combined stream-reported cost: $0.0118425. Report: `.lab-data/lesson-live-smoke/lesson-27-20261103T104719912259Z/report.json`. These cases verify host `asyncio` task ownership around a real SDK turn. They do not exercise CLI-managed task IDs or `stop_task`.

## Lesson 28: 3 November 2026

Three provider-backed SDK MCP refund cases passed. Every tool call had a matching result ID and handler callback. The host retried only transient statuses, used the fixed backoff, stopped on permanent rejection, and stopped after three transient attempts without confirmation. The in-memory key was applied once in the recovery and exhaustion paths and never in the permanent path. No payment service was contacted.

| Live case | Host decision | Reported USD |
|---|---|---|
| recover | Two retries, then confirmed already applied | 0.013767 |
| permanent-stop | Rejected after one call, no ledger effect | 0.008482 |
| transient-exhausted | Stopped after three transient calls, one ledger effect, unconfirmed | 0.013440 |

Combined stream-reported cost: $0.0356889. Report: `.lab-data/lesson-live-smoke/lesson-28-20261103T110940812923Z/report.json`.

## Lesson 29: 3 November 2026

Two provider-backed typed image-input cases passed. The host sent one 256×256 PNG from its isolated workspace as an `image/png` base64 block alongside a text question. Both 851-byte files retained their hashes, the SDK results matched initialized sessions, and the observed answers changed with the controlled image color.

| Live case | Observed answer | Reported USD |
|---|---|---|
| red-image | `RED` | 0.006355 |
| blue-image | `BLUE` | 0.006415 |

Combined stream-reported cost: $0.012770. Report: `.lab-data/lesson-live-smoke/lesson-29-20261103T113124278022Z/report.json`. These responses are behavioral evidence of image input, not direct visibility into the provider's internal vision processing.

## Lesson 30: 3 November 2026

The first provider-backed probe failed: the CLI initialized with an empty tool inventory, so no `TodoWrite` hook fired. The model produced a tool-call-shaped string instead of a real tool call. After setting `CLAUDE_CODE_ENABLE_TASKS=0` only in this lesson's isolated child environment, the CLI listed `TodoWrite` and all four final cases passed. Actual SDK call/result IDs, pre-hook decisions and accepted post-hook commits matched in each case. Denied proposals did not commit.

| Final live case | Hook and ledger result | Reported USD |
|---|---|---|
| valid-progress | Three accepted calls and commits; Read/Verify completed, Publish pending | 0.021496 |
| skip-rejected | One denied call, no commit | 0.006804 |
| parallel-rejected | One denied call, no commit | 0.006871 |
| reopen-rejected | Two accepted commits, then denied reopening | 0.017337 |

Final run reported total: $0.05250865. Report: `.lab-data/lesson-live-smoke/lesson-30-20261103T121527136864Z/report.json`. The failed first probe reported $0.00758125 and is recorded at `.lab-data/lesson-live-smoke/lesson-30-20261103T121034318024Z/report.json`. Combined stream-reported cost: $0.06008990.

## Lesson 31: 3 November 2026

Two provider-backed `AskUserQuestion` scenarios passed. Each observed one real SDK tool call and matching result, an accepted host `can_use_tool` callback, and a successful terminal on the initialized session. The answer was explicitly simulated by the selected lesson control; no person clicked during the automated acceptance.

| Live case | Simulated host answer | Reported USD |
|---|---|---:|
| concise-answer | Concise | 0.01089385 |
| detailed-answer | Detailed | 0.00535515 |

Combined stream-reported cost: $0.01624900. Report: `.lab-data/lesson-live-smoke/lesson-31-20261103T123556860095Z/report.json`. This verifies fixed-shape routing and both choices, not a deployed human answer UI.

## Lesson 32: 3 November 2026

Three provider-backed Plan mode scenarios passed. The approved valid plan showed plan then default permission modes on the same SDK session before two fixed host workers ran. The valid review-only and duplicate-owner scenarios stayed in plan mode with no workers. Approval was a selected lab control, not a person reviewing during the automated run.

| Final live case | Host outcome | Reported USD |
|---|---|---:|
| valid-approved | Validated, switched to default, two workers | 0.014248 |
| valid-review-only | Validated, remained in plan mode, no workers | 0.004673 |
| duplicate-rejected | Rejected by host, remained in plan mode, no workers | 0.003916 |

Final run cost: $0.022837. Report: `.lab-data/lesson-live-smoke/lesson-32-20261103T131201923828Z/report.json`. An earlier successful SDK run reported $0.012218 but failed the lab's overly narrow internal-call count; it is recorded at `.lab-data/lesson-live-smoke/lesson-32-20261103T130025038240Z/report.json`. The preceding passing run reported $0.020865 at `.lab-data/lesson-live-smoke/lesson-32-20261103T130702247755Z/report.json`. Combined stream-reported cost across all three runs: $0.055920.

## Lesson 33: 3 November 2026

The final provider-backed SDK tool bridged to the actual owned Python MCP server. The client callback supplied a selected simulated form answer. Accept booked the local Blue room; decline and cancel returned distinct no-booking states. All three runs had one SDK tool call/result pair, one MCP callback, a matching server outcome and a successful initialized session. No external calendar was contacted.

| Final live case | Server outcome | Reported USD |
|---|---|---:|
| accept | Local booking confirmed | 0.00888050 |
| decline | Not booked, state `decline` | 0.00845445 |
| cancel | Not booked, state `cancel` | 0.00847215 |

Final run cost: $0.02580710. Report: `.lab-data/lesson-live-smoke/lesson-33-20261103T133638514476Z/report.json`. Three earlier CLI-hook probes cost $0.028112 total and showed that hook responses did not alter the MCP server's `cancel` result on this installed SDK. Their reports are under `.lab-data/lesson-live-smoke/lesson-33-20261103T132946988913Z`, `lesson-33-20261103T133152588671Z` and `lesson-33-20261103T133355233726Z`. Combined stream-reported cost: $0.05391910. Native Agent SDK elicitation routing remains unverified.

## Lesson 34: 3 November 2026

Three provider-backed output-style variants passed. The SDK reported `teaching`, `brief` and `default` in initialization, and each fixed response marker matched. The owned style and settings hashes stayed unchanged, no model tool call appeared, and each terminal matched its initialized session.

| Final live case | SDK style and marker | Reported USD |
|---|---|---:|
| teaching-project | `teaching`, `STYLE_TEACHING_34` | 0.0053490 |
| brief-project | `brief`, `STYLE_BRIEF_34` | 0.0050560 |
| project-disabled | `default`, `STYLE_NONE_34` | 0.0072325 |

Final run cost: $0.0176375. Report: `.lab-data/lesson-live-smoke/lesson-34-20261103T151311351266Z/report.json`. The earlier passing comparison cost $0.0180965 at `.lab-data/lesson-live-smoke/lesson-34-20261103T151049556435Z/report.json`. Combined stream-reported cost: $0.0357340. This is a fixed behavioral comparison, not a full resolved-prompt inspection.

## Lesson 35: 3 November 2026

Eight provider-backed storage scenarios passed against the final check. The host JSON read-back showed replacement or preserved baseline as selected. SDK mirroring used the in-memory or owned SQLite adapter. For every passing storage case, all UUID-bearing entries in the first local CLI transcript appeared in the mirror, summary identity and modification time matched, and no mirror error occurred. A reopened SQLite adapter with a fresh SDK configuration resumed and recalled `ORBIT_35`. Disabled and rejected mirrors left the model turn successful but correctly failed the storage check.

| Live case | Observed host and SDK outcome | Reported USD |
|---|---|---:|
| commit | Host replacement and one mirrored SDK turn | 0.000936 |
| interrupted | Old host JSON retained and one mirrored SDK turn | 0.000931 |
| resume | Two turns through one in-memory store | 0.001070 |
| durable-resume | Reopened SQLite store and fresh configuration | 0.000921 |
| batched-resume | Durable resume with batched flushing | 0.000886 |
| delayed-load | Durable resume with delayed store load | 0.000849 |
| mirror-disabled | Model success; storage check needs review | 0.000962 |
| append-rejected | Model success; storage check needs review | 0.000884 |

Final reported total: $0.007439. Report: `.lab-data/lesson-live-smoke/lesson-35-20261103T162944295278Z/report.json`. All seven lesson 35 smoke runs reported $0.030591 combined. The check compares UUID coverage for the first owned local CLI transcript; it does not compare every byte or prove mirroring of entries without UUIDs. SQLite persistence was also reopened from a separate Python process in the offline test. Remote shared storage and recorded narration remain outside this bounded exercise.

## Lesson 36: 3 November 2026

Five provider-backed scenarios completed. Success and stderr produced the fixed host JSONL outcome and a separate successful SDK terminal. Failed launch, timeout and cancellation correctly failed the success check; the interrupted children were reaped. `machine-a` and `machine-b` are local cwd aliases. The installed Python SDK has no public custom-spawner option, so the host child did not carry SDK protocol.

| Live case | Host check | Reported USD |
|---|---|---:|
| success-a | Passed | 0.000822 |
| stderr-b | Passed, separate stderr marker | 0.000903 |
| failed-launch | Needs review | 0.000801 |
| timeout | Needs review, child reaped | 0.000775 |
| cancel | Needs review, child reaped | 0.000760 |

Reported total: $0.004061. Report: `.lab-data/lesson-live-smoke/lesson-36-20261103T200504332493Z/report.json`.

On 5 November, two repeat live smokes stopped on the first case with a 120-second lesson deadline and no terminal result (`lesson-36-20261105T075930385420Z` and `lesson-36-20261105T080551777705Z`). A bounded diagnostic run completed the owned child and emitted SDK `init` followed by repeated `api_retry` messages before its deadline. The repeat run therefore did not refresh provider-backed acceptance; the earlier five-case result above remains the last passing live evidence.

A fresh run with provider network access passed all five scenarios on 5 November: success and separate stderr passed their success checks; failed launch, timeout and cancel produced the expected Needs review checks. The stream reported $0.003932 total. Report: `.lab-data/lesson-live-smoke/lesson-36-20261105T082803744170Z/report.json`. The earlier retries were `ECONNREFUSED` in the restricted network path; this run is the current live gate.

## Lesson 37: 5 November 2026

Six provider-backed permission-gate scenarios passed their expected checks using `permission_prompt_tool_name`, an owned Write hook, a fixed Python stdio MCP process and a token-scoped loopback host decision. Allow, Edit and Remember produced successful owned Write effects and fresh disk matches. Deny, Malformed and Interrupt did not pass the approval criterion. Remember proposed one session rule; no later reuse was tested. Node is unavailable in this workspace, so the process uses Python.

| Live case | Approval check | Reported USD |
|---|---|---:|
| allow | Passed | 0.005033 |
| edit | Passed, edited file | 0.005450 |
| remember | Passed, rule proposed | 0.004982 |
| deny | Needs review | 0.005839 |
| malformed | Needs review | 0.009836 |
| interrupt | Needs review | 0.002916 |

Reported total: $0.034056. Report: `.lab-data/lesson-live-smoke/lesson-37-20261105T085501575986Z/report.json`. Two earlier probes failed before the host gate ran because the MCP parameter name differed from the CLI call; a third reached the host but returned a structured MCP result the CLI rejected. Those probes cost $0.029822 total and are retained under the lesson 37 live smoke folders.

The final rerun after the manual pending-answer route and scoped rule preview passed all six outcomes at `.lab-data/lesson-live-smoke/lesson-37-20261105T092422403907Z/report.json`. Stream-reported costs were $0.005769 Allow, $0.005783 Edit, $0.005183 Remember, $0.005295 Deny, $0.007248 Malformed and $0.003291 Interrupt, totaling $0.032569. The earlier passing run remains as comparison evidence.

## Lesson 38: 5 November 2026

Four provider-backed prompt-suggestion outcomes met their expected checks. The enabled chat observed a nonempty raw suggestion after successful turns in one SDK session. The edited chat observed real suggestions and sent changed suggestion text as a third validated input; all three turns succeeded in order. The omitted-flag and environment-off controls completed successful turns but correctly did not pass the suggestion acceptance check.

| Live case | Suggestion check | Reported USD |
|---|---|---:|
| enabled | Passed, raw suggestion observed | 0.011620 |
| edited | Passed, observed suggestion edited and submitted | 0.025953 |
| omitted | Needs review; no raw suggestion observed | 0.006932 |
| env-off | Needs review; no raw suggestion observed | 0.005837 |

Reported total for these selected passing scenario reports: $0.050342. Reports: `.lab-data/lesson-live-smoke/lesson-38-20261105T100756838891Z/report.json` (enabled), `lesson-38-20261105T101154582979Z/report.json` (edited), `lesson-38-20261105T101528102764Z/report.json` (omitted), and `lesson-38-20261105T101646598839Z/report.json` (env-off). Two earlier edited attempts completed ordered successful turns with no suggestion; they correctly stayed Needs review and reported another $0.015784 combined. Suggestion absence alone does not establish which control suppressed it. The installed Python SDK parser skips this raw event; the lesson observes it at the transport boundary.

## Lesson 39: 5 November 2026

Seven provider-backed configuration-root scenarios passed their selected checks on fresh owned Git worktrees. Trusted, omitted and branch origin probes matched SDK init cwd with hook and discovered command origins; disabling sources produced no project hook or command. The docs/omitted control correctly stayed Needs review: no hook ran, but the CLI still discovered project commands despite the docs worktree having no `.claude` directory. The trusted takeover produced `trusted-tool-unavailable`: Bash was absent from init tools, with no attempted tool call, fallback denial or proof file. The omitted-root branch takeover produced one exact Bash call, matching tool result, valid host PreToolUse observation and nonce proof file.

| Live case | Observed check | Reported USD |
|---|---|---:|
| where-trusted | Passed, trusted configuration origin | 0.001504 |
| where-omitted | Passed, branch configuration origin | 0.001611 |
| where-branch | Passed, branch configuration origin | 0.001557 |
| where-docs-omitted | Needs review, commands discovered without docs hook | 0.001580 |
| where-no-sources | Passed, no project hook or command | 0.001431 |
| takeover-trusted | Passed, Bash unavailable at init | 0.001899 |
| takeover-omitted | Passed, exact branch Bash proof | 0.00837325 |

Sum of reported terminal costs: $0.01795525. Live report: `.lab-data/lesson-live-smoke/lesson-39-20261105T115047266399Z/report.json`. Three additional credential-free real CLI startup probes rejected relative, missing and file configuration roots with exit code 1 and recorded stderr. They used an isolated config directory, a restricted child environment with no provider credentials and an unreachable loopback provider base. Startup report: `.lab-data/lesson39-startup-smoke/20261105T115139850419Z/report.json`.

## Lesson 40: 5 November 2026

The provider-backed four-turn source persisted host UUIDs, the owned pause tool exchange and the queued Oslo attachment in turn 3. The exact turn 4 drop produced a successful fork retaining turns 1–3 and the queued attachment. Normal recovery produced another successful fork retaining all four turns. The source transcript hash was unchanged.

The unsafe turn 3 drop triggered the real CLI guard for absorbed `queued_command` content. The Python SDK raised `ResultError` during `ClaudeSDKClient.connect` before its iterator yielded the result, but the exception preserved the CLI's structured `result` frame in `data`. The lesson parses that frame with the SDK parser and verifies its UUID, session ID, `error_during_execution` subtype, zero reported cost and concrete queued-content error. Exception text alone remains insufficient. The SDK cleaned up the failed connection; the full comparison now **passes**.

The integrated smoke reported $0.046004 as a sum of terminal cost fields: four source results ($0.001460, $0.003008, $0.007257, $0.009355), exact fork ($0.012234) and recovery fork ($0.012690). The source results can contain cumulative session cost; this sum is an observation, not a distinct-charge calculation. The unsafe guard produced no terminal cost field. Report: `.lab-data/lesson-live-smoke/lesson-40-20261105T122735770166Z/report.json`. An earlier direct live build and comparison at `.lab-data/l40-live-build-probe/494214b25ded44968b6210155c4a09f2` showed the same connection-time guard behavior.

The corrected integrated smoke passed at `.lab-data/lesson-live-smoke/lesson-40-20261105T125326107273Z/report.json`: source, exact drop, unsafe typed CLI result and recovery all verified, with unchanged source hash and closed connections. Reported terminal cost fields sum to $0.054249: four source results ($0.001969, $0.003747, $0.008602, $0.011114), exact fork ($0.014274), unsafe result ($0) and recovery ($0.014543). These may include inherited session cost and are not a distinct-charge total.

## Lesson 41: 5 November 2026

The Python edition's provider-backed client comparison passed at `.lab-data/lesson-live-smoke/lesson-41-20261105T131329921401Z/report.json`. Three sequential prompts on one `ClaudeSDKClient` produced successful terminals with distinct result UUIDs and the same session ID. Three initialization observations matched that ID. After disconnect, a new query raised `CLIConnectionError`. A fresh client resumed the validated owned session and produced a successful terminal with a matching fourth initialization ID. The exercise checks lifecycle and identity, not the model's recall text.

The four terminal cost fields were $0.000791, $0.002230, $0.003425 and $0.004779. Their sum is $0.011225, but resumed and repeated session totals can include inherited costs, so the sum is not an independent billing total. The historical JavaScript V2 API from the reference is not present in this Python SDK; this outcome verifies the explicit Python lifecycle adaptation only.

## Lesson 42: 5 November 2026

Eight selected provider-backed web actions ran in fresh owned homes. Basics produced one same-ID WebSearch result and one WebFetch result; the search post-hook observed `allowed_domains=["nodejs.org"]` and the fetch returned code 200. The HTML, release JSON and trailing-slash fetch variants returned code 200. The fixed missing page returned code 404 and correctly stayed **Needs review**. The injection comparison fetched the public about page in two independent lanes, then overlaid a harmless authored sentence in the host: the unguarded SDK-visible result retained it, while the guarded result contained the replacement marker. The guard action recorded a host denial and error result for `https://example.com/`, with no successful fetch post-hook for that URL. Quick and verified research lanes had distinct sessions, correlated tool IDs and observed-source citation labels.

| Live action | Observed check | Terminal cost fields (USD) |
|---|---|---:|
| basics | Passed | 0.0311061 |
| fetch-page | Passed | 0.0051283 |
| fetch-json | Passed | 0.0106909 |
| fetch-redirect | Passed | 0.0054963 |
| fetch-missing | Needs review, code 404 | 0.0040010 |
| injection | Both lanes passed | 0.0053633 + 0.0051805 |
| guard | Passed, fixed URL denied | 0.0441600 |
| research | Quick and verified passed | 0.0352724 + 0.0365375 |

The ten terminal cost fields sum to $0.1829363; this is a sum of SDK reports, not an independently reconciled invoice. Reports: `.lab-data/lesson-live-smoke/lesson-42-20261105T140107378052Z/report.json` (basics), `lesson-42-20261105T140154330423Z` (page), `lesson-42-20261105T140206401700Z` (JSON), `lesson-42-20261105T140222495107Z` (trailing slash), `lesson-42-20261105T140238855494Z` (missing), `lesson-42-20261105T140256271632Z` (injection), `lesson-42-20261105T140317566345Z` (guard), and `lesson-42-20261105T140341148252Z` (research), all under `.lab-data/lesson-live-smoke/`. The saved frames were re-evaluated after tightening exact fetch URL, duplicate post-hook and invalid search-hit checks; the expected checks still held without further paid calls. The redaction is heuristic, the hostile sentence was authored by the host, citation provenance does not prove claim support, and the trailing-slash case is not an SSRF or redirect-isolation proof.

A final live research rerun after narrowing citation extraction to the final assistant answer passed both lanes at `.lab-data/lesson-live-smoke/lesson-42-20261105T142209478851Z/report.json`. Quick cited one fetched URL and one search hit; verified cited both fetched URLs. Those terminal fields were $0.034244 and $0.03811505, adding $0.07235905 in reported fields. Across the selected runs and this rerun, terminal fields sum to $0.25529535, still not an independently reconciled invoice.

## Lesson 43: 5 November 2026

The owned loopback MCP fixture passed local challenge, metadata discovery, machine credential grant, HTTP and SSE transport probes, token reuse and revocation, tool inventory, and digest-checked reads of the runbook, incident note, order, PNG and inert HTML resource. The focused route and lab suite passed 21 tests.

Provider-backed `ClaudeSDKClient` runs reached the same owned fixture: HTTP tool ($0.005148), HTTP tool plus runbook resource ($0.006622), SSE tool ($0.004794), and SSE tool plus runbook resource ($0.006767). Each run had a matching SDK tool-use/result ID, allowed host hook observation, server handler receipt, successful terminal and closed connection. The resource runs recorded an actual MCP `resources/read` request. These four reported terminal fields sum to $0.023331; they are SDK cost observations, not an invoice.

The Python SDK installed here exposes `reconnect_mcp_server` but no public `set_mcp_servers` control to replace a connected server's Authorization header. The local host-client rotation passes, but the same-client provider-backed rotation contract remains **Needs review**. Lesson 44 must wait until this is resolved or explicitly adapted with an equivalent verified control. The fixture's machine grant does not certify a third-party OAuth provider.

The final integrated rerun after making `find_order` return an MCP `resource_link` passed all four cases at `.lab-data/lesson-live-smoke/lesson-43-20261105T151957158385Z/report.json`. HTTP tool, SSE tool, HTTP resource, and SSE resource terminal cost fields were $0.005244, $0.005471, $0.006916, and $0.006622, respectively (sum $0.024253). The earlier integrated run also passed all four cases; an initial smoke-runner attempt incorrectly classified an SDK tool result with `is_error=None`, which the runner now accepts as non-error. The reported sum is not an independently reconciled invoice.

Additional provider-backed same-client reconnect cases passed over HTTP and SSE. Each produced two successful turns with one session ID, server status connected before and after `reconnect_mcp_server`, and handler markers 1 and 2 under credential-1. Reports: `.lab-data/lesson-live-smoke/lesson-43-20261105T154544596918Z/report.json` (HTTP, final cumulative terminal field $0.010195) and `.lab-data/lesson-live-smoke/lesson-43-20261105T154607142794Z/report.json` (SSE, $0.010571). These totals are per query; the first-turn fields are not added again.

A separate live config-file rotation probe revoked credential-1, issued credential-2, rewrote the SDK's MCP config file and called `reconnect_mcp_server` on the connected client. The CLI rejected the still-configured old Authorization header with HTTP 401; only marker 1 reached the handler. The second SDK terminal was `success`, so a terminal alone would have been a false positive for rotation. This directly confirms the remaining native configuration-update gap. The probe removed its temporary secret config file after disconnect.

The final six-case integrated run passed at `.lab-data/lesson-live-smoke/lesson-43-20261105T155823710651Z/report.json` after adding exact marker/RPC-ID/credential-label joins between server handlers and authenticated wire calls. Reported terminal cost fields were $0.005171 (HTTP tool), $0.005141 (SSE tool), $0.006790 (HTTP resource), $0.008569 (SSE resource), $0.010762 (HTTP same-client reconnect) and $0.010969 (SSE same-client reconnect), totaling $0.047402. The reconnect fields are final cumulative values for their two-turn queries. This sum is an SDK observation, not a reconciled invoice. The local auth action also now observes a 401 after forcing its issued token past expiry; missing/foreign/failed prepared cases alter the evidence before evaluation.

The complete non-browser regression reported 1,715 passes, eight skips and two failures outside Lesson 43: Lesson 72 exceeded its deadline under the long run, and a stdio MCP test lost its stream. Both passed on immediate isolated rerun. The focused Lesson 43 API, local protocol and phone browser tests passed (22 tests), and Ruff and mypy passed. The complete suite therefore has no all-green single-run result for this revision.

## Lesson 43 gap closure: 6 November 2026

The local protocol report now carries connection-scoped JSON-RPC call/result keys, independent authenticated wire markers and resource URIs, handler connection IDs, and digest-matched resource reads. Local negative scenarios alter missing, foreign or failed observations before evaluation. The API now exposes the pinned seven action paths, with `step=tool|resource|rotate` under `/api/c43/live`; only that path permits `mode=live`. The browser phone test runs all seven local actions and both additional local agent steps. A scrubber removes issued fixture credentials and credential-bearing fields before reports leave the action. Listener cleanup, Origin, grant audience, operation overlap, and saved-state pointer checks have focused tests.

The final integrated six-case provider-backed run passed at `.lab-data/lesson-live-smoke/lesson-43-20261106T072345390101Z/report.json`. HTTP tool, SSE tool, HTTP resource, SSE resource, HTTP reconnect and SSE reconnect final terminal cost fields were $0.003653, $0.003642, $0.009704, $0.010088, $0.007815 and $0.007543 (sum $0.042445, not an invoice). Resource turns used both ListMcpResourcesTool and ReadMcpResourceTool; the connected server status listed `get_status`. A later validator-only condition requiring that inventory was checked against all six saved frames without another paid call. Native same-client credential rotation remains unavailable: the pinned contract requires `setMcpServers` before reconnect, while this Python SDK has no equivalent public control and a config-file rewrite probe retained the revoked header.

After the API report was corrected to label host actions local and reject evidence above 700 frames or 2 MB, the integrated HTTP resource case passed again at .lab-data/lesson-live-smoke/lesson-43-20261106T073536254328Z/report.json (terminal cost field USD 0.007919). The operation-slot, saved-summary integrity, listener cleanup and report-bound tests pass. The Python portal uses content-derived concept and walkthrough visuals; separate Lesson 43 image briefs are authored, but no distinct raster images or recorded narration were produced in this pass.

Two distinct Lesson 43 SVG diagrams were then added to the concept and walkthrough tabs. The phone browser test loaded both assets, exercised all seven local actions plus resource/rotation rehearsals, and found no page errors or horizontal overflow. Both SVGs were rendered in a browser and visually inspected at 1200 x 690; text and arrows were readable and within the frame. The media gap is now recorded narration rather than lesson-specific visual content.

The order resource case now follows the URI from the actual find_order resource_link instead of separately selecting the same string; all five resource kinds passed on both HTTP and SSE (10 focused cases). The final local API, state, report-bound and browser checks passed, with Ruff, mypy and git diff --check clean. Native connected-client credential rotation remains the unclosed Lesson 43 acceptance gate.

The rotation gate was closed with a version-guarded private `mcp_set_servers` control request in Python SDK 0.2.174. The live action revokes credential-1, observes 401 for that token, obtains credential-2, replaces the connected server configuration, calls reconnect and observes the second tool handler receipt under credential-2 in the original SDK session. Direct HTTP and SSE probes both passed. This control is private and must be reviewed on an SDK upgrade; changing a config file alone did not rotate the connection.

The final integrated eight-case live run passed at `.lab-data/lesson-live-smoke/lesson-43-20261106T080553468306Z/report.json`: tool HTTP/SSE, resource HTTP/SSE, reconnect HTTP/SSE and rotate HTTP/SSE. The reported final terminal cost fields were $0.003474, $0.003690, $0.007603, $0.007864, $0.007778, $0.007574, $0.007777 and $0.007731 (sum $0.053491, not an invoice). Both rotation cases recorded `mcp_set_servers.added=[lesson_remote]`, a revoked-token 401, handler labels credential-1 then credential-2, and one session ID across two successful turns. The 26 focused local/API tests, Ruff and mypy passed. Recorded narration and independent student acceptance remain separate.

Three reviewed Lesson 43 source explanations were recorded with Yash / `inworld-tts-2` after configuring the previously supplied key in the ignored workspace `.env`. The provider reported 1,438 processed characters without a price. The clips last 23.04, 28.49 and 31.61 seconds; source identity, word timings, MP3 decode, HTTP delivery and browser play/pause passed. The final focused local/API/audio suite passed 27 tests and the phone browser test passed. Human listening review and independent student acceptance remain.

## Lesson 44: 6 November 2026

The owned OTLP HTTP JSON collector passed six local actions over real loopback HTTP. Each action received positive metrics, logs and traces; privacy and exporter comparisons used two lanes. Local negative cases for missing receipts, foreign run identity and failed closure correctly required review. The collector returned 401 for an unauthenticated probe, 400 for malformed or wrong-signal JSON, 415 for unsupported protobuf, and 200 with zero records for a valid empty envelope. The reducer summed two delta cost points to 0.03 and kept the latest cumulative point at 0.02. The local 390 px browser test exercised all six actions and seven questions.

A native provider-backed probe first established that the installed Claude CLI actually emits OTLP HTTP JSON metrics, logs and traces to the owned collector, including session and tool-use IDs. Collector authentication initially failed because this CLI sent the literal string Bearer%20 from the header environment setting. A literal space in the private header value produced the expected Bearer header; the final collector-auth action observed its unauthenticated 401 followed by authorized native exports. No credential value entered the report.

The final integrated six-action/eight-query live run passed at .lab-data/lesson-live-smoke/lesson-44-20261106T084709867568Z/report.json. Recorded SDK cost fields were $0.0050057 (Signals), $0.0104445 (two Privacy lanes), $0.0050037 (Tracing), $0.00898815 (Rich), $0.0100558 (two Exporters lanes) and $0.005061 (Collector), totaling $0.04455885. These are SDK observations, not a reconciled invoice. Every lane had a successful SDK terminal, matching Read tool use/result and hook/hash observation, and positive native receipts for all three signals. Privacy observed the synthetic marker only in the content lane while retaining no raw body. Tracing received the native child under the manual host span; Rich recorded one denied Bash call/result with native tool ID and a separate executed Read. Exporters received actual delta and cumulative sum temporalities. The strengthened evaluator was replayed against the saved six cases without another paid call and all still passed.

At this earlier checkpoint, narration, independent student acceptance, dedicated injected-query tests, a fuller streaming Stop/cancellation audit and wider regression were pending. The later post-check run below supersedes its live gate.

The final post-check run passed all six actions and eight queries at .lab-data/lesson-live-smoke/lesson-44-20261106T091324587806Z/report.json. Its per-action recorded cost fields were $0.0049845, $0.0101406, $0.0049959, $0.0090777, $0.0102288 and $0.0049542 (sum $0.0443817, not an invoice). The portal now requires fresh live consent per action and resets its checkbox after use. The live evaluator checks UUIDs, finite costs, matching native receipt/session/tool identities, actual delta/cumulative temporalities and a denied Bash result without a Bash post-use receipt.

## Lesson 45: cloud provider routing

On 6 November 2026, the final five-action `/api/c45` live matrix passed. Its sanitized report is under `.lab-data/cloud-api-live-final/c45-cloud/<group-run-id>/report.json`. Action IDs were Catalog `09a4fa07-3883-4d28-b531-30f8dd464655`, Same `449c172b-360e-48bd-bf75-13132be44e3c`, Auth `b8c2d725-00c9-4c30-abe3-e069612f0d7b`, Models `6148c834-d3fc-4b79-9596-60eed0bd59f8` and Failures `758a6eed-286b-417f-ac5e-8e0a3965ba9e`.

Catalog inspected all five native provider configurations without forwarding a prompt or charging inference. Same sent one bounded Haiku request through each provider-shaped route; every lane had a matching SDK assistant ID and successful fixed-upstream HTTP response. Auth observed missing and wrong Bedrock bearer requests fail with 401 before one valid native request. Models observed the owned Bedrock profile ARN on the signed wire request. Failures observed a native Sonnet 403, `is_error: true`, zero upstream inference and zero SDK cost, followed by a fresh successful Haiku query. The configured fallback did not fire in the tested SDK/CLI version, so the observed recovery is the separate request.

The nine native inference queries across these actions reported $0.008227 in summed SDK cost fields, below the $0.90 combined test ceiling. Direct native SigV4, profile and region cases also passed with individual evaluator replay. The shared `/api/lessons/45/run` completed a live Auth action and an offline Same action. These receipts prove this owned proxy and fixed upstream behavior; they do not establish access to deployed AWS, Google Cloud or Azure services. Recorded values are SDK observations, not a reconciled invoice. Human listening review of the three recorded Yash clips and independent student acceptance remain open.

Three source-aligned Lesson 44 Yash clips were recorded; the provider reported 1,520 processed characters and no price. The clips last 27.26, 31.61 and 29.59 seconds. Source hashes, word timing, MP3 decode, HTTP delivery and browser play/pause passed. Human listening review remains separate.

The focused tests now inject SDK messages and real loopback OTLP HTTP exports without a provider call. The passing injection joins Read hook, result, session and collector receipts; malformed trace IDs return 400 and fail the live evaluator. A deterministic cancellation test ends the portal run as cancelled without a successful summary. This does not yet cover every streaming Stop timing or a separate student's independent acceptance.

A bounded native Stop probe cancelled the provider-backed privacy action after the owned collector received 11 export receipts. The action task was cancelled and the listener was unreachable after cleanup. The local in-flight export and portal cancellation tests also passed without leaving a successful summary. These checks cover the active listener and SDK task path; they do not certify every timing race or downstream exporter retry.

After adding the unsupported-protobuf probe to Exporters, that action passed again with two native provider queries at `.lab-data/lesson-live-smoke/lesson-44-20261106T092725852251Z/report.json` (recorded SDK cost fields $0.0101257). Its owned collector returned HTTP 415 and decoded no protobuf record while receiving positive native JSON exports for both temporalities. The latest validator replay passed all six actions using five cases from the preceding integrated run and this new Exporters case; their recorded SDK cost fields sum to $0.0442786, not an invoice. The third narration clip was rerecorded to match the changed source.

## Lesson 46: prompt caching and cost

On 6 November 2026 the five-action `/api/c46` live command passed, saving incremental sanitized cases under `.lab-data/cache-api-live/63db1d89-212c-4879-abf6-908fa1c55a2c/`. It observed ten successful native turns and two authenticated upstream receipts per action. Action operation IDs were Anatomy `df09aea2-a13a-4745-90d1-cea093510846`, 1-hour Switches `9230bd9d-b7b7-41ff-8ab0-4055ed820bf9`, changed-prefix Breakers `a94fddd1-836d-4709-b637-e54c8155fbaa`, capped model switch `1a69b6b5-66ef-4fe8-8429-02792a54f4aa` and allowed model switch `b8525c8f-f159-4f4f-8255-5a3f45f0719b`.

Each action matched its native assistant IDs, initialized session, two successful terminals, independent SDK usage and wire response counters. Anatomy observed a second-turn cache read. The 1-hour owned wire perturbation observed one-hour writes and a later read. The changed-prefix perturbation changed its system digest but still read earlier cached tokens; no complete miss is claimed. The cap hook denied a warm-cache switch with no post-hook and a Haiku second turn. The allowed case had both native hooks and a Sonnet 4.5 second turn. The five last cumulative SDK cost fields were $0.0063744, $0.0098891, $0.0063719, $0.0063776 and $0.0241695, totaling $0.0531825 under the $0.75 combined session ceilings. A separate shared lesson-runner Anatomy live case completed with two turns and a $0.00636835 last cumulative SDK field. These are SDK observations, not a reconciled invoice or guaranteed saving.

Direct bounded native probes passed for Switches with caching off and five-minute TTL; Breakers with tool, dynamic, short and stable prefixes; and Anatomy with a short prefix. Each saved case replayed as passing under the current evaluator. The dynamic case observed an added owned suffix. The first stable Breakers attempt failed because its first turn exhausted the 128-token output cap and did not produce two successful turns; one repeat passed with operation `85003b5b-5a48-4cd2-b52c-bce9121465b8`, two successful turns, and 4,591 cache-read tokens on turn two. A separate native cancellation run (`3ee4efba-d344-4248-bb2c-73f81e3e371b`) stopped after one upstream receipt and confirmed the loopback listener was unreachable. Human listening review of the three Yash clips and independent student acceptance remain open.

## Lesson 47: multi-agent orchestration

On 6 November 2026 the five-action `/api/c47` live matrix passed under `.lab-data/orchestra-api-live/92606627-9032-4a53-9708-5ffaf76e8ab7/`. Orchestrator `65032571-2032-4409-9659-f1f124aa827c` had two worker rows and one root query; hierarchy `44d99f22-6837-4dc1-b4dc-8ba4beebccda` had three worker rows and one root query. In each native tree, the host joined the actual Agent tool ID, admitted pre-hook, SubagentStart agent ID, task_started depth, owned analyst Read/hash, SubagentStop report and completed task notification. Pipeline `6278de8b-0d8b-471a-8fa9-70ad4bb1158b` had three separate queries and two checked digest-bound handoffs. Fan-out `e75d28f7-6454-4b2f-b887-cf975ab4de6d` had three owned regional queries. Evaluator `e78c9fa4-77ca-4c80-875e-d2aeae109d24` had a verified writer report, then one separate PASS critic query. The five action SDK terminal cost sums were $0.0145472, $0.0225578, $0.00571, $0.013662 and $0.005058, totaling $0.061535 under the $0.85 combined query ceilings. These are observed SDK cost fields, not a reconciled invoice.

A direct one-worker fan-out `cfa3604c-9eb8-439a-b3a4-fd235acf94d0` passed: maximum active 1, maximum queued 2, final active/queued 0/0 and $0.013717 reported. The shared lesson runner passed a native orchestrator `45916cc2-47ae-4d58-9f06-a32ae659a0e6` with two workers and $0.0145796 reported. Before the final matrix, failed probes exposed a root hook misattribution, Windows newline hash mismatch and one critic prose/FAIL response. Those failed runs were retained; the final cases passed with fixed hook attribution, byte-stable fixtures and an explicit candidate prompt. Local missing-file, foreign-identity, wrong-report, worker-failure and cancellation scenarios remain labelled authored fixtures. A shared-runner Stop probe (07012477-f0c5-4875-abc4-017341016a63) cancelled after its isolated native home appeared, saved no passing evidence and left zero active runs; it does not prove a completed provider inference. Human listening review and independent student acceptance remain open.

## Lesson 48: security hardening

On 6 November 2026 a first bounded native permissions attempt reached Anthropic but received HTTP 400 with a credit balance error before tool execution. After credits became available, the four-action `/api/c48` live matrix passed at `.lab-data/hardening-api-live/adf61c95-6edf-43e0-995a-f7047045e004/summary.json`: eight native SDK lanes, 22 fixed tool calls and $0.0524189 in summed SDK terminal cost fields under a $0.80 matrix ceiling. Permissions observed contrast synthetic reads and outside write with guarded denials. Lockdown observed contrast collector egress and guarded egress denial. Secrets observed a guarded PostToolUse known-marker rewrite with no marker in model-bound wire bytes. Injection read an untrusted ticket while guarded protected read and egress calls remained denied. Every lane retained correlated call/result IDs, upstream message receipts, checked file and collector effects and closed listeners. These costs are SDK observations, not a reconciled invoice.

The shared lesson runner passed a native secrets action (`dc476047-00f7-487a-bb44-5c87db07b61f`, $0.01346825 reported). An active cancellation (`7ba997a7-5a71-4eeb-a29d-08e1a551d7b6`) saved no passing evidence, left zero active runs and closed both listeners. The final matrix reports replayed under the tightened evaluator without a further paid call. Four local two-lane actions, strict API checks, mobile UI and source audio passed; the prior full offline regression finished with 1,967 passed and 13 skipped. See [Lesson 48 implementation](lesson-48-security.md). Human listening review and independent student acceptance remain open.

## Lesson 49: deployment and headless CI

On 6 November 2026 the four-action `/api/c49` matrix passed at `.lab-data/headless-api-live/a2e35753-9e27-4b6f-9f32-8601eb0c38cc/summary.json`. The native Headless action observed successful Claude CLI and Python SDK child runs with exact schema and run identity. The native CI action returned code 0 for the clean fixture and code 20 for the valid FAIL classification of the buggy fixture. SDK terminal cost fields summed to $0.006155 and $0.00537 by action, $0.011525 total under a $0.40 matrix ceiling. These are SDK observations, not a reconciled invoice.

The local Limits action observed mapped codes 0, 11, 11, 12, 124 and 127 from real child outcomes. The local Deploy action observed health and readiness 200, second job 429, drain readiness 503, completed admitted job 200, worker exit 0 and closed TCP; a separate deadline test observed job 408. A shared lesson runner native CI action passed (`2ef412b1-862a-40bd-9395-ef94b0cd41d7`, $0.005227 reported). Active cancellation (`bc1f27c8-c7a1-433e-9726-fb7449f52dad`) saved no passing evidence and left zero active runs. The final post-change matrix also passed at `.lab-data/headless-api-live/1a38b2e8-4e3b-44d6-b8e9-65283c9f59b2/summary.json`: two native actions and two local actions, $0.011522 in summed SDK cost fields. The full offline regression passed on 7 November 2026 with 1,975 passed and 14 skipped after normalizing the Lesson 13 MCP success flag. See [Lesson 49 implementation](lesson-49-headless.md). Source-aligned narration was rerecorded after the process edit; human listening review remains open.

## Lesson 50: full-stack synthetic support desk

The final provider-backed `/api/c50` matrix passed at `.lab-data/desk-api-live/c2fcb1be-fe99-4b5f-8985-0c96c84663be/summary.json`. One native conversation (`1ad9b76f-1b9c-41ba-9f01-66cfbf3c981b`) completed Orders, a resumed Ticket, a denied Refund, an approved 1000-cent Refund and a restricted structured CRM close. Each write turn made its own fresh Orders call; native call/result IDs matched persisted host effects. Denial left no refund row, approval left exactly one, the CRM transcript remained unchanged, and the free local evaluations passed. SDK cost deltas were $0.003540, $0.007154, $0.009371, $0.011708 and $0.036870 respectively, totaling **$0.068643** under the $0.50 matrix ceiling. These SDK cost fields are observations, not a reconciled invoice.

The shared lesson runner's native Orders probe passed at `.lab-data/desk-runner-live/64824229-cd86-4f14-a2df-b3d6f6be6199/report.json`, with a $0.003558 SDK cost delta. A separate provider-backed refund run was stopped at its exact pending approval (`d0d8f5fd-8cd0-42d9-bf85-64aba0924b98`); its report is `.lab-data/desk-api-live-cancel/cac1b4f8-89dd-40b0-aff1-7c441fa93f52/summary.json`. The stop left zero refund rows and zero pending approvals. Cancellation yielded no SDK terminal cost receipt, so its actual cost is unknown; the native request had a $0.10 action cap. The final full offline regression passed with **1,985 passed and 14 skipped** after adding a bounded Windows atomic-replace retry and verifying the source-bound narration again. See [Lesson 50 implementation](lesson-50-desk.md). Production identity, payments and CRM integration, human audio listening and independent student acceptance remain open.

## Lesson 51: offline host unit testing

The reference contract expressly has no live selector, provider call or API key requirement. Acceptance runs the normal 16/16 host suite, its single-failure denial mutation, six synthetic replays, strict API and network-guarded CLI. Actual model calls and billed cost are zero. The `--live` CLI option is rejected. The full offline regression passed with **1,992 passed and 15 skipped** (`.lab-data/pytest-l51-verified.log`). See [Lesson 51 implementation](lesson-51-offline.md).

## Lesson 52: evaluation and regression baselines

On 7 November 2026 the paid `scripts/eval.py --live --budget 1 --trials 1 --demo baseline` path executed fresh isolated support hosts and a separate model judge. Five complete three-case runs reached six native queries each and retained real replies, independently checked host effects, judge results and known SDK cost fields. The latest complete run is `.lab-data/offline-validation/evals-e1521054-bfa8-4bc2-8bcb-b1aa226a2b7a/report.json`: three cases, six calls, **$0.029535** in reported terminal fields. Its Orders empathy criterion failed; Ticket and denied-refund passed all five rubric criteria, and all three business booleans were true. An earlier complete run (`evals-655ca147-58b9-40d9-a771-84583738c085`) passed Orders and Ticket but failed denied-refund empathy. These subjective failures are retained. No complete run met the all-pass promotion gate, no live baseline was promoted, and comparisons correctly remain `stale`.

Three earlier partial attempts encountered `error_max_structured_output_retries` in the separate model judge. The first full nine-trial run reached 18 native queries for $0.086147 but failed three empathy decisions. The harness version and fixed case instructions were then updated. The final nine-trial run at `.lab-data/offline-validation/evals-e6dcd893-33c4-4a54-a51a-755128c3fe07/report.json` completed 18 native queries, all 45 rubric decisions and all 27 business decisions for **$0.089180** in reported SDK terminal fields. Its run ID `bf780500-9978-4016-89e1-e01078c74d51` passed the current fingerprint and reviewed-digest gate, was promoted into the scoped live/model baseline, and `/api/c52/baseline?mode=live&judge=model` read back that exact ID with HTTP 200. A fresh three-case provider-backed CLI comparison then passed all 24 metrics against that baseline at `.lab-data/offline-validation/evals-1107c9ad-f538-47db-bd22-1a0b366f7b15/report.json`: six native queries and **$0.027259** in reported terminal fields.

The paid `/api/c52/stop` control was also exercised after a fresh isolated native agent initialized. Stop returned HTTP 200; the run returned a retained incomplete report (`a6c0f4a2-7baa-441d-90d6-cf50fb98c343`) with one initiated model call, zero completed rows, no terminal cost and `actualBilledUsd: null`. It is not promotion eligible. Five earlier complete three-case probes reported $0.144407 in summed terminal fields, and three partial attempts reported $0.032554 in known fields. Including both nine-trial runs and the final comparison, all known observed fields sum to **$0.379547**, not a reconciled invoice; the stopped call's actual cost is unknown. The first Inworld narration request returned HTTP 403 `SESSION_TOKEN_EXPIRED`; after replacing the credential and reconciling that failed request, all three reviewed Yash clips were recorded with provider word timing. The clean full offline regression passed with **2,000 passed and 16 skipped**. See [Lesson 52 implementation](lesson-52-evals.md) and [narration evidence](lesson-52-narration.md).

## Lesson 53: debugging an agent run

On 8 November 2026 the final free `scripts/debugging_check.py` matrix passed all seven prepared scenarios with zero model calls and zero cost. Its report is `.lab-data/offline-validation/debug-93204ed6-7282-4727-9c93-e5d94b3fb9fd/report.json`. The final provider-backed `--live --budget 1` matrix passed all four supported scenarios at `.lab-data/offline-validation/debug-3a529b49-1957-47b9-abb8-ce4f9eb25157/report.json`: success `83af303a-67ae-446c-a182-985a55ca8267` ($0.005031), denied `d706cb9d-2419-4aae-89af-7e66e1d857f5` ($0.004991), missing `2e6146c7-a3aa-41c1-b358-b5dbe1986380` ($0.005777) and max turns `02414024-e1f8-4c3b-8ad3-f6dd889d2eb5` ($0.002532). Each made one native SDK query. The four reported terminal fields total **$0.018331**, not a reconciled invoice.

A separate provider-backed API Stop probe (`724f042c-91b5-4dfe-86aa-8c5780c8ee6e`) returned Stop 200, saved an interrupted bundle and recovered it after cleanup. It initiated one native model call without a terminal cost receipt; actual cost is unknown. The native SDK warns that an `allowed_tools` Read entry shadows its permission callback; the exact-target PreToolUse hook remains the active gate and the live denial case observed that gate. Three reviewed Yash clips were recorded with provider word timing. Human listening and independent student acceptance remain open. See [Lesson 53 implementation](lesson-53-debugging.md) and [narration evidence](lesson-53-narration.md).

The offline regression gate passed after correcting four older browser checks that could accept a previous run's result. The browser-only suite passed **157 cases**. The final uninterrupted full suite passed **2,009 cases with 17 expected skips** using a short Windows pytest temp path. An earlier Windows quoted-path parser fix required Lesson 48's three source-bound narration clips to be repinned and rerecorded; their integrity test passed in the final suite. Human listening and independent student acceptance remain open.
