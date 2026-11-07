# Lesson 27: Background tasks

The original offline exercise starts a Python coroutine, cancels it, awaits it, and checks its `finally` cleanup. The enhanced experiment carries a host-owned watcher across one real SDK query. The watcher is pending when the query begins; after the successful SDK result, the host either cancels it or releases its waiting event. Both endings await the task and verify its cleanup before disconnecting the client.

The automatic check requires a successful result in the initialized SDK session, the fixed response marker, a watcher that was running during the query, a completed await and `finally` cleanup, the selected cancellation or release outcome, and a closed SDK connection. Recorded negative scenarios remove individual observations offline.

SDK-managed background agent or Bash tasks have a separate lifecycle. They expose `TaskStartedMessage.task_id` and can be stopped with `ClaudeSDKClient.stop_task(task_id)`; terminal status can arrive through `TaskUpdatedMessage` or `TaskNotificationMessage`. This experiment verifies host `asyncio` task ownership and does not claim to exercise that CLI-managed task path. See the [official SDK client method](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py) for its contract.

Run the offline exercise with `uv run agent-lab lesson 27`. Run both bounded provider-backed cases with `uv run python scripts/lesson_live_smoke.py 27 --live` after the live environment is configured. Reports are saved under `.lab-data/lesson-live-smoke/`.
