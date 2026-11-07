# Lesson 40: Resume drops turn

`resume_drops_turn` removes one selected user turn while `resume_session_at` chooses an earlier persisted boundary. The lesson tests both flags against an owned four-turn SDK session. A host UUID marks each user message. Turn 3 invokes the owned `mcp__rewind__pause` tool and absorbs a queued Oslo message as a `queued_command` attachment; that attachment belongs to turn 3, not a fifth turn.

## Inspect the persisted source

The lab reads the raw JSONL transcript from an isolated CLI home. It follows `parentUuid` from the last active record, excludes inactive side branches, and derives logical turns from user prompts. It rejects duplicate or malformed UUIDs, missing parents, cycles, unsafe files, missing queue evidence and source hash changes. The original transcript hash is checked again after every comparison.

`POST /api/c40/dry` captures the installed SDK's serialized resume flags without starting the CLI. `POST /api/c40/build` makes a prepared or explicitly consented live source. `GET /api/c40/state` returns its manifest and active-chain summary. `POST /api/c40/cases` runs the exact, unsafe and optional recovery comparison. `POST /api/c40/undo` runs one selected turn and boundary experiment without claiming the full comparison. `GET /api/c40/code` supplies three current Python excerpts. Each route accepts only fixed lesson choices and owned build IDs; live operations require fresh consent and run under a bounded operation lock.

## Comparison criterion

- The exact last-turn case resumes at the end of turn 3 and drops turn 4. A successful new fork must retain turns 1–3, including the single queued attachment.
- The unsafe case resumes at the end of turn 2 and tries to drop turn 3. Its range includes absorbed queued content. The pinned criterion requires an actual CLI result frame parsed to `ResultMessage` with subtype `error_during_execution` and an error beginning `Resume rejected by --resume-drops-turn:`. Exception text alone does not count.
- The optional recovery case forks normally and must retain all four prompts and the queued attachment. The source transcript must remain byte-identical throughout.

Prepared mode uses authored transcript and refusal fixtures and labels them as such. It is useful for studying the boundary and testing the checker, but it does not establish CLI behavior. On 5 November 2026, the real live source build, exact fork and normal recovery fork succeeded. The installed CLI emitted a structured unsafe `result` frame, then the SDK raised `ResultError` during `ClaudeSDKClient.connect` before its iterator could yield it. The lab parses `ResultError.data` through the SDK parser, records its origin and verifies the frame's UUID, session, subtype, cost and concrete error. The full provider-backed comparison passed.
