# M09 · Summarize a run honestly

**Goal:** Turn SDK messages into an answer and a timeline without overstating success.

## Implement

`summarize_run(messages)`: collect top-level assistant text, count MCP and specialist tool calls, record tool results and MCP connections, and take the subtype from the final result. The run is an error unless that result is `success` with `is_error` false and no stream error followed. Without a result the subtype is `sdk_stream_error`. Set `STAGE = 2`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Run a prepared case: the badge says PREPARED FIXTURE and the subtype is success.
2. Choose the scenario **Turn limit reached**: partial text, subtype `error_max_turns`.
3. Choose **Turn limit, then a stream error**: it must stay a failure.

## Expected result

A fluent answer never hides a failed or limited run; the timeline shows how the run ended.

## Check

```shell
uv run agent-lab studio check
```

## Hints

1. Text is content; only the final result reports how the run ended.
2. Subagent text has a parent_tool_use_id and is not the user-facing answer.

## Quiz

- **Assistant text arrived, then the result says error_max_turns. Success?**
  No: the result decides; the text is partial.
- **The iterator raised after a success result. What then?**
  Mark the run as an error: the stream did not end cleanly.

Related lesson: [lesson 1](http://127.0.0.1:8080/?lesson=1).
