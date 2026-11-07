# Lesson 30: Todo tracking

The original offline exercise validates six local task transitions. The enhanced experiment uses the pinned Claude CLI's real `TodoWrite` tool on one isolated SDK session. This CLI exposes the legacy tool when `CLAUDE_CODE_ENABLE_TASKS=0` is set for the lesson's child environment; without that setting, its initialization inventory was empty and the model printed a tool-call-shaped string instead of invoking a tool.

The host owns three exact task identities. A `PreToolUse` hook rejects missing, duplicate or unknown tasks, illegal status changes and more than one task in progress. Accepted proposals are staged by tool-use ID. A matching `PostToolUse` callback commits them only after the actual tool succeeds. The automatic check correlates each SDK call/result ID, pre decision, accepted post callback, final ledger and a suggestion derived from that ledger.

The four live cases cover valid progress, skipping directly from pending to completed, two active tasks, and reopening a completed task. Denied calls leave the prior ledger unchanged. Recorded negative scenarios exercise missing or mismatched evidence offline. This is a fixed teaching ledger, not a general task-management service.

Run the offline exercise with `uv run agent-lab lesson 30`. Run the four bounded provider-backed cases with `uv run python scripts/lesson_live_smoke.py 30 --live` after the live environment is configured. Reports are saved under `.lab-data/lesson-live-smoke/`.
