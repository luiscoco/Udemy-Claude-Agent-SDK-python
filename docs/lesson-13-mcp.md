# Lesson 13: MCP servers

The selected experiment compares an owned stdio child process, loopback HTTP service and in-process SDK server. All three expose `stock` and `reserve`. The default reservation changes notebook stock from 12 to 10. Only the selected tool is permitted; a live agent reservation is limited to one write with the authorized item and quantity. The old notes-server example remains as a separate reference.

Offline mode really connects, discovers tool schemas, calls MCP tools and reads host inventory before and after. Its agent call/result identities and parent outcome are explicitly recorded fixtures. Live mode uses actual SDK status, `toggle_mcp_server`/`reconnect_mcp_server` controls and the actual agent stream. The automatic check requires a configured permitted tool, one successful result matching its call/run identity, initialized parent identity and successful parent completion. Configuration, tool discovery and file changes alone cannot satisfy that criterion. Remote service correctness is not certified.

Try the disabled configuration, missing-evidence, mismatched-identity and inventory-error comparisons. The last requires an enabled Reserve tool and starts with exhausted fixture stock. The server returns an explicit error and changes no stock. The installed Python SDK maps its handler's `is_error` field to MCP's `isError`; an error message with a false flag is not accepted as error evidence.

The separate **MCP transport workshop · no model calls** supports status/tool discovery, stock inspection, reservations, disable/enable, reconnect, selecting another owned transport, reset and end. It uses its own inventory and does not complete the automatic agent check. Its handle persists inventory and enablement, not a live Claude conversation. Each operation opens and closes its transport in the same task. **Last probe connected** is historical; **Connection open** reports the current resource state. Disabling blocks before a transport or tool starts. Changing transport selects the next connection; probe it separately. Reset affects only that workshop's stock.

The browser cannot supply arbitrary commands, paths, URLs, headers or tool names. Reservations validate item and integer quantity before effects. Workshops use control tokens, bounded concurrency, at most 30 actions and ten-minute expiry. The archive holds at most 32 workshops. Read-only inspection of completed stock remains available with its token. Connection/protocol errors remain visible, and failed agent/authentication results do not pass or trigger host retries. Owned transports close on success, errors and cancellation.

## API and CLI

`POST /api/c13/query` runs the bounded agent experiment. Its strict request accepts mode, prompt, limits, scenario and typed `lesson_options`: transport, tool, sku, quantity, enabled and lifecycle. Live queries additionally require `consent=true` and enabled/configured live access.

The no-model workshop routes are `POST /api/c13/session`, `/log`, `/mcp`, `/send`, `/status`, `/toggle`, `/reconnect`, `/set-servers`, `/stock/reset` and `/end`. Creation returns an application handle and control token. Every later POST requires both. `GET /api/c13/stock` takes `application_handle` as a query parameter and the token in the `x-control-token` header. Configuration/log/stock inspection makes no model call. A status or reconnect action performs a real MCP handshake, then closes the transport. `/send` calls a validated inventory tool directly; it does not send an agent prompt. Responses distinguish observed state, tool results and inventory.

The shared lesson run, stream/WebSocket routes and CLI use the same validated experiment:

```shell
uv run agent-lab lesson 13
uv run agent-lab lesson 13 --scenario tool-error
uv run agent-lab lesson 13 --lesson-options-file mcp-options.json
```

For the last command, use `{"transport":"stdio","tool":"reserve","quantity":2,"lifecycle":"toggle"}`. Negative recorded scenarios are offline only. Inputs are rejected before creating an agent task/workspace when invalid.

Seven explained questions, hints, a worked explanation and a challenge appear in **Learn**; the original two question positions are preserved. Three exact excerpts cover server configuration, the transport experiment and the shared evidence evaluator. Guides, quizzes and source inspection never run an agent or complete manual review.

This adapts the pinned [MCP teaching contract](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/blob/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts/l13-lesson-13-mcp-servers.md). Workshop handles are not persistent live-agent MCP sessions. Live lifecycle controls occur before one bounded query; dynamic server selection in the workshop applies to successive owned connections. Arbitrary remote/authenticated services, paid account acceptance, authored media and recorded narration remain pending. Automated agent-stream tests use injected producers; transport and inventory effects are real local fixtures. Lesson 14's thinking/model comparisons are next.
