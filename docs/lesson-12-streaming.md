# Lesson 12: Streaming input

Open lesson 12 and choose **Run the exercise**. The default offline script sends the prompt and follow-up through one input iterator. Compare **Queue both messages** with **Wait for the first result**, and optionally request a runtime model or permission-mode change. These are acknowledged SDK control requests, separate from proof of model behavior or permission effects. The lesson exposes no agent tools.

To try a persistent session, select **Keep session open for manual messages** before running. The initial prompt consumes one authorized message. The limit defaults to two and can be raised to four before the run starts. **Queue message** pushes later input into the same iterator; **End input** wakes an idle queue and drains queued work. **Cancel** aborts. The host deadline also applies while idle. Opening a fresh run is required after closure.

The displayed application handle identifies owned host objects. The SDK identity comes from initialization; input UUIDs identify submitted messages. They serve different purposes. The timeline distinguishes queued inputs, yielded inputs, SDK results and runtime-control acknowledgements. Yielding is not per-message completion evidence. The bounded check requires matching input/application identities, successful results under the initialized SDK identity, and observed input-iterator, output and connection closure. It does not grade queue timing or recall. An interrupted queue remains visible and needs review.

Offline mode uses the official SDK client with a scripted CLI transport; it makes no model call. Live mode uses the same queue and owner loop with the real CLI. Connect/disconnect remain in one owning task; a response pump lets the owner process runtime controls while multiple turns arrive. Cleanup cancels pumps, closes input and disconnects before emitting the final summary. A blocked event consumer cannot hold SDK cleanup indefinitely.

The seven explained questions, two hints, worked explanation and challenge are in **Learn**. The original two question indices are preserved for saved answers. Three source excerpts show the queue, owner loop and evaluator with current line references. The compact original `query()` example remains separately available. Source inspection, context inspection, quizzes and guides make no model call and never complete manual review.

## Session routes

The browser uses the same owned runtime as `/api/c12/session`, `/send`, `/model`, `/permission-mode`, `/context`, `/end` and `/script` (all POST). Session/script creation returns an application handle and control token. Later requests must include both; an SDK session ID does not grant access. Context inspection returns a snapshot and final evidence without sending input or changing controls. Completed snapshots are retained in a bounded archive of 32 sessions, while active sessions remain subject to the shared concurrency limit.

Creation accepts the standard run fields and `lesson_options`: `interactive`, `queue_timing`, `runtime_control` and `max_messages`. The session route selects manual mode; script selects automatic mode. Live creation additionally requires `consent=true` and enabled/configured live access. Invalid values are rejected before creating a task or workspace. Runtime model values are `haiku` or `sonnet`; permission modes are `default` or `plan`. Bypass modes, arbitrary session IDs and unknown options are rejected. Acknowledged changes are displayed separately from observed model behavior. Closed and stale handles cannot send more input or controls.

The shared `/api/lessons/12/run`, streaming and WebSocket routes still work. Use scripted mode with the blocking run/CLI interfaces. The CLI accepts explicit JSON options files:

```shell
uv run agent-lab lesson 12
uv run agent-lab lesson 12 --scenario interrupted
uv run agent-lab lesson 12 --lesson-options-file stream-options.json
```

For the last example, use `{"queue_timing":"after-result","runtime_control":"permission"}`. Missing-evidence, mismatched-identity and interrupted scenarios are offline demonstrations; they cannot be selected for live or manual sessions.

The [pinned reference contract](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/blob/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts/l12-lesson-12-streaming-input.md) is adapted through the installed Python SDK's public `ClaudeSDKClient.connect(prompt=async_iterator)` API. Automated verification uses scripted/injected transports. Paid account/model acceptance, authored image assets, recorded narration and full reference certification remain separate work. Lesson 13's MCP lifecycle controls are next.
