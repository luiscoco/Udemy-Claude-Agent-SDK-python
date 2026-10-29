# M04 · Keep the conversation

**Goal:** Keep the application conversation identity separate from the provider's session id.

## Implement

`continue_conversation(current_id, returned_id)`: for a new conversation (current_id is None) accept a valid returned UUID; for an existing one the returned id must equal current_id. Reject missing, invalid or different ids. Set `STAGE = 4`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Ask a question, then a follow-up: the conversation id stays the same and the fixture answer quotes your earlier question.
2. Choose New conversation: the next answer gets another id.
3. Start a new conversation before changing mode.

## Expected result

Fixture follow-ups display the earlier question; live follow-ups resume the server-held SDK session.

## Check

```shell
uv run agent-lab coach check
```

## Hints

1. Application UUIDs group your turns. The Claude SDK session id is a different, opaque value kept on the server for `resume`.
2. If the server ever answers a different conversation, refuse it rather than switching silently.

## Quiz

- **Why not use the SDK session id as the conversation id?**
  It belongs to the provider, may change, and must stay on the server.
- **current_id is A and the server returns B. What happens?**
  continue_conversation raises ValueError.

Related lesson: [lesson 6](http://127.0.0.1:8080/?lesson=6).
