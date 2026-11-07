# Lesson 20: Hooks in depth

Choose **Allow and audit**, **Deny before execution**, **Rewrite Read to alternate fixture**, **Observe missing-file failure** or **Contain a synthetic callback error**. Every run attempts exactly one Read of a fixed owned target. No model shell, writes, external MCP service, arbitrary regex or callback code is accepted. The independent host guard stays registered regardless of teaching matcher and audit controls.

## Decisions and observed effects

The global `PreToolUse` guard and permission scope permit Read only on three disposable fixtures. The teaching pre-hook has a finite `Read`, `Read|Glob` or `Write|Edit` matcher. Both guard and teaching callback validate scope; an explicit allow decision can bypass a later permission callback, so authorization is not delegated solely to `can_use_tool`.

- Allow requires the original marker in the actual tool result and successful post-hook response, with a matching target and call ID.
- Deny requires the matched teaching denial and error result, with no successful post audit or leaked fixture marker.
- Rewrite requires `updatedInput` to redirect the Read to the owned alternate file, followed by that alternate target and marker in the actual success audit and result. Returning a rewrite instruction alone cannot pass.
- Missing-file failure permits the intentionally absent target and observes `PostToolUseFailure`, an error result and no success audit. Tool failure can be followed by a successful final agent result; the two outcomes are checked separately.
- The synthetic callback fault is caught inside the teaching pre-hook and converted to denial. The timeline records its exception type without the raw exception body. This does not claim that all uncaught SDK exceptions or timeouts fail closed.

Using `Write|Edit` with these Read experiments demonstrates a nonmatching teaching hook. The always-active guard and global success/failure observers remain independent. Matching pre-hooks may run concurrently; the evaluator does not assume their relative ordering.

`UserPromptSubmit` observes the actual prompt digest and parent identity and returns a small fixed teaching context. `Stop` observes completion, returns no block decision and does not ask the agent for another turn. Neither observation certifies model adherence to every instruction. The full learning criterion requires all success/failure/prompt/Stop channels enabled. Disabling a channel deliberately yields **Needs review**, even when `observation_passed` confirms the configured control behaved correctly.

## Evidence and isolation

The host joins a single Read, its unique result, matching session/call IDs, guard and selected teaching decision, expected success/failure audit, prompt and Stop stages, and actual file markers. Response audit rows retain sizes, hashes and marker labels; they do not retain response or error bodies. Ordinary SDK diagnostics may still contain the synthetic tool messages. File hashes must remain unchanged and the owned client must close.

Wrong callback identities, missing guards or hashes, early post/Stop stages, late prompt records, foreign audit IDs, duplicate results and changed fixtures cannot pass. The observer records sequence numbers for actual callback observations; those numbers do not turn a hook into an OS sandbox. See [lesson 18](lesson-18-sandbox.md) for process isolation.

Offline invokes the same registered callbacks and performs actual local Reads, with explicitly recorded SDK identities. The original five-call host pipeline remains a separate source example; its `executed`, `audited` and `every_execution_audited` counters cannot substitute for the enhanced `experiment` criterion. Live registers the callbacks on the actual Python SDK client. Authentication errors, cancellation and disconnect failures cannot complete the check. The contained pre-hook fault is intentionally distinct from those run failures.

## Run and verify

```shell
uv run agent-lab lesson 20
uv run agent-lab lesson 20 --scenario missing-guard
uv run agent-lab lesson 20 --lesson-options-file hooks-options.json
uv run python scripts/lesson_live_smoke.py 20 --live
```

Example options: `{"behavior":"rewrite","matcher":"Read","post_hook":true,"failure_hook":true,"prompt_hook":true,"stop_hook":true}`. The normal `/api/lessons/20/run`, CLI and UI share strict validation. Negative recorded evidence scenarios are offline only. Callback matchers use a fixed ten-second timeout; the lesson does not expose arbitrary delays or certify timeout fallback behavior.

All seven real live cases passed on 3 November 2026: allow, deny, rewrite, missing-file failure, contained callback error, nonmatching matcher and disabled success audit. The last case intentionally needs review under the full criterion, and the live runner separately requires its actual control observations to pass. Reported total cost was $0.05037; see [live acceptance](live-acceptance.md). Each live case has four turns, a $0.10 SDK threshold and a 120-second host deadline; thresholds are not hard billing caps and the runner stops at the first failed acceptance without automatically retrying.

Seven explained questions preserve the original two answer positions. Three exact implementation excerpts, a reviewed four-section concept code tour and the content-derived seven-section Learning Guide accompany the experiment. The concept guard resolves and checks the canonical target instead of using a path string prefix.

This is a verified Python adaptation using SDK 0.2.174 and the [official hook documentation](https://code.claude.com/docs/en/agent-sdk/hooks). Other hook kinds, subagent interleaving, arbitrary callback/network integrations, broad timeout behavior, authored media and full reference certification remain separate. Lesson 21, Slash commands, is next after the completed offline, browser and real live checks.
