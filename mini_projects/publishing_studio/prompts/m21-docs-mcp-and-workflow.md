# M21 · Optional docs MCP and the full workflow

**Goal:** Add optional external documentation and verify the whole student workflow.

## Implement

`source_settings(source, mode, mcp_consent)`: no source; or the official docs MCP, which in live mode needs its own consent, allows only `mcp__claude_docs__*` and more turns. Prepared mode says the source was not used. Set `STAGE = 7`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Live answer with **Official Claude documentation MCP**: tick both consent boxes.
2. Read MCP calls in the answer details: zero calls means the source was not used.
3. Complete the prepared flow from prompt to four downloaded files without a paid call.
4. Download the project ZIP from the status card.

## Expected result

The answer details show model, origin, subtype, cost, files, MCP call count and source; every file shows its SHA-256.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. Configured is not used: only a tool call shows the documentation was consulted.
2. MCP retrieval can need more turns and budget; explain a limit, never show a sample as live.

## Quiz

- **The docs MCP was configured but no MCP tool was called. Is the answer grounded?**
  No: it is not verified by that source.
- **Does building a document need MCP?**
  No: builders stay local; MCP is only for retrieval.

Related lesson: [lesson 43](http://127.0.0.1:8080/?lesson=43).
