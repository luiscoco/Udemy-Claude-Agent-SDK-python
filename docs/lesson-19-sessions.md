# Lesson 19: Session management

Every run creates its own disposable SDK session, closes the client, and then manages that session's local transcript. Select **Inspect and paginate**, **Rename and tag**, **Fork the owned transcript**, or **Delete this disposable transcript**. No external session ID, configuration directory or project path is accepted from the browser, API or lesson options.

The public SDK catalog functions use the process environment to select a transcript store. This lesson executes them in a separate child with the run's private `CLAUDE_CONFIG_DIR`; the server's environment stays unchanged. All queries use an explicit project directory, and listings disable sibling worktree expansion. Directory filtering is not authorization: the child additionally verifies the original session ID, cwd and original user-prompt digest before any mutation.

## Observed outcomes

- Inspect requires persisted metadata and both user and assistant messages, matching identities, correct session/message pagination and unchanged transcript bytes.
- Rename/tag uses `rename_session` and `tag_session`, verifies the new metadata and a changed transcript file, and requires visible content and message UUIDs to remain unchanged.
- Fork uses `fork_session`, verifies a new session identity, disjoint message UUIDs, preserved visible content and unchanged original transcript bytes. This local file fork does not itself verify that a later model connection can resume it, and does not create filesystem isolation or undo history.
- Delete uses `delete_session` only on the transcript created by this run. Its file, metadata and messages must be absent afterward, while listings no longer contain the identity. Workspace files, manual progress and the run's evidence remain. Evidence includes bounded previews, so catalog deletion is not an evidence-erasure operation.

Page size is bounded to 1-10 and offset to 0-20. An offset beyond the available rows produces a valid empty page. The check separately inspects the original messages, rather than treating an empty page as a missing session. Previews contain at most 240 characters per message. Titles are trimmed, bounded and restricted to simple text; tags are the fixed reviewed/practice choices.

The child also checks a fresh empty config and another project scope, which must not list this session. A successful model answer, a method call or a missing persistence file cannot substitute for these observations. Missing final results, mismatched parent identity, missing catalog reports and mismatched operation effects need review. Incomplete content digests, missing retained-session metadata, unchanged rename/tag bytes and inconsistent fork/delete observations fail the criterion.

Offline creates a labelled transcript fixture and uses the actual public SDK file APIs. Live creates an actual tools-disabled CLI session and waits for `disconnect()` before catalog access. No host fixture is substituted if live persistence fails. Authentication failure, cancellation, missing initialization or uncertain connection closure prevents mutation; owned clients and catalog child processes are cleaned up. The local catalog operations themselves make no model call.

## Run and verify

```shell
uv run agent-lab lesson 19
uv run agent-lab lesson 19 --scenario missing-catalog
uv run agent-lab lesson 19 --lesson-options-file catalog-options.json
uv run python scripts/lesson_live_smoke.py 19 --live
```

Example options: `{"action":"rename-tag","title":"Reviewed lesson session","tag":"practice","page_size":1,"offset":0}`. The normal `/api/lessons/19/run`, CLI and UI share strict validation. Each live case uses a fresh private config and transcript, four turns, a $0.10 SDK threshold and a 120-second host deadline. Thresholds are not hard billing caps; the runner stops at the first failed acceptance without an automatic retry.

On 3 November 2026 all four real live cases passed: paged inspection, rename/tag, local fork and owned deletion. Reported cost totaled $0.00459. The recorded native observations also satisfy the final stricter evaluator. See [live acceptance](live-acceptance.md) for the report location. Seven explained questions preserve the two existing answer positions; three exact implementation excerpts and the content-derived seven-section Learning Guide accompany the experiment. The existing inspection concept tour was reviewed with explicit `include_worktrees=False`.

This implementation uses the pinned Python SDK 0.2.174 and its public catalog/mutation methods, alongside the [official session documentation](https://code.claude.com/docs/en/agent-sdk/sessions). The pinned reference lesson contract was unavailable during this work, so this is an individually verified Python adaptation rather than full reference certification. External stores, cross-user authorization, resumed fork conversations, broad archive management and authored media remain separate. Continue with [lesson 20, Hooks in depth](lesson-20-hooks.md).
