# Lesson 33: MCP elicitation

The provider-backed Agent SDK calls one owned `mcp__rooms__book_room` tool. Its host handler opens an in-memory Python MCP client/server session. The server requests a fixed booking form; the MCP client's callback supplies the selected **simulated host response**. Accept provides validated Student/2/confirmed data and books the local Blue room. Decline and cancel return distinct no-booking states. No external calendar is contacted.

The automatic check requires one SDK tool call and matching result, one MCP form callback from the owned server, the selected action, the actual server outcome, and a successful terminal on the initialized SDK session. The original `elicitation` exercise separately demonstrates four direct MCP callback outcomes, including invalid accepted data.

This adapter is intentional. In this installed Agent SDK, `ClaudeAgentOptions` has no `on_elicitation` option. Earlier live probes showed that `Elicitation` and `ElicitationResult` hooks fired and returned accept/decline/cancel decisions, but the MCP server received cancel in all cases. A callback log alone therefore did not establish the server outcome. The final path uses the Python MCP client's supported `elicitation_callback` and verifies the returned server data. It does not establish native Agent SDK elicitation routing.

## Live acceptance

All three final provider-backed variants passed on 3 November 2026:

| Host selection | Actual MCP server result | Stream reported USD |
|---|---|---:|
| Accept | Blue room booked locally | 0.00888050 |
| Decline | `state: decline`, `booked: false` | 0.00845445 |
| Cancel | `state: cancel`, `booked: false` | 0.00847215 |

Final run cost: **$0.02580710**. Report: `.lab-data/lesson-live-smoke/lesson-33-20261103T133638514476Z/report.json`. Three earlier probes of the CLI hook path reported $0.011960, $0.012294 and $0.003858 respectively; their reports are under `.lab-data/lesson-live-smoke/lesson-33-20261103T132946988913Z`, `lesson-33-20261103T133152588671Z` and `lesson-33-20261103T133355233726Z`. Combined stream-reported cost: **$0.05391910**.

References: [Python MCP elicitation handlers](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/handlers/elicitation.md), [Agent SDK hook output types](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py).
