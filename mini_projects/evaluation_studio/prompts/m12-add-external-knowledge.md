# M12 · Add external knowledge with MCP

**Goal:** Add evidence-backed external knowledge and make the timeline useful for debugging.

## Implement

`mcp_settings(mode, name, url, tools)`: none gives no servers; docs gives the official docs server with `mcp__claude_docs__*`; custom needs a short name, a public HTTPS URL without credentials, query or fragment (no localhost or private addresses) and one to five exact tool names, allowed as `mcp__<name>__<tool>`. Set `STAGE = 5`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Live run with **Official docs MCP**: tick both consent boxes, then check MCP calls in the result.
2. Compare the same case with and without the docs source: evidence, latency and cost.
3. Try a custom URL with `?token=` or `http://`: it is refused before any connection.

## Expected result

The timeline separates a configured source from an actual MCP tool call.

## Check

```shell
uv run agent-lab studio check
```

## Hints

1. Configuration is not use: only a tool_use event shows the source was called.
2. Credentials stay in the server environment, never in URLs or the browser.

## Quiz

- **Why reject https://127.0.0.1/mcp?**
  Private and loopback addresses can reach internal services.
- **A server is configured but no MCP tool was called. Is the answer grounded?**
  No: it is unverified by that source.

Related lesson: [lesson 43](http://127.0.0.1:8080/?lesson=43).
