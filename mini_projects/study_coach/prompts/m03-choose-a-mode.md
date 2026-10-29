# M03 · Choose fixture or live mode

**Goal:** Choose fixture or live mode while keeping API credentials on the server.

## Implement

`create_tutor_request(question, mode, conversation_id=None)`: allow only `fixture` or `live`, validate the question with `prepare_question`, and accept `conversation_id` only when it is None or a canonical UUID string. Return `{"question", "mode", "conversation_id"}`. Set `STAGE = 3`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Run the fixture checks; they need no credentials.
2. Optional live: set `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true` in `.env`, restart, choose Live agent, tick consent and ask for a small code snippet.
3. Confirm the live answer addresses your actual question and renders Markdown like the prepared one.

## Expected result

Fixture questions work without keys; a live question needs fresh consent each time.

## Check

```shell
uv run agent-lab coach check
```

## Hints

1. The server re-sends the coach instructions on every turn and resumes its own SDK session id; the browser never receives credentials.
2. Reject `LIVE`, `paid` and malformed ids instead of guessing what the caller meant.

## Quiz

- **Where does the API key live?**
  Only in the server environment (.env); the page and your coach.py never see it.
- **Is 'NOT-A-UUID' an acceptable conversation id?**
  No: only None or a canonical UUID string.

Related lesson: [lesson 4](http://127.0.0.1:8080/?lesson=4).
