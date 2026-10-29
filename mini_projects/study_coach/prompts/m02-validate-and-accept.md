# M02 · Validate questions and accept only completed answers

**Goal:** Validate student input, and accept only confirmed, nonempty answers.

## Implement

`prepare_question`: trim strings, reject non-text, blank input and more than 2,000 characters (raise ValueError). `accept_answer`: require `status == "completed"` and nonempty `text`; return the complete text. Then set `STAGE = 2`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Ask a prepared question: watch RUNNING with the streamed draft, then the final answer.
2. Submit a blank question: it fails clearly and nothing is sent.
3. Compare the draft with the final answer: the completed text replaces the draft.

## Expected result

Valid questions produce formatted prepared answers; blank input is rejected before submission.

## Check

```shell
uv run agent-lab coach check
```

## Hints

1. A partial stream is not a result. Only a completed status establishes completion.
2. Return the completed answer as a replacement for the streamed draft, never draft + answer.

## Quiz

- **A turn has status running and text 'partial dra'. What does accept_answer do?**
  Raise ValueError: a running turn is not complete.
- **Why trim before checking for blank input?**
  '   ' has length 3 but no content; trimming makes the blank check honest.

Related lesson: [lesson 1](http://127.0.0.1:8080/?lesson=1).
