# M06 · Recover a saved turn

**Goal:** Inspect saved work before deciding whether another request is appropriate.

## Implement

`recover_turn(turn)`: return `reuse` for a completed nonempty answer, `wait` for running, `new-turn` for a confirmed failure and `inspect` for uncertain or unrecognised states. Set `STAGE = 6`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Ask a prepared question and reload the page while it is running.
2. Paste the turn id into Inspect saved turn: `wait` while it runs, then `reuse` with the saved answer.
3. Stop the server during a running turn and start it again: the turn becomes uncertain and its conversation is blocked.

## Expected result

The saved answer can be recovered, and inspecting never calls the model or starts another turn.

## Check

```shell
uv run agent-lab coach check
```

## Hints

1. The server keeps working after a browser disconnect; a disconnect does not prove the provider stopped.
2. Never resubmit an uncertain live turn automatically: it may already have run and cost money.

## Quiz

- **A live turn's network call failed after sending. Which action?**
  inspect: the outcome is uncertain, so no automatic retry.
- **Why does a restart block the conversation?**
  Work that was running may or may not have reached the provider.

Related lesson: [lesson 28](http://127.0.0.1:8080/?lesson=28).
