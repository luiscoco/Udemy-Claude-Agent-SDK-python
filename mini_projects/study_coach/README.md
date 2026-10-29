# Study Coach milestone project

Build a study coach for this course in seven stages. You write the host contracts in
[coach.py](coach.py); the course app runs **your** file at
<http://127.0.0.1:8080/coach>, so every stage you finish unlocks a feature on that page.

| Stage | Prompt | You implement | Unlocks on the page |
|---|---|---|---|
| M01 | [Start the app](prompts/m01-start-the-app.md) | nothing yet | the concept guide and prepared answers |
| M02 | [Validate and accept](prompts/m02-validate-and-accept.md) | `prepare_question`, `accept_answer` | asking questions; final answers replace drafts |
| M03 | [Choose a mode](prompts/m03-choose-a-mode.md) | `create_tutor_request` | the Live agent mode |
| M04 | [Keep the conversation](prompts/m04-keep-the-conversation.md) | `continue_conversation` | follow-ups in one conversation |
| M05 | [Validate a study plan](prompts/m05-validate-a-study-plan.md) | `validate_plan` | prepared and live study plans |
| M06 | [Recover a saved turn](prompts/m06-recover-a-saved-turn.md) | `recover_turn` | Inspect saved turn |
| M07 | [Verify and present](prompts/m07-verify-and-present.md) | evidence, no new code | your finished project |

## Run and check

```shell
uv run agent-lab serve                      # open http://127.0.0.1:8080/coach
uv run agent-lab coach check                # checks YOUR coach.py, stage by stage
uv run agent-lab coach check --reference    # checks the reference; never marks your work done
```

Raise `STAGE` in `coach.py` after each stage passes. Tests for later stages are skipped
until you do. On the page, choose **Your coach.py** or **Reference** to compare behavior;
**Reload my code** picks up your edits without restarting the server.

## How it fits together

- `coach.py` (yours) and `reference/coach.py` hold the same six functions. Pure Python:
  no SDK, no network, easy to test.
- `agent_lab/study_coach.py` is the server: it owns the Claude credentials, the SDK
  session id used to resume live conversations, and the saved turns in
  `.lab-data/study-coach/state.json`. The browser never sees any of them.
- Prepared mode answers from this course's lesson content with zero model calls. Live mode
  is optional: it needs `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true` in `.env`, and fresh
  consent for each paid question (0.05 USD threshold, one turn, no tools).

A generated answer is not evidence that a stage passed: the checks are.
