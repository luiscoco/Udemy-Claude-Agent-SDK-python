# Lesson 17: Checkpointing and rewind

The experiment keeps one client connection open, captures the original replayed user-message UUID, permits one exact replacement of the run's disposable `notes.txt`, and calls the public `ClaudeSDKClient.rewind_files()` method. It compares original, changed and final file hashes. A successful control response alone is insufficient: the file must actually have changed and then match its original bytes, and the client must close.

Keep **Enable SDK file checkpointing**, **Replay user messages** and **Rewind the owned file** selected for the passing example. Both replacement variants display their exact content. **Inspect only**, disabled checkpointing and disabled replay deliberately leave the restoration criterion unmet. Requests accept only these bounded choices, never a caller-supplied session/checkpoint ID or path. Prompts do not authorize a different file, content or tool.

Offline runs use the real installed Python SDK client and its stream-JSON control protocol. A scripted transport emits the replay, Write and terminal records; its file edit, backup and restoration effects are real local Python operations. These effects are explicitly labelled fixtures, and do not certify native CLI backup behavior. The original small host snapshot remains a separate source example; its `restored` field cannot satisfy the enhanced automatic check.

Live runs use actual SDK messages and native rewind in the same open connection. Host hooks and permission callbacks allow Read and the selected exact Write only on `notes.txt`; settings sources and external MCP configuration are disabled. A UUID from a tool-result message, unrelated prompt, child turn, invalid value or late replay is never selected. Missing parent success, missing initialization or mismatched session identity prevents rewind. There is no host snapshot fallback if native rewind fails. Each run's disposable workspace retains the observed file state for inspection.

The check requires a unique successful Write/result pair, checkpointing and replay options, a captured user UUID before the edit, parent success, changed bytes, acknowledged rewind, restored original bytes and confirmed closure. Missing-checkpoint, missing-evidence, wrong-identity, rewind-error and no-effect scenarios intentionally need review. Authentication retries reporting HTTP 401 stop immediately; errors and cancellation close the client in its owning task. The host makes no paid retry.

```shell
uv run agent-lab lesson 17
uv run agent-lab lesson 17 --scenario no-effect
uv run agent-lab lesson 17 --lesson-options-file checkpoint-options.json
```

Example options file: `{"checkpointing":true,"replay_messages":true,"action":"rewind","replacement":"short"}`. The normal `/api/lessons/17/run` API, CLI and UI share validation. Negative recorded scenarios are offline only. Seven explained questions preserve the two existing answer positions; three exact source excerpts and the content-derived seven-section Learning Guide explain the implementation.

This implementation follows the pinned installed Python SDK's public method and the [official file-checkpointing documentation](https://code.claude.com/docs/en/agent-sdk/file-checkpointing). It does not rewind conversation history or external side effects. All four current live variants passed on 3 November 2026, including native restoration; see [live acceptance](live-acceptance.md). Resumed/multiple checkpoints, multiple files, authored media and full reference certification remain pending. Continue with [lesson 18, Sandbox](lesson-18-sandbox.md).
