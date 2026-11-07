# Lesson 25: Compaction and context

The lesson uses a fixed eight-step log of 5,168 characters. A real SDK MCP tool returns either the first 600 or 200 characters, followed by a marker that gives the exact number removed. The host independently keeps `{completed: [0..7], next: "verify"}` when the summary control is enabled.

The automatic check requires one actual tool callback, one matching SDK tool call and successful tool result, a successful terminal result in the initialized session, and the exact bounded payload. The omitted-summary control still proves the tool interaction, but needs review because the concise progress state was discarded.

`PreCompact` is registered and its events are recorded if they fire. These short runs do not force automatic compaction. An empty event list means no compaction boundary was observed; it does not establish whether automatic compaction is enabled or how a long session would behave. The SDK's `get_context_usage()` is not used, because [an upstream report](https://github.com/anthropics/claude-agent-sdk-python/issues/1159) describes possible provider calls outside the streamed usage record.

Run the offline exercise with `uv run agent-lab lesson 25`. Run the three bounded provider-backed scenarios with `uv run python scripts/lesson_live_smoke.py 25 --live` after the live environment is configured. The latter writes a per-run report under `.lab-data/lesson-live-smoke/`.
